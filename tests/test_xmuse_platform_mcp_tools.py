import json
import pytest
from pathlib import Path
from xmuse_core.platform.mcp_tools import McpToolHandler
from xmuse_core.platform.state_machine import LaneStateMachine


@pytest.fixture
def setup(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix bug",
         "worktree": str(tmp_path / "wt")},
    ]}))
    wt = tmp_path / "wt"
    wt.mkdir()
    gates_dir = tmp_path / "logs" / "gates" / "lane-1"
    gates_dir.mkdir(parents=True)
    (gates_dir / "report.json").write_text(json.dumps({
        "passed": True, "feature_id": "lane-1", "profile_ids": ["linter-only"],
    }))
    ek_path = tmp_path / "error_knowledge.json"
    ek_path.write_text(json.dumps({"entries": [
        {"id": "ek-1", "pit": "mypy arg-type", "root_cause": "wrong type",
         "scope": "type errors"},
    ]}))
    sm = LaneStateMachine(lanes_path)
    status_changes = []
    handler = McpToolHandler(
        state_machine=sm,
        xmuse_root=tmp_path,
        on_status_change=lambda lid, s: status_changes.append((lid, s)),
    )
    return handler, sm, tmp_path, status_changes


def test_get_lane(setup):
    handler, _, _, _ = setup
    result = handler.call("get_lane", {"lane_id": "lane-1"})
    assert result["feature_id"] == "lane-1"
    assert result["status"] == "gated"


def test_get_gate_report(setup):
    handler, _, _, _ = setup
    result = handler.call("get_gate_report", {"lane_id": "lane-1"})
    assert result["passed"] is True


def test_query_knowledge(setup):
    handler, _, _, _ = setup
    result = handler.call("query_knowledge", {"query": "mypy type", "top_k": 3})
    assert len(result["matches"]) == 1
    assert result["matches"][0]["entry"]["id"] == "ek-1"


def test_update_lane_status_valid(setup):
    handler, sm, _, status_changes = setup
    result = handler.call("update_lane_status", {
        "lane_id": "lane-1", "status": "reviewed",
    })
    assert result["status"] == "reviewed"
    assert sm.get_lane("lane-1")["status"] == "reviewed"
    assert status_changes == [("lane-1", "reviewed")]


def test_update_lane_status_invalid(setup):
    handler, _, _, _ = setup
    result = handler.call("update_lane_status", {
        "lane_id": "lane-1", "status": "merged",
    })
    assert "error" in result


def test_unknown_tool(setup):
    handler, _, _, _ = setup
    result = handler.call("nonexistent_tool", {})
    assert "error" in result
