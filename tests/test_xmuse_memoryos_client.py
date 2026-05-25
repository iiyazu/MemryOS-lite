from __future__ import annotations

import pytest
import httpx

from xmuse_core.agents.memoryos_client import MemoryOSClient


@pytest.mark.asyncio
async def test_create_session():
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, json={"id": "ses_123", "title": "test", "created_at": "2026-01-01T00:00:00Z"}
    ))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        sid = await mos.create_session("feature:my-feat")
        assert sid == "ses_123"


@pytest.mark.asyncio
async def test_build_context():
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, json={"context": "some historical context"}
    ))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        ctx = await mos.build_context("ses_123", "fix the bug", budget=4096)
        assert "context" in ctx


@pytest.mark.asyncio
async def test_ingest():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        await mos.ingest("ses_123", "assistant", "I fixed the bug")


@pytest.mark.asyncio
async def test_degraded_mode_on_connection_error():
    def raise_error(req):
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(raise_error)
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        sid = await mos.create_session("test")
        assert sid is None
