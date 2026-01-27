from __future__ import annotations

from aiogram import Bot


async def send_text(bot: Bot, chat_id: int, text: str) -> None:
    await bot.send_message(chat_id=chat_id, text=text)
