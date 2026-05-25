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
