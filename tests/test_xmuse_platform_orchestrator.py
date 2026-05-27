import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from xmuse_core.platform.orchestrator import PlatformOrchestrator
from xmuse_core.platform.agent_spawner import SpawnResult


@pytest.fixture
def setup(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "pending", "prompt": "fix bug",
         "worktree": str(tmp_path)},
    ]}))
    (tmp_path / "error_knowledge.json").write_text(json.dumps({"entries": []}))
    gates_dir = tmp_path / "logs" / "gates" / "lane-1"
    gates_dir.mkdir(parents=True)
    (gates_dir / "report.json").write_text(json.dumps({"passed": True}))
    (tmp_path / "xmuse" / "god_prompts").mkdir(parents=True)
    (tmp_path / "xmuse" / "god_prompts" / "execution_god.md").write_text("exec")
    (tmp_path / "xmuse" / "god_prompts" / "review_god.md").write_text("review")
    return tmp_path, lanes_path


@pytest.mark.asyncio
async def test_dispatch_lane_transitions_to_dispatched(setup):
    tmp_path, lanes_path = setup
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    mock_result = SpawnResult(exit_code=0, stdout="", stderr="")
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=mock_result):
        with patch.object(orch, "_run_gate", new_callable=AsyncMock,
                          return_value=True):
            await orch.dispatch_lane("lane-1")
            import asyncio
            await asyncio.sleep(0.1)

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] in ("dispatched", "executed", "gated")


@pytest.mark.asyncio
async def test_execution_god_timeout_marks_exec_failed(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    timeout_result = SpawnResult(exit_code=-1, stdout="", stderr="timeout",
                                 timed_out=True)
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=timeout_result):
        await orch._run_execution_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "exec_failed"


@pytest.mark.asyncio
async def test_on_lane_reviewed_transitions_to_merged(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    await orch.on_lane_reviewed("lane-1")
    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "merged"


@pytest.mark.asyncio
async def test_mcp_status_change_callback(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    result = orch._tools.call("update_lane_status", {
        "lane_id": "lane-1", "status": "reviewed",
    })
    assert result["status"] == "reviewed"
