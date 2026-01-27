from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.make_client import MakeClient
from app.db.models import MakeRequest, MakeRequestStatus


def setup_dispatcher(
    *,
    bot: Bot,
    session_factory: async_sessionmaker,
    make_client: MakeClient,
    public_base_url: str | None,
) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(F.text | F.caption | F.sticker | F.photo | F.voice | F.video | F.document)
    async def on_any_message(message: Message) -> None:
        correlation_id = uuid.uuid4().hex

        callback_url = None
        if public_base_url:
            callback_url = public_base_url.rstrip("/") + "/make/callback"

        payload = {
            "correlation_id": correlation_id,
            "chat_id": message.chat.id,
            "user_id": message.from_user.id if message.from_user else None,
            "message_id": message.message_id,
            "text": message.text or message.caption or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "callback_url": callback_url,
        }

        # Persist mapping (correlation_id -> chat_id) so callback can reply to correct chat.
        async with session_factory() as session:
            req = MakeRequest(
                correlation_id=correlation_id,
                chat_id=message.chat.id,
                user_id=message.from_user.id if message.from_user else 0,
                message_id=message.message_id,
                status=MakeRequestStatus.created,
            )
            session.add(req)
            await session.commit()
            req_id = req.id

        async def _send_background() -> None:
            async with session_factory() as session:
                try:
                    await make_client.send_incoming_message(payload)
                    req2 = await session.get(MakeRequest, req_id)
                    if req2:
                        req2.status = MakeRequestStatus.sent
                        req2.last_error = None
                    await session.commit()
                except Exception as e:  # noqa: BLE001
                    req2 = await session.get(MakeRequest, req_id)
                    if req2:
                        req2.status = MakeRequestStatus.failed
                        req2.last_error = str(e)[:500]
                    await session.commit()

        asyncio.create_task(_send_background())

    return dp
