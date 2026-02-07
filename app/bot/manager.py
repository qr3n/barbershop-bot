from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.dispatcher import setup_dispatcher
from app.bot.make_client import MakeClient, MakeClientConfig
from app.db.models import BotLog, BotLogLevel, BotSettings

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class BotStatus(str, enum.Enum):
    stopped = "stopped"
    starting = "starting"
    running = "running"
    stopping = "stopping"
    error = "error"


@dataclass
class BotState:
    status: BotStatus = BotStatus.stopped
    started_at: datetime | None = None
    error_message: str | None = None
    bot_username: str | None = None


class BotManager:
    """Manages the Telegram bot lifecycle with support for restart and token changes."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self._settings = settings
        self._session_factory = session_factory
        
        self._bot: Bot | None = None
        self._dp: Dispatcher | None = None
        self._make_client: MakeClient | None = None
        self._polling_task: asyncio.Task | None = None
        
        self._state = BotState()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> BotState:
        return self._state

    @property
    def bot(self) -> Bot | None:
        return self._bot

    @property
    def make_client(self) -> MakeClient | None:
        return self._make_client

    async def _log_event(
        self,
        level: BotLogLevel,
        message: str,
        details: str | None = None,
    ) -> None:
        """Log bot event to database."""
        try:
            async with self._session_factory() as session:
                log_entry = BotLog(
                    level=level,
                    message=message,
                    details=details,
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to log bot event to DB: {e}")

    async def get_bot_token(self) -> str | None:
        """Get bot token from DB, fallback to settings."""
        async with self._session_factory() as session:
            bot_settings = await session.get(BotSettings, 1)
            if bot_settings and bot_settings.bot_token:
                return bot_settings.bot_token
        return self._settings.bot_token if self._settings.bot_token else None

    async def get_bot_settings(self) -> BotSettings | None:
        """Get bot settings from DB."""
        async with self._session_factory() as session:
            return await session.get(BotSettings, 1)

    async def update_bot_token(self, token: str) -> None:
        """Update bot token in database."""
        async with self._session_factory() as session:
            bot_settings = await session.get(BotSettings, 1)
            if bot_settings:
                bot_settings.bot_token = token
                bot_settings.updated_at = datetime.now(timezone.utc)
            else:
                bot_settings = BotSettings(id=1, bot_token=token, is_enabled=True)
                session.add(bot_settings)
            await session.commit()
        
        await self._log_event(BotLogLevel.info, "Bot token updated")

    async def set_enabled(self, enabled: bool) -> None:
        """Enable or disable bot in database."""
        async with self._session_factory() as session:
            bot_settings = await session.get(BotSettings, 1)
            if bot_settings:
                bot_settings.is_enabled = enabled
                bot_settings.updated_at = datetime.now(timezone.utc)
            else:
                bot_settings = BotSettings(id=1, is_enabled=enabled)
                session.add(bot_settings)
            await session.commit()

    async def start(self) -> bool:
        """Start the bot. Returns True if started successfully."""
        async with self._lock:
            if self._state.status == BotStatus.running:
                return True

            self._state.status = BotStatus.starting
            self._state.error_message = None

            try:
                token = await self.get_bot_token()
                if not token:
                    self._state.status = BotStatus.stopped
                    self._state.error_message = "No bot token configured"
                    await self._log_event(BotLogLevel.warning, "Bot start failed: no token configured")
                    return False

                # Check if bot is enabled
                bot_settings = await self.get_bot_settings()
                if bot_settings and not bot_settings.is_enabled:
                    self._state.status = BotStatus.stopped
                    self._state.error_message = "Bot is disabled"
                    await self._log_event(BotLogLevel.info, "Bot start skipped: disabled in settings")
                    return False

                # Create bot instance
                self._bot = Bot(token=token)
                
                # Validate token by getting bot info
                try:
                    bot_info = await self._bot.get_me()
                    self._state.bot_username = bot_info.username
                except Exception as e:
                    await self._bot.session.close()
                    self._bot = None
                    self._state.status = BotStatus.error
                    self._state.error_message = f"Invalid token: {str(e)}"
                    await self._log_event(BotLogLevel.error, "Bot start failed: invalid token", str(e))
                    return False

                # Create Make client
                self._make_client = MakeClient(
                    MakeClientConfig(
                        webhook_url=self._settings.make_webhook_url,
                        bearer_token=self._settings.make_outgoing_bearer_token,
                    )
                )

                # Setup dispatcher
                self._dp = setup_dispatcher(
                    bot=self._bot,
                    session_factory=self._session_factory,
                    make_client=self._make_client,
                    public_base_url=self._settings.public_base_url,
                )

                # Start polling
                self._polling_task = asyncio.create_task(self._dp.start_polling(self._bot))
                
                self._state.status = BotStatus.running
                self._state.started_at = datetime.now(timezone.utc)
                
                await self._log_event(
                    BotLogLevel.info,
                    f"Bot started successfully",
                    f"Username: @{self._state.bot_username}"
                )
                
                return True

            except Exception as e:
                self._state.status = BotStatus.error
                self._state.error_message = str(e)
                await self._log_event(BotLogLevel.error, "Bot start failed", str(e))
                logger.exception("Failed to start bot")
                return False

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        async with self._lock:
            if self._state.status not in (BotStatus.running, BotStatus.starting):
                return

            self._state.status = BotStatus.stopping
            
            try:
                # Cancel polling task
                if self._polling_task:
                    self._polling_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._polling_task
                    self._polling_task = None

                # Close Make client
                if self._make_client:
                    await self._make_client.aclose()
                    self._make_client = None

                # Close bot session
                if self._bot:
                    await self._bot.session.close()
                    self._bot = None

                self._dp = None
                self._state.status = BotStatus.stopped
                self._state.started_at = None
                
                await self._log_event(BotLogLevel.info, "Bot stopped")
                
            except Exception as e:
                self._state.status = BotStatus.error
                self._state.error_message = str(e)
                await self._log_event(BotLogLevel.error, "Bot stop failed", str(e))
                logger.exception("Failed to stop bot")

    async def restart(self) -> bool:
        """Restart the bot. Returns True if restarted successfully."""
        await self._log_event(BotLogLevel.info, "Bot restart initiated")
        await self.stop()
        return await self.start()

    async def get_logs(self, limit: int = 50) -> list[BotLog]:
        """Get recent bot logs."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(BotLog)
                .order_by(BotLog.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def shutdown(self) -> None:
        """Clean shutdown for application exit."""
        await self.stop()
