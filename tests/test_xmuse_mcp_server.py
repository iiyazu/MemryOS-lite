from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "xmuse" / "mcp_server.py"


def load_mcp_module():
    spec = importlib.util.spec_from_file_location("xmuse_mcp_server", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def mcp_call(client: TestClient, name: str, arguments: dict | None = None) -> dict:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": f"call-{name}",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "error" not in payload, payload
    result = payload["result"]
    assert result["isError"] is False
    return result["structuredContent"]


def test_sse_endpoint_and_tools_list(tmp_path: Path) -> None:
    server = load_mcp_module()

    client = TestClient(server.create_app(xmuse_root=tmp_path / "xmuse"))

    sse = client.get("/sse")
    assert sse.status_code == 200
    assert sse.headers["content-type"].startswith("text/event-stream")
    assert "event: endpoint" in sse.text
    assert "/messages?session_id=" in sse.text

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "tools", "method": "tools/list"},
    )

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert names == {
        "list_lanes",
        "enqueue_lane",
        "get_status",
        "abort_lane",
        "get_error_knowledge",
        "get_logs",
    }


def test_list_lanes_and_enqueue_lane_update_feature_lanes(tmp_path: Path) -> None:
    server = load_mcp_module()

    xmuse_root = tmp_path / "xmuse"
    lanes_path = xmuse_root / "feature_lanes.json"
    write_json(
        lanes_path,
        {"lanes": [{"feature_id": "existing", "task_type": "execute", "status": "done"}]},
    )
    client = TestClient(server.create_app(xmuse_root=xmuse_root))

    assert mcp_call(client, "list_lanes") == read_json(lanes_path)

    created = mcp_call(
        client,
        "enqueue_lane",
        {
            "feature_id": "new-lane",
            "prompt": "Implement the new lane.",
            "capabilities": ["code", "test"],
        },
    )

    assert created["status"] == "queued"
    lanes = read_json(lanes_path)
    assert lanes["lanes"][-1] == {
        "feature_id": "new-lane",
        "task_type": "execute",
        "prompt": "Implement the new lane.",
        "capabilities": ["code", "test"],
        "status": "queued",
    }


def test_get_status_and_abort_lane_include_active_session(tmp_path: Path) -> None:
    server = load_mcp_module()

    xmuse_root = tmp_path / "xmuse"
    write_json(
        xmuse_root / "feature_lanes.json",
        {"lanes": [{"feature_id": "active-lane", "status": "running"}]},
    )
    write_json(
        xmuse_root / "active_sessions.json",
        {
            "sessions": {
                "active-lane": {
                    "session_id": "sess-1",
                    "pid": 999999,
                    "status": "running",
                }
            }
        },
    )
    client = TestClient(server.create_app(xmuse_root=xmuse_root))

    status = mcp_call(client, "get_status", {"feature_id": "active-lane"})
    assert status["lane"]["status"] == "running"
    assert status["active_session"]["session_id"] == "sess-1"

    aborted = mcp_call(client, "abort_lane", {"feature_id": "active-lane"})

    assert aborted["aborted"] is True
    assert aborted["lane"]["status"] == "aborted"
    assert aborted["active_session"]["status"] == "aborted"
    assert read_json(xmuse_root / "feature_lanes.json")["lanes"][0]["status"] == "aborted"
    sessions = read_json(xmuse_root / "active_sessions.json")["sessions"]
    assert sessions["active-lane"]["abort_requested"] is True


def test_error_knowledge_search_and_lane_logs(tmp_path: Path) -> None:
    server = load_mcp_module()

    xmuse_root = tmp_path / "xmuse"
    write_json(
        xmuse_root / "error_knowledge.json",
        {
            "entries": [
                {
                    "entry_id": "ek-1",
                    "pit": "ruff failed on unused import",
                    "root_cause": "stale import after refactor",
                    "fix": "remove the import",
                    "lesson": "run ruff before review",
                },
                {
                    "entry_id": "ek-2",
                    "pit": "timeout during public benchmark",
                    "lesson": "separate network-bound evals",
                },
            ]
        },
    )
    log_dir = xmuse_root / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "round-001-alpha.log").write_text("first log\n", encoding="utf-8")
    (log_dir / "round-002-alpha.log").write_text("second log\n", encoding="utf-8")
    (log_dir / "round-001-beta.log").write_text("other log\n", encoding="utf-8")
    client = TestClient(server.create_app(xmuse_root=xmuse_root))

    matches = mcp_call(client, "get_error_knowledge", {"query": "unused import ruff"})
    assert matches["matches"][0]["entry"]["entry_id"] == "ek-1"
    assert matches["matches"][0]["score"] > 0

    logs = mcp_call(client, "get_logs", {"feature_id": "alpha"})
    assert [entry["path"] for entry in logs["logs"]] == [
        "logs/round-001-alpha.log",
        "logs/round-002-alpha.log",
    ]
    assert "first log" in logs["combined"]
    assert "second log" in logs["combined"]
