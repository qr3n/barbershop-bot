from __future__ import annotations

from functools import lru_cache
from typing import FrozenSet

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str

    # Make: incoming messages webhook (where we POST any user message)
    make_webhook_url: str

    # Optional: token for OUR -> Make webhook (if your Make webhook is protected)
    make_outgoing_bearer_token: str | None = None

    # Token used for Make -> OUR endpoints (/make/*: booking + callback)
    make_bearer_token: str

    # Admin-only token (masters + working hours management)
    admin_bearer_token: str | None = None

    public_base_url: str | None = None

    # DB
    database_url: str

    # bootstrap
    admin_telegram_ids: str = ""

    timezone: str = "Europe/Moscow"

    @property
    def admin_ids(self) -> FrozenSet[int]:
        ids: set[int] = set()
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if not part:
                continue
            ids.add(int(part))
        return frozenset(ids)


@lru_cache
def get_settings() -> Settings:
    return Settings()
