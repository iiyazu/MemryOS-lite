"""Tests for the xmuse callback HTTP server."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from xmuse_core.routing.callbacks import CallbackCredentials, CallbackRouter
from xmuse_core.routing.server import create_app
from xmuse_core.routing.worklist import Worklist


@pytest.fixture
def worklist() -> Worklist:
    return Worklist()


@pytest.fixture
def router(worklist: Worklist) -> CallbackRouter:
    return CallbackRouter(worklist)


@pytest.fixture
def creds(router: CallbackRouter) -> CallbackCredentials:
    c = CallbackCredentials(
        invocation_id="inv-001",
        callback_token="tok-secret",
        agent_id="agent-alpha",
        loop_id="loop-1",
    )
    router.register(c)
    return c


@pytest_asyncio.fixture
async def client(worklist: Worklist, router: CallbackRouter) -> AsyncClient:
    app = create_app(worklist, router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_worklist_status_empty(client: AsyncClient) -> None:
    resp = await client.get("/callbacks/worklist-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending"] == 0
    assert data["aborted"] is False


@pytest.mark.asyncio
async def test_post_message_valid(
    client: AsyncClient, creds: CallbackCredentials
) -> None:
    resp = await client.post(
        "/callbacks/post-message",
        json={
            "invocation_id": creds.invocation_id,
            "callback_token": creds.callback_token,
            "content": "Hey @agent-beta check this",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "agent-beta" in data["enqueued"]


@pytest.mark.asyncio
async def test_post_message_invalid_creds(client: AsyncClient) -> None:
    resp = await client.post(
        "/callbacks/post-message",
        json={
            "invocation_id": "bad-id",
            "callback_token": "bad-tok",
            "content": "hello @someone",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_abort_valid(
    client: AsyncClient, creds: CallbackCredentials, worklist: Worklist
) -> None:
    resp = await client.post(
        "/callbacks/abort",
        json={
            "invocation_id": creds.invocation_id,
            "callback_token": creds.callback_token,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["aborted"] is True
    assert worklist.chain.aborted is True


@pytest.mark.asyncio
async def test_abort_invalid_creds(client: AsyncClient) -> None:
    resp = await client.post(
        "/callbacks/abort",
        json={
            "invocation_id": "wrong",
            "callback_token": "wrong",
        },
    )
    assert resp.status_code == 401
