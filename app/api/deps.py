from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from aiogram import Bot
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.bot.manager import BotManager


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_bot(request: Request) -> Bot:
    bot_manager: BotManager = request.app.state.bot_manager
    if bot_manager.bot is None:
        raise HTTPException(status_code=503, detail="Bot is not running")
    return bot_manager.bot


def get_bot_manager(request: Request) -> "BotManager":
    return request.app.state.bot_manager
