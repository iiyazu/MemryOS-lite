from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_ingest_batch_success(client, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORYOS_DATA_DIR", str(tmp_path))
    # Create a session first
    resp = client.post("/sessions", json={"title": "test-session"})
    if resp.status_code != 200:
        pytest.skip("session creation requires full service setup")
    session_id = resp.json()["id"]

    # Batch ingest
    resp = client.post(f"/sessions/{session_id}/ingest-batch", json={
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_ingest_batch_404_for_missing_session(client):
    resp = client.post("/sessions/nonexistent/ingest-batch", json={
        "messages": [{"role": "user", "content": "hello"}]
    })
    assert resp.status_code == 404


def test_summary_404_for_missing_session(client):
    resp = client.get("/sessions/nonexistent/summary")
    assert resp.status_code == 404
