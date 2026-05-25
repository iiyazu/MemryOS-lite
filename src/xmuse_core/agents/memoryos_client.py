from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class MemoryOSClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = http_client

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client:
            return self._client
        self._client = httpx.AsyncClient(headers=self._headers())
        return self._client

    async def create_session(self, title: str) -> str | None:
        try:
            client = await self._get_client()
            resp = await client.post(f"{self._base_url}/sessions", json={"title": title})
            resp.raise_for_status()
            return resp.json()["id"]
        except (httpx.HTTPError, KeyError) as e:
            logger.warning("memoryos create_session failed: %s", e)
            return None

    async def build_context(self, session_id: str, task: str, budget: int = 4096) -> str:
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self._base_url}/sessions/{session_id}/build-context",
                json={"task": task, "budget": budget},
            )
            resp.raise_for_status()
            return str(resp.json())
        except httpx.HTTPError as e:
            logger.warning("memoryos build_context failed: %s", e)
            return ""

    async def ingest(self, session_id: str, role: str, content: str) -> None:
        try:
            client = await self._get_client()
            await client.post(
                f"{self._base_url}/sessions/{session_id}/ingest",
                json={"role": role, "content": content},
            )
        except httpx.HTTPError as e:
            logger.warning("memoryos ingest failed: %s", e)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
