from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_env():
    old = os.environ.pop("MEMORYOS_API_KEY", None)
    yield
    if old:
        os.environ["MEMORYOS_API_KEY"] = old
    else:
        os.environ.pop("MEMORYOS_API_KEY", None)


def _get_app():
    from memoryos_lite.api.app import app

    return app


def test_request_id_injected():
    client = TestClient(_get_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "X-Request-Id" in resp.headers
    assert len(resp.headers["X-Request-Id"]) == 32


def test_request_id_preserved_from_client():
    client = TestClient(_get_app())
    resp = client.get("/health", headers={"X-Request-Id": "my-custom-id"})
    assert resp.headers["X-Request-Id"] == "my-custom-id"


def test_no_api_key_configured_allows_all():
    os.environ.pop("MEMORYOS_API_KEY", None)
    client = TestClient(_get_app())
    resp = client.get("/health")
    assert resp.status_code == 200


def _keyed_client(api_key: str) -> TestClient:
    from fastapi import FastAPI

    from memoryos_lite.middleware import ApiKeyAuthMiddleware

    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware, api_key=api_key)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/sessions")
    def sessions() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"X-API-Key": "secret-key"}, 200),
        ({"X-API-Key": "secret-kez"}, 401),
        ({"X-API-Key": "secret-key-longer"}, 401),
        ({"X-API-Key": "Ü-not-ascii".encode("latin-1")}, 401),
        ({}, 401),
    ],
)
def test_api_key_guards_protected_routes(headers, expected):
    resp = _keyed_client("secret-key").get("/sessions", headers=headers)
    assert resp.status_code == expected
    if expected == 401:
        assert resp.json() == {"detail": "invalid_api_key"}


def test_api_key_leaves_health_open():
    assert _keyed_client("secret-key").get("/health").status_code == 200
