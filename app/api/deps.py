from __future__ import annotations

from collections.abc import AsyncIterator

from aiogram import Bot
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_bot(request: Request) -> Bot:
    return request.app.state.bot
