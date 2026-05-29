"""Tests for GET /api/health endpoint."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "xmuse" / "dashboard_api.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("xmuse_dashboard_api_health", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


create_app = _load_module().create_app


def test_health_returns_ok_and_version(tmp_path):
    client = TestClient(create_app(base_dir=tmp_path))
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["graph_authority"]["merge_state"] == "unknown"
    assert body["graph_authority"]["lineage_status"] == "unknown"
