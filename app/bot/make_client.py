from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class MakeClientConfig:
    webhook_url: str
    bearer_token: str | None = None
    timeout_s: float = 10.0


class MakeClient:
    def __init__(self, cfg: MakeClientConfig):
        self._cfg = cfg
        self._client = httpx.AsyncClient(timeout=cfg.timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_incoming_message(self, payload: dict) -> None:
        headers: dict[str, str] = {}
        if self._cfg.bearer_token:
            headers["Authorization"] = f"Bearer {self._cfg.bearer_token}"

        for attempt in range(3):
            try:
                resp = await self._client.post(self._cfg.webhook_url, json=payload, headers=headers)
                resp.raise_for_status()
                return
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
