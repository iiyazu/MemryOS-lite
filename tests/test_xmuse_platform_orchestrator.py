import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from xmuse_core.gates.models import GateReport
from xmuse_core.platform.agent_spawner import SpawnResult
from xmuse_core.platform.orchestrator import PlatformOrchestrator
from xmuse_core.platform.state_validation import StateValidationError


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
            await asyncio.sleep(0.1)

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] in ("dispatched", "executed", "gated", "gate_failed")


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
    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
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


def test_orchestrator_default_mcp_port_matches_server(setup):
    tmp_path, lanes_path = setup
    orch = PlatformOrchestrator(lanes_path=lanes_path, xmuse_root=tmp_path)

    assert orch._spawner._mcp_port == 8100


def test_orchestrator_defaults_to_codex_runtime(setup, monkeypatch):
    tmp_path, lanes_path = setup
    monkeypatch.delenv("XMUSE_GOD_RUNTIME", raising=False)
    orch = PlatformOrchestrator(lanes_path=lanes_path, xmuse_root=tmp_path)

    assert orch._execution_god.runtime == "codex"
    assert orch._review_god.runtime == "codex"


def test_orchestrator_god_runtime_arg_overrides_env(setup, monkeypatch):
    tmp_path, lanes_path = setup
    monkeypatch.setenv("XMUSE_GOD_RUNTIME", "codex")
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, god_runtime="claude",
    )

    assert orch._execution_god.runtime == "claude"
    assert orch._review_god.runtime == "claude"


def test_orchestrator_god_runtime_env_picks_claude(setup, monkeypatch):
    tmp_path, lanes_path = setup
    monkeypatch.setenv("XMUSE_GOD_RUNTIME", "claude")
    orch = PlatformOrchestrator(lanes_path=lanes_path, xmuse_root=tmp_path)

    assert orch._execution_god.runtime == "claude"
    assert orch._review_god.runtime == "claude"


def test_orchestrator_rejects_unknown_runtime(setup, monkeypatch):
    tmp_path, lanes_path = setup
    monkeypatch.delenv("XMUSE_GOD_RUNTIME", raising=False)
    with pytest.raises(ValueError):
        PlatformOrchestrator(
            lanes_path=lanes_path, xmuse_root=tmp_path, god_runtime="grok",
        )


def test_orchestrator_mixed_runtime_round_robins_per_lane(setup, monkeypatch):
    """In mixed mode, _pick_execution_god alternates between codex and claude
    for *new* lanes, and respects an existing god_runtime metadata value when
    revisiting a lane (so retries keep the same provider).
    """
    tmp_path, lanes_path = setup
    monkeypatch.delenv("XMUSE_GOD_RUNTIME", raising=False)
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-a", "status": "pending", "prompt": "x",
         "worktree": str(tmp_path)},
        {"feature_id": "lane-b", "status": "pending", "prompt": "x",
         "worktree": str(tmp_path)},
        {"feature_id": "lane-c", "status": "dispatched", "prompt": "x",
         "worktree": str(tmp_path), "god_runtime": "claude"},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, god_runtime="mixed",
    )

    assert orch._runtime_mode == "mixed"
    assert {g.runtime for g in orch._execution_gods} == {"codex", "claude"}

    # Two fresh lanes round-robin
    first = orch._pick_execution_god("lane-a").runtime
    second = orch._pick_execution_god("lane-b").runtime
    assert {first, second} == {"codex", "claude"}

    # An already-dispatched lane keeps its recorded runtime
    pinned = orch._pick_execution_god("lane-c").runtime
    assert pinned == "claude"


def test_orchestrator_mixed_review_god_matches_lane_runtime(setup, monkeypatch):
    tmp_path, lanes_path = setup
    monkeypatch.delenv("XMUSE_GOD_RUNTIME", raising=False)
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-claude", "status": "gated", "prompt": "x",
         "worktree": str(tmp_path), "god_runtime": "claude"},
        {"feature_id": "lane-codex", "status": "gated", "prompt": "x",
         "worktree": str(tmp_path), "god_runtime": "codex"},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, god_runtime="mixed",
    )

    assert orch._pick_review_god("lane-claude").runtime == "claude"
    assert orch._pick_review_god("lane-codex").runtime == "codex"


@pytest.mark.asyncio
async def test_review_god_does_not_retransition_already_gated_lane(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    review_result = SpawnResult(exit_code=0, stdout="", stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_no_verdict"


@pytest.mark.asyncio
async def test_mcp_reviewed_status_triggers_auto_merge(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        result = orch._tools.call("update_lane_status", {
            "lane_id": "lane-1", "status": "reviewed",
        })
        await asyncio.sleep(0.1)

    assert result["status"] == "reviewed"
    assert orch._sm.get_lane("lane-1")["status"] == "merged"


@pytest.mark.asyncio
async def test_reconcile_external_reviewed_status_triggers_auto_merge(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        await orch.reconcile_status_changes()

    assert orch._sm.get_lane("lane-1")["status"] == "merged"


@pytest.mark.asyncio
async def test_reconcile_external_executed_status_runs_gate_and_review(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "executed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_gate", new_callable=AsyncMock, return_value=True) as gate:
        with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
            await orch.reconcile_status_changes()

    assert orch._sm.get_lane("lane-1")["status"] == "gated"
    gate.assert_awaited_once_with("lane-1")
    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_mcp_executed_status_triggers_gate_and_review(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_gate", new_callable=AsyncMock, return_value=True) as gate:
        with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
            result = orch._tools.call("update_lane_status", {
                "lane_id": "lane-1", "status": "executed",
            })
            await asyncio.sleep(0.1)

    assert result["status"] == "executed"
    assert orch._sm.get_lane("lane-1")["status"] == "gated"
    gate.assert_awaited_once_with("lane-1")
    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_concurrent_executed_handlers_do_not_double_transition(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "executed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_gate", new_callable=AsyncMock,
                      return_value=True) as gate:
        with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
            await asyncio.gather(
                orch._on_lane_executed("lane-1"),
                orch._on_lane_executed("lane-1"),
            )

    assert orch._sm.get_lane("lane-1")["status"] == "gated"
    assert gate.await_count >= 1
    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_reconcile_recovers_gated_lane_without_review_start(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path), "gate_passed": True},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_gate_failure_marks_lane_gate_failed_and_skips_review(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "executed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_gate", new_callable=AsyncMock, return_value=False):
        with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
            await orch._on_lane_executed("lane-1")

    assert orch._sm.get_lane("lane-1")["status"] == "gate_failed"
    review.assert_not_called()


@pytest.mark.asyncio
async def test_gate_failure_transition_is_rejected_without_failure_reason(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "executed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with pytest.raises(StateValidationError, match="failure_reason"):
        orch._sm.transition("lane-1", "gate_failed")

    assert orch._sm.get_lane("lane-1")["status"] == "executed"


@pytest.mark.asyncio
async def test_run_gate_uses_plural_gate_profiles(setup):
    tmp_path, lanes_path = setup
    (tmp_path / "gate_profiles.json").write_text(json.dumps({
        "schema_version": 1,
        "defaults": {
            "full_gate_profile": "strict-product",
            "full_gate_interval": 20,
            "unknown_diff_policy": "strict-product",
            "unclassified_test_policy": "fail",
        },
        "command_catalog": {
            "noop": {
                "argv": ["true"],
                "cwd": ".",
                "timeout_s": 0,
                "allow_extra_args": False,
            }
        },
        "profiles": {
            "strict-product": {
                "description": "strict",
                "blocking": True,
                "env": {},
                "commands": [{"command": "noop", "args": []}],
                "diff_selectors": ["src/memoryos_lite/**"],
                "test_files": ["tests/test_xmuse_platform_orchestrator.py"],
                "test_nodeids": [],
                "test_markers": [],
                "mixed_test_files": [],
            },
            "xmuse-core": {
                "description": "xmuse",
                "blocking": True,
                "env": {},
                "commands": [{"command": "noop", "args": []}],
                "diff_selectors": ["src/xmuse_core/**"],
                "test_files": ["tests/test_xmuse_platform_orchestrator.py"],
                "test_nodeids": [],
                "test_markers": [],
                "mixed_test_files": [],
            },
        },
    }))
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "executed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_profiles": ["xmuse-core"],
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    async def fake_run(plan):
        assert plan.profiles == ["xmuse-core"]
        assert plan.warnings == [
            "explicit gate_profiles selected; full dirty-worktree "
            "coverage is recorded but not used to reject this lane"
        ]
        return GateReport(
            feature_id=plan.feature_id,
            passed=True,
            blocking_passed=True,
            nonblocking_failures=[],
            profile_ids=plan.profiles,
            resolution_reasons=plan.resolution_reasons,
            command_results=[],
            artifact_dir=tmp_path / "logs" / "gates" / "lane-1",
            warnings=[],
        )

    with patch.object(
        orch,
        "_get_changed_paths",
        return_value=[
            "src/xmuse_core/platform/orchestrator.py",
            "src/memoryos_lite/config.py",
        ],
    ):
        with patch("xmuse_core.gates.runner.GateRunner.run", side_effect=fake_run):
            assert await orch._run_gate("lane-1") is True


@pytest.mark.asyncio
async def test_reconcile_recovers_review_timeout_by_rerunning_review(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_timeout",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gated"
    assert lane["review_retry_count"] == 1
    assert lane["review_recovered_from"] == "review_timeout"
    assert "failure_reason" not in lane
    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_reconcile_recovers_review_no_verdict_by_rerunning_review(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_no_verdict",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gated"
    assert lane["review_retry_count"] == 1
    assert lane["review_recovered_from"] == "review_no_verdict"
    assert "failure_reason" not in lane
    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_non_zero_exit_marks_gate_failed(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    review_result = SpawnResult(exit_code=1, stdout="", stderr="boom")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_non_zero_exit"


@pytest.mark.asyncio
async def test_review_god_usage_limit_marks_infra_unavailable_with_backoff(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path), "gate_passed": True},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=1,
        stdout="",
        stderr="ERROR: You've hit your usage limit. Try again later.",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_infra_unavailable"
    assert lane["review_infra_reason"] == "usage_limit"
    assert lane["review_retry_after_at"] > lane["review_started_at"]


@pytest.mark.asyncio
async def test_reconcile_waits_for_review_infra_backoff(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_infra_unavailable",
            "review_retry_after_at": 9999999999,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    assert orch._sm.get_lane("lane-1")["status"] == "gate_failed"
    review.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_recovers_review_infra_failure_after_backoff(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_infra_unavailable",
            "review_retry_after_at": 1,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gated"
    assert lane["review_retry_count"] == 1
    assert lane["review_recovered_from"] == "review_infra_unavailable"
    assert "failure_reason" not in lane
    review.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_approves_when_mcp_status_missing(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
        require_final_action_approval=True,
    )
    review_result = SpawnResult(exit_code=0, stdout="No findings. Approved.", stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "awaiting_final_action"
    assert lane["review_fallback"] == "stdout"
    assert lane["review_fallback_reason"] in {
        "approval_marker",
        "positive_no_findings",
    }
    assert lane["review_decision"] == "merge"


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_approves_none_findings_with_negated_blocking_issue(
    setup,
):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
        require_final_action_approval=True,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout=(
            "**Findings**\n\n"
            "None. I did not find a blocking issue in the current lane state."
        ),
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "awaiting_final_action"
    assert lane["review_fallback"] == "stdout"
    assert lane["review_fallback_reason"] == "positive_none"
    assert lane["review_decision"] == "merge"


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_approves_common_empty_findings_prose(
    setup,
):
    tmp_path, lanes_path = setup
    for stdout in (
        "**Findings**\n\nNone. I did not find any issues.",
        "**Findings**\n\nNo issues were found.",
    ):
        lanes_path.write_text(json.dumps({"lanes": [
            {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
             "worktree": str(tmp_path)},
        ]}))
        orch = PlatformOrchestrator(
            lanes_path=lanes_path,
            xmuse_root=tmp_path,
            mcp_port=9999,
            require_final_action_approval=True,
        )
        review_result = SpawnResult(exit_code=0, stdout=stdout, stderr="")

        with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                          return_value=review_result):
            await orch._run_review_god("lane-1")

        lane = orch._sm.get_lane("lane-1")
        assert lane["status"] == "awaiting_final_action"
        assert lane["review_fallback"] == "stdout"
        assert lane["review_decision"] == "merge"


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_blocking_findings(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(exit_code=0, stdout="**Findings**\n1. High: bug", stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_fallback"] == "stdout"
    assert lane["review_fallback_reason"] == "severity_finding"
    assert lane["review_decision"] == "rework"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_findings_even_with_approved_word(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: approved review can still stall",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_markdown_heading_findings(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="## Findings\n- Missing coverage. No findings in tests.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] in {"findings_section", "missing_coverage"}
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_no_findings_prefix_inside_findings(
    setup,
):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="## Findings\n- No findings in tests; missing coverage.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] in {"findings_section", "missing_coverage"}
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_no_issues_prefix_inside_findings(
    setup,
):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n\nNo issues were found in tests; missing coverage remains.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] in {
        "findings_section",
        "unresolved_finding",
    }
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_global_no_issues_prefix_with_issue(
    setup,
):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="No issues were found in tests; missing coverage remains.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] == "unresolved_finding"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_common_rejection_prose(setup):
    tmp_path, lanes_path = setup
    cases = (
        ("I would not merge this yet; tests are absent.", "explicit_rejection"),
        ("This is not ready to merge; validation is incomplete.", "explicit_rejection"),
        ("Needs rework before merge.", "needs_rework"),
        ("The change is not acceptable for merge.", "explicit_rejection"),
    )
    for stdout, expected_reason in cases:
        lanes_path.write_text(json.dumps({"lanes": [
            {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
             "worktree": str(tmp_path)},
        ]}))
        orch = PlatformOrchestrator(
            lanes_path=lanes_path,
            xmuse_root=tmp_path,
            mcp_port=9999,
        )
        review_result = SpawnResult(exit_code=0, stdout=stdout, stderr="")

        with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                          return_value=review_result):
            with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
                await orch._run_review_god("lane-1")

        lane = orch._sm.get_lane("lane-1")
        assert lane["status"] == "reworking"
        assert lane["review_decision"] == "rework"
        assert lane["review_fallback_reason"] == expected_reason
        dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_reproduced_findings(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout=(
            "No findings claimed by the fallback summary, but the rework "
            "finding still reproduces in the live code."
        ),
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] == "reproduced_finding"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_explicit_not_approved(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n- Missing coverage; not approved.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] == "explicit_rejection"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_cannot_approve(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="Cannot approve: missing tests.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] == "explicit_rejection"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_do_not_merge(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="Do not merge: missing tests.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] == "explicit_rejection"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_reject_marker(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="Reject: missing tests.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] == "explicit_rejection"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_findings_section_despite_no_findings(
    setup,
):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n- Missing coverage. No findings in tests.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"
    assert lane["review_fallback_reason"] in {"findings_section", "missing_coverage"}
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_empty_stdout_marks_review_no_verdict(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path), "gate_passed": True},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(exit_code=0, stdout="", stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_no_verdict"


@pytest.mark.asyncio
async def test_dispatch_lane_waits_for_execution_lifecycle(setup):
    tmp_path, lanes_path = setup
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    gate = asyncio.Event()

    async def wait_for_gate(_: str) -> None:
        await gate.wait()

    with patch.object(orch, "_run_execution_god", side_effect=wait_for_gate):
        task = asyncio.create_task(orch.dispatch_lane("lane-1"))
        await asyncio.sleep(0)

        assert not task.done()
        gate.set()
        await task


@pytest.mark.asyncio
async def test_reviewed_lane_enters_final_action_hold_when_enabled(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
        require_final_action_approval=True,
    )

    await orch.reconcile_status_changes()

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "awaiting_final_action"
    assert lane["final_action_hold_id"]
    holds = orch._final_action_store.list_actions()
    assert len(holds) == 1
    assert holds[0].action == "merge"


@pytest.mark.asyncio
async def test_reviewed_lane_without_branch_terminalizes_as_merged(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )

    await orch.on_lane_reviewed("lane-1")

    assert orch._sm.get_lane("lane-1")["status"] == "merged"


@pytest.mark.asyncio
async def test_reconcile_status_changes_projects_newly_ready_dependents_for_merged_lane(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "conversation_id": "conv-1",
            "resolution_id": "res-1",
            "graph_id": "graph-1",
            "graph_version": 1,
        },
    ]}))
    graph_dir = tmp_path / "lane_graphs"
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph-1.json").write_text(json.dumps({
        "id": "graph-1",
        "conversation_id": "conv-1",
        "resolution_id": "res-1",
        "version": 1,
        "status": "planned",
        "lanes": [
            {
                "feature_id": "lane-1",
                "prompt": "build chat",
                "priority": 90,
                "depends_on": [],
            },
            {
                "feature_id": "lane-2",
                "prompt": "build dashboard",
                "priority": 60,
                "depends_on": ["lane-1"],
            },
        ],
    }))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    await orch.reconcile_status_changes()
    await orch.reconcile_status_changes()

    lanes = json.loads(lanes_path.read_text(encoding="utf-8"))["lanes"]
    assert [lane["feature_id"] for lane in lanes] == ["lane-1", "lane-2"]
    assert lanes[1]["status"] == "pending"


@pytest.mark.asyncio
async def test_reproject_dependents_facade_delegates_to_projection_module(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch(
        "xmuse_core.platform.orchestrator.reproject_dependents_if_needed",
        new_callable=AsyncMock,
    ) as reproject:
        await orch._reproject_dependents_if_needed("lane-1")

    reproject.assert_awaited_once_with(
        "lane-1",
        sm=orch._sm,
        graph_store=orch._graph_store,
    )


# ---------------------------------------------------------------------------
# clarification_recovery: stdout fallback unknown-text safety (evbundle_0a8afa9f)
# Finding: High — stdout fallback defaulted unknown review text to merge.
# Fix: unknown/unclassifiable stdout now rejects with "unknown_review_text".
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_ambiguous_prose(setup):
    """Ambiguous review prose with no positive/negative signals must reject."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    # Ambiguous text: no approval marker, no rejection marker, no findings section.
    review_result = SpawnResult(
        exit_code=0,
        stdout="The implementation looks reasonable.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    # on_lane_rejected transitions to reworking and re-dispatches (retry_count < 2)
    assert lane["status"] == "reworking"
    assert lane["review_fallback"] == "stdout"
    assert lane["review_fallback_reason"] == "unknown_review_text"
    assert lane["review_decision"] == "rework"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_generic_reviewed_prose(setup):
    """'I reviewed the changes' with no verdict signals must reject, not merge."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="I reviewed the changes.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_fallback_reason"] == "unknown_review_text"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_rejects_implementation_complete_prose(setup):
    """'Implementation complete.' with no verdict signals must reject, not merge."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="Implementation complete.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock) as dispatch:
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_fallback_reason"] == "unknown_review_text"
    dispatch.assert_awaited_once_with("lane-1")


@pytest.mark.asyncio
async def test_review_god_stdout_fallback_still_approves_explicit_approval_marker(setup):
    """Explicit 'approved' marker must still resolve to merge after the fix."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
        require_final_action_approval=True,
    )
    review_result = SpawnResult(
        exit_code=0,
        stdout="Approved. No findings.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "awaiting_final_action"
    assert lane["review_decision"] == "merge"
    assert lane["review_fallback_reason"] == "approval_marker"


@pytest.mark.asyncio
async def test_infer_review_fallback_unknown_text_returns_rejected_tuple(setup):
    """Unit-level: _infer_review_fallback returns rejected for unclassifiable text."""
    tmp_path, lanes_path = setup
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    ambiguous_cases = [
        "The implementation looks reasonable.",
        "I reviewed the changes.",
        "The code has been examined.",
        "Changes look okay to me.",
        "Implementation complete.",
        "Looks good overall.",
    ]
    for text in ambiguous_cases:
        decision, _summary, reason = orch._infer_review_fallback(text)
        assert decision == "rejected", (
            f"Expected 'rejected' for ambiguous text {text!r}, got {decision!r}"
        )
        assert reason == "unknown_review_text", (
            f"Expected 'unknown_review_text' for {text!r}, got {reason!r}"
        )


# ---------------------------------------------------------------------------
# Review plane integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_review_god_opens_review_task_and_stamps_lane(setup):
    """_run_review_god opens a ReviewTask and stamps review_task_id on the lane."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    review_result = SpawnResult(exit_code=0, stdout="Approved. No findings.", stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert "review_task_id" in lane
    task_id = lane["review_task_id"]
    assert task_id.startswith("rtask_")

    # The task must be persisted in the review plane store.
    task = orch._review_plane.store.get_task(task_id)
    assert task.lane_id == "lane-1"


@pytest.mark.asyncio
async def test_on_lane_reviewed_ingests_verdict_through_review_plane(setup):
    """on_lane_reviewed persists the verdict through ReviewPlaneController."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "reviewed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "review_decision": "merge",
            "review_summary": "No findings.",
            "review_verdict_id": "verdict-lane-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Open a task first so ingest_verdict has a task to link to.
    task = orch._review_plane.open_review_task("lane-1")
    orch._sm.update_metadata("lane-1", {"review_task_id": task.task_id})

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        await orch.on_lane_reviewed("lane-1")

    # Verdict must be persisted in the review plane store.
    verdict = orch._review_plane.store.get_verdict("verdict-lane-1")
    assert verdict.lane_id == "lane-1"
    assert verdict.decision.value == "merge"
    assert verdict.task_id == task.task_id


@pytest.mark.asyncio
async def test_verdict_lineage_for_lane_returns_chain_after_merge(setup):
    """verdict_lineage_for_lane returns the task→verdict chain after a merge."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "reviewed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "review_decision": "merge",
            "review_summary": "No findings.",
            "review_verdict_id": "verdict-lineage-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    task = orch._review_plane.open_review_task("lane-1")
    orch._sm.update_metadata("lane-1", {"review_task_id": task.task_id})

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        await orch.on_lane_reviewed("lane-1")

    lineage = orch.verdict_lineage_for_lane("lane-1")

    assert len(lineage) == 1
    assert lineage[0]["task"]["task_id"] == task.task_id
    assert lineage[0]["verdict"] is not None
    assert lineage[0]["verdict"]["id"] == "verdict-lineage-1"


@pytest.mark.asyncio
async def test_has_verdict_lineage_is_true_after_merge(setup):
    """has_verdict_lineage returns True after a lane is merged through the review plane."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "reviewed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "review_decision": "merge",
            "review_summary": "No findings.",
            "review_verdict_id": "verdict-has-lineage-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    task = orch._review_plane.open_review_task("lane-1")
    orch._sm.update_metadata("lane-1", {"review_task_id": task.task_id})

    assert orch.has_verdict_lineage("lane-1") is False

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        await orch.on_lane_reviewed("lane-1")

    assert orch.has_verdict_lineage("lane-1") is True


def test_has_verdict_lineage_is_false_for_unknown_lane(setup):
    """has_verdict_lineage returns False for a lane with no review plane record."""
    tmp_path, lanes_path = setup
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    assert orch.has_verdict_lineage("lane-unknown") is False


@pytest.mark.asyncio
async def test_run_review_god_captures_gate_report_ref_in_task(setup):
    """_run_review_god captures the gate report ref in the ReviewTask when available."""
    tmp_path, lanes_path = setup
    # The setup fixture already creates logs/gates/lane-1/report.json.
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    review_result = SpawnResult(exit_code=0, stdout="Approved. No findings.", stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    task_id = lane.get("review_task_id")
    assert task_id is not None

    task = orch._review_plane.store.get_task(task_id)
    assert task.gate_report_ref is not None
    assert "lane-1" in task.gate_report_ref
    assert "report.json" in task.gate_report_ref


@pytest.mark.asyncio
async def test_review_plane_error_does_not_break_execution_path(setup):
    """A review plane failure must not prevent the lane from transitioning normally."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "reviewed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "review_decision": "merge",
            "review_summary": "No findings.",
            "review_verdict_id": "verdict-error-1",
            # Deliberately omit review_task_id so ingest_verdict raises KeyError.
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        # Should not raise even though there is no review_task_id.
        await orch.on_lane_reviewed("lane-1")

    assert orch._sm.get_lane("lane-1")["status"] == "merged"


@pytest.mark.asyncio
async def test_rework_verdict_creates_review_task_and_verdict_lineage(setup):
    """A rework verdict via _run_review_god is persisted in the review plane."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gated",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Simulate review GOD returning a rework verdict via stdout fallback.
    review_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: core behavior is incorrect.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reworking"
    assert lane["review_decision"] == "rework"

    # The review task must have been opened and stamped on the lane.
    task_id = lane.get("review_task_id")
    assert task_id is not None
    task = orch._review_plane.store.get_task(task_id)
    assert task.lane_id == "lane-1"


# ---------------------------------------------------------------------------
# Run-level terminal aggregation (review_plane track, evbundle_648180f3cce14c129fad244774d94f80)
# Spec: blueprint-anchored self-evolution, "Run Terminal Aggregation" section.
# Hard Rule #10: run terminalization must be computed through an explicit
# aggregation contract rather than guessed from individual lane states.
# ---------------------------------------------------------------------------


def test_aggregate_run_terminal_status_merged_when_all_lanes_merged(setup):
    """All lanes merged → run status is 'merged'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
        {
            "feature_id": "lane-2",
            "status": "merged",
            "prompt": "build dashboard",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    assert result.graph_id == "graph-1"
    assert result.status == "merged"
    assert result.open_lane_lineages == []
    assert result.failed_lineages == []
    assert result.open_final_action_holds == []


def test_aggregate_run_terminal_status_in_progress_when_lane_pending(setup):
    """A pending lane keeps the run in 'in_progress'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
        {
            "feature_id": "lane-2",
            "status": "pending",
            "prompt": "build dashboard",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    assert result.status == "in_progress"
    assert "lane-2" in result.open_lane_lineages
    assert result.failed_lineages == []


def test_aggregate_run_terminal_status_terminated_when_lane_failed(setup):
    """A failed lane with all others merged → run status is 'terminated'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
        {
            "feature_id": "lane-2",
            "status": "failed",
            "prompt": "build dashboard",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    assert result.status == "terminated"
    assert "lane-2" in result.failed_lineages
    assert result.open_lane_lineages == []


def test_aggregate_run_terminal_status_terminated_for_exec_failed(setup):
    """exec_failed lane with all others merged → run status is 'terminated'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
        {
            "feature_id": "lane-2",
            "status": "exec_failed",
            "prompt": "build dashboard",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    assert result.status == "terminated"
    assert "lane-2" in result.failed_lineages


def test_aggregate_run_terminal_status_blocked_for_input_when_hold_pending(setup):
    """All lanes merged but a pending final-action hold → 'blocked_for_input'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "awaiting_final_action",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    # Create a pending hold for lane-1.
    orch._final_action_store.create_hold(
        lane_id="lane-1",
        verdict_id="verdict-1",
        action="merge",
        target_status="reviewed",
        summary="awaiting approval",
    )
    # Manually move lane-1 to a closed state so the only blocker is the hold.
    # We simulate: lane is in awaiting_final_action (open), so in_progress first.
    # To test blocked_for_input we need all lineages closed but hold pending.
    # Patch the lane to a non-open status that is also not in _CLOSED_OK/_CLOSED_FAIL.
    # The spec says blocked_for_input = all lineages closed + open hold.
    # awaiting_final_action is in _OPEN, so the run is in_progress.
    # We test the pure blocked_for_input path by using a lane with no open lineages.
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))

    result = orch.aggregate_run_terminal_status("graph-1")

    assert result.status == "blocked_for_input"
    assert len(result.open_final_action_holds) == 1


def test_aggregate_run_terminal_status_includes_patch_forward_descendants(setup):
    """Patch-forward descendants are included in the lineage closure."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "failure_reason": "patch_forward_requested",
        },
        {
            "feature_id": "lane-1-patch-forward",
            "status": "pending",
            "prompt": "patch forward",
            "worktree": str(tmp_path),
            "source_lane_id": "lane-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    # The patch-forward descendant is still pending → in_progress.
    assert result.status == "in_progress"
    assert "lane-1-patch-forward" in result.open_lane_lineages


def test_aggregate_run_terminal_status_patch_forward_merged_closes_lineage(setup):
    """When the patch-forward descendant merges, the lineage is fully closed."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "failure_reason": "patch_forward_requested",
        },
        {
            "feature_id": "lane-1-patch-forward",
            "status": "merged",
            "prompt": "patch forward",
            "worktree": str(tmp_path),
            "source_lane_id": "lane-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    # lane-1 is failed (terminated lineage), patch-forward is merged (closed ok).
    # All lineages closed, at least one via fail → terminated.
    assert result.status == "terminated"
    assert "lane-1" in result.failed_lineages
    assert result.open_lane_lineages == []


def test_aggregate_run_terminal_status_empty_graph_returns_merged(setup):
    """A graph with no lanes is considered merged (vacuously complete)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": []}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-empty")

    assert result.status == "merged"
    assert result.open_lane_lineages == []
    assert result.failed_lineages == []


def test_aggregate_run_terminal_status_basis_records_aggregation_inputs(setup):
    """The basis field records the key aggregation inputs for audit."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    assert "graph_id=graph-1" in result.basis
    assert "total_lane_lineages=1" in result.basis
    assert "open=0" in result.basis
    assert "failed=0" in result.basis


def test_aggregate_run_terminal_status_ignores_lanes_from_other_graphs(setup):
    """Lanes from a different graph_id do not affect the aggregation."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
        {
            "feature_id": "lane-other",
            "status": "pending",
            "prompt": "other graph work",
            "worktree": str(tmp_path),
            "graph_id": "graph-2",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    # graph-2's pending lane must not affect graph-1's aggregation.
    assert result.status == "merged"
    assert "lane-other" not in result.open_lane_lineages


def test_aggregate_run_terminal_status_in_progress_for_dispatched_lane(setup):
    """A dispatched lane keeps the run in 'in_progress'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "dispatched",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    result = orch.aggregate_run_terminal_status("graph-1")

    assert result.status == "in_progress"
    assert "lane-1" in result.open_lane_lineages


# ---------------------------------------------------------------------------
# StructuredEvidenceBundle assembly
# (review_plane track, self-evolution-review_plane-res_e0fefabbce6c449799c942bfca91061a-graph-v1)
# Spec: blueprint-anchored self-evolution, "Evidence Model" section.
# Testing Expectations #1-2: terminal run outcome can produce a structured
# evidence bundle; bundles expose curated summaries plus full primary refs
# under a versioned selection policy.
# ---------------------------------------------------------------------------


def test_assemble_evidence_bundle_from_merged_run(setup):
    """A merged run produces an evidence bundle with run_terminal_status 'merged'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "resolution_id": "res-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle("graph-1")

    assert bundle.source_run_id == "graph-1"
    assert bundle.run_terminal_status == "merged"
    assert bundle.source_resolution_id == "res-1"
    assert bundle.bundle_id.startswith("evbundle_")
    assert bundle.created_at


def test_assemble_evidence_bundle_from_terminated_run(setup):
    """A terminated run produces a bundle with run_terminal_status 'terminated'."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
        {
            "feature_id": "lane-2",
            "status": "failed",
            "prompt": "build dashboard",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "failure_reason": "non_zero_exit",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle("graph-1")

    assert bundle.run_terminal_status == "terminated"
    assert bundle.source_run_id == "graph-1"


def test_evidence_bundle_includes_negative_signal_refs_for_failed_lanes(setup):
    """Evidence bundle records negative signal refs for every failed lane."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "failure_reason": "merge_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle("graph-1")

    assert any("lane-1" in ref for ref in bundle.signal_refs)
    assert any("merge_failed" in ref for ref in bundle.signal_refs)
    # primary_refs must include the negative signal entry
    neg_primaries = [r for r in bundle.primary_refs if r.get("type") == "negative_signal"]
    assert len(neg_primaries) == 1
    assert neg_primaries[0]["lane_id"] == "lane-1"
    assert neg_primaries[0]["failure_reason"] == "merge_failed"


def test_evidence_bundle_includes_verdict_refs_and_primary_refs(setup):
    """Evidence bundle includes verdict refs and full primary refs for each verdict."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "review_decision": "merge",
            "review_summary": "No findings.",
            "review_verdict_id": "verdict-ev-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Open a task and ingest a verdict so the lineage exists.
    task = orch._review_plane.open_review_task("lane-1")
    orch._sm.update_metadata("lane-1", {"review_task_id": task.task_id})
    from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict
    verdict = ReviewVerdict(
        id="verdict-ev-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="No findings.",
        task_id=task.task_id,
    )
    orch._review_plane.store.save_verdict(verdict)
    # Update task to verdict_emitted state.
    task.verdict_id = "verdict-ev-1"
    from xmuse_core.structuring.models import ReviewTaskStatus
    task.status = ReviewTaskStatus.VERDICT_EMITTED
    orch._review_plane.store.save_task(task)

    bundle = orch.assemble_evidence_bundle("graph-1")

    assert "verdict-ev-1" in bundle.verdict_refs
    verdict_primaries = [r for r in bundle.primary_refs if r.get("type") == "review_verdict"]
    assert len(verdict_primaries) == 1
    assert verdict_primaries[0]["id"] == "verdict-ev-1"
    assert verdict_primaries[0]["decision"] == "merge"


def test_evidence_bundle_includes_gate_report_refs(setup):
    """Evidence bundle includes gate report refs from review tasks."""
    tmp_path, lanes_path = setup
    # setup fixture already creates logs/gates/lane-1/report.json
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Open a task with a gate_report_ref.
    task = orch._review_plane.open_review_task(
        "lane-1", gate_report_ref="logs/gates/lane-1/report.json"
    )
    orch._sm.update_metadata("lane-1", {"review_task_id": task.task_id})

    bundle = orch.assemble_evidence_bundle("graph-1")

    assert "logs/gates/lane-1/report.json" in bundle.gate_report_refs
    task_primaries = [r for r in bundle.primary_refs if r.get("type") == "review_task"]
    assert any(r.get("gate_report_ref") == "logs/gates/lane-1/report.json" for r in task_primaries)


def test_evidence_bundle_includes_lineage_refs_for_patch_forward(setup):
    """Evidence bundle includes lineage refs for patch-forward descendants."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "build chat",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "failure_reason": "patch_forward_requested",
        },
        {
            "feature_id": "lane-1-patch",
            "status": "merged",
            "prompt": "patch forward",
            "worktree": str(tmp_path),
            "source_lane_id": "lane-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle("graph-1")

    assert any("lane-1-patch" in ref for ref in bundle.lineage_refs)
    lineage_primaries = [r for r in bundle.primary_refs if r.get("type") == "lane_lineage"]
    assert any(r.get("lane_id") == "lane-1-patch" for r in lineage_primaries)


def test_evidence_bundle_selection_policy_is_versioned(setup):
    """Evidence bundle records selection_policy_id and selection_policy_version."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle(
        "graph-1",
        selection_policy_id="review-plane-v1",
        selection_policy_version="2",
    )

    assert bundle.selection_policy_id == "review-plane-v1"
    assert bundle.selection_policy_version == "2"


def test_evidence_bundle_is_persisted_in_evidence_store(setup):
    """Evidence bundle is persisted in the evidence store when provided."""
    from xmuse_core.structuring.verdict_store import EvidenceBundleStore

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")

    bundle = orch.assemble_evidence_bundle("graph-1", evidence_store=store)

    # Bundle must be retrievable from the store.
    retrieved = store.get(bundle.bundle_id)
    assert retrieved.bundle_id == bundle.bundle_id
    assert retrieved.source_run_id == "graph-1"
    assert retrieved.run_terminal_status == "merged"


def test_evidence_bundle_summary_contains_key_aggregation_facts(setup):
    """Evidence bundle summary includes run id, status, and lane counts."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-summary",
        },
        {
            "feature_id": "lane-2",
            "status": "failed",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-summary",
            "failure_reason": "exec_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle("graph-summary")

    assert "graph-summary" in bundle.summary
    assert "terminated" in bundle.summary
    assert "Failed: 1" in bundle.summary


def test_evidence_bundle_primary_refs_cover_all_cited_items(setup):
    """Every item referenced in verdict_refs / gate_report_refs / signal_refs
    must also appear in primary_refs (evidence curation contract)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "failure_reason": "merge_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Open a task with a gate report ref.
    task = orch._review_plane.open_review_task(
        "lane-1", gate_report_ref="logs/gates/lane-1/report.json"
    )
    orch._sm.update_metadata("lane-1", {"review_task_id": task.task_id})

    bundle = orch.assemble_evidence_bundle("graph-1")

    primary_types = {r.get("type") for r in bundle.primary_refs}
    # Gate report ref → review_task primary ref must exist.
    if bundle.gate_report_refs:
        assert "review_task" in primary_types
    # Negative signal → negative_signal primary ref must exist.
    if bundle.signal_refs:
        assert "negative_signal" in primary_types


# ---------------------------------------------------------------------------
# Merge guards (evbundle_6259476d67dd414a8be293d1025ccb8c)
# Finding: graph lineage terminated without proper merge, leaving sibling
# lineages stranded and run-level terminal status ambiguous.
# Guards: check_lineage_merge_completeness, assert_termination_safe,
#         record_incomplete_termination.
# ---------------------------------------------------------------------------


def test_check_lineage_merge_completeness_all_merged(setup):
    """All lanes merged → report is complete with no open or unmerged lineages."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
        },
        {
            "feature_id": "lane-2",
            "status": "merged",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    report = orch._review_plane.check_lineage_merge_completeness("graph-mg")

    assert report.is_complete is True
    assert set(report.merged_lineages) == {"lane-1", "lane-2"}
    assert report.terminated_without_merge == []
    assert report.open_lineages == []


def test_check_lineage_merge_completeness_open_lane(setup):
    """A pending lane is classified as open, making the report incomplete."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
        },
        {
            "feature_id": "lane-2",
            "status": "pending",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    report = orch._review_plane.check_lineage_merge_completeness("graph-mg")

    assert report.is_complete is False
    assert "lane-1" in report.merged_lineages
    assert "lane-2" in report.open_lineages
    assert report.terminated_without_merge == []


def test_check_lineage_merge_completeness_failed_without_merge_verdict(setup):
    """A failed lane with no merge verdict is classified as terminated_without_merge."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
        },
        {
            "feature_id": "lane-2",
            "status": "failed",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
            "failure_reason": "exec_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    report = orch._review_plane.check_lineage_merge_completeness("graph-mg")

    assert report.is_complete is False
    assert "lane-1" in report.merged_lineages
    assert "lane-2" in report.terminated_without_merge
    assert report.open_lineages == []


def test_check_lineage_merge_completeness_failed_with_merge_verdict_counts_as_merged(setup):
    """A failed lane that has a finalized MERGE verdict is classified as merged."""
    from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
            "failure_reason": "patch_forward_requested",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Persist a MERGE verdict for lane-1 directly in the store.
    verdict = ReviewVerdict(
        id="verdict-mg-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="Merged via patch-forward.",
        status="finalized",
    )
    orch._review_plane.store.save_verdict(verdict)

    report = orch._review_plane.check_lineage_merge_completeness("graph-mg")

    assert "lane-1" in report.merged_lineages
    assert report.terminated_without_merge == []
    assert report.is_complete is True


def test_check_lineage_merge_completeness_includes_source_lane_descendants(setup):
    """Descendants linked via source_lane_id are included in the completeness check."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-mg",
            "failure_reason": "patch_forward_requested",
        },
        {
            "feature_id": "lane-1-patch",
            "status": "pending",
            "prompt": "patch",
            "worktree": str(tmp_path),
            "source_lane_id": "lane-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    report = orch._review_plane.check_lineage_merge_completeness("graph-mg")

    # lane-1 is failed without merge verdict → terminated_without_merge.
    # lane-1-patch is pending → open.
    assert "lane-1" in report.terminated_without_merge
    assert "lane-1-patch" in report.open_lineages
    assert report.is_complete is False


def test_assert_termination_safe_passes_when_all_siblings_merged(setup):
    """assert_termination_safe does not raise when all sibling lineages are merged."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
        {
            "feature_id": "lane-2",
            "status": "gated",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # lane-2 is the lane being terminated; lane-1 is merged → safe.
    # Should not raise.
    orch._review_plane.assert_termination_safe("lane-2", "graph-ts")


def test_assert_termination_safe_raises_when_sibling_is_open(setup):
    """assert_termination_safe raises IncompleteLineageTerminationError when a
    sibling lineage is still open (in-flight)."""
    from xmuse_core.platform.review_plane import IncompleteLineageTerminationError

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gated",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
        {
            "feature_id": "lane-2",
            "status": "gated",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Terminating lane-2 while lane-1 is still open must be blocked.
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        orch._review_plane.assert_termination_safe("lane-2", "graph-ts")

    err = exc_info.value
    assert err.lane_id == "lane-2"
    assert err.graph_id == "graph-ts"
    assert "lane-1" in err.open_lineages
    assert err.unmerged_lineages == []


def test_assert_termination_safe_raises_when_sibling_terminated_without_merge(setup):
    """assert_termination_safe raises when a sibling already terminated without merge."""
    from xmuse_core.platform.review_plane import IncompleteLineageTerminationError

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
            "failure_reason": "exec_failed",
        },
        {
            "feature_id": "lane-2",
            "status": "gated",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # lane-1 terminated without merge; terminating lane-2 must be blocked.
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        orch._review_plane.assert_termination_safe("lane-2", "graph-ts")

    err = exc_info.value
    assert "lane-1" in err.unmerged_lineages


def test_assert_termination_safe_excludes_terminating_lane_from_sibling_check(setup):
    """The lane being terminated is excluded from the sibling open/unmerged checks."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
        {
            "feature_id": "lane-2",
            "status": "gated",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-ts",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # lane-2 is in-flight but it is the lane being terminated — must not block itself.
    # lane-1 is merged → no open siblings → safe.
    orch._review_plane.assert_termination_safe("lane-2", "graph-ts")


def test_ingest_verdict_terminate_blocked_by_open_sibling(setup):
    """ingest_verdict raises IncompleteLineageTerminationError for TERMINATE when
    a sibling lineage is still open (evbundle_6259476d67dd414a8be293d1025ccb8c)."""
    from xmuse_core.platform.review_plane import IncompleteLineageTerminationError
    from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gated",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-iv",
        },
        {
            "feature_id": "lane-2",
            "status": "gated",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-iv",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Open a review task for lane-2.
    task = orch._review_plane.open_review_task("lane-2")

    terminate_verdict = ReviewVerdict(
        id="verdict-term-1",
        lane_id="lane-2",
        decision=ReviewDecision.TERMINATE,
        summary="Terminating lane-2.",
    )

    # lane-1 is still open → TERMINATE must be blocked.
    with pytest.raises(IncompleteLineageTerminationError):
        orch._review_plane.ingest_verdict(task.task_id, terminate_verdict)


def test_ingest_verdict_terminate_allowed_when_all_siblings_merged(setup):
    """ingest_verdict allows TERMINATE when all sibling lineages are merged."""
    from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "merged",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-iv",
        },
        {
            "feature_id": "lane-2",
            "status": "gated",
            "prompt": "fix2",
            "worktree": str(tmp_path),
            "graph_id": "graph-iv",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    task = orch._review_plane.open_review_task("lane-2")

    terminate_verdict = ReviewVerdict(
        id="verdict-term-2",
        lane_id="lane-2",
        decision=ReviewDecision.TERMINATE,
        summary="Terminating lane-2 safely.",
    )

    # lane-1 is merged → TERMINATE is safe.
    result = orch._review_plane.ingest_verdict(task.task_id, terminate_verdict)
    assert result is not None


def test_record_incomplete_termination_persists_verdict(setup):
    """record_incomplete_termination writes a synthetic TERMINATE verdict with
    status='incomplete_termination' for the failed lane."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-rit",
            "failure_reason": "exec_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    verdict = orch._review_plane.record_incomplete_termination(
        "lane-1", "graph-rit", reason="exec_failed"
    )

    assert verdict.lane_id == "lane-1"
    assert verdict.status == "incomplete_termination"
    assert verdict.terminate_reason == "exec_failed"
    assert "evbundle_6259476d67dd414a8be293d1025ccb8c" in verdict.summary

    # Must be retrievable from the store.
    stored = orch._review_plane.store.get_verdict(verdict.id)
    assert stored.id == verdict.id
    assert stored.status == "incomplete_termination"


def test_record_incomplete_termination_is_idempotent(setup):
    """Calling record_incomplete_termination twice returns the same verdict."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-rit",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    v1 = orch._review_plane.record_incomplete_termination("lane-1", "graph-rit")
    v2 = orch._review_plane.record_incomplete_termination("lane-1", "graph-rit")

    assert v1.id == v2.id


def test_evidence_bundle_records_incomplete_termination_for_failed_lane(setup):
    """assemble_evidence_bundle calls record_incomplete_termination for failed lanes
    that never received a merge verdict, adding an incomplete_termination primary ref."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-rit",
            "failure_reason": "exec_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    bundle = orch.assemble_evidence_bundle("graph-rit")

    # An incomplete_termination primary ref must be present.
    incomplete_primaries = [
        r for r in bundle.primary_refs if r.get("type") == "incomplete_termination"
    ]
    assert len(incomplete_primaries) == 1
    assert incomplete_primaries[0]["lane_id"] == "lane-1"
    assert incomplete_primaries[0]["evidence_bundle_ref"] == (
        "evbundle_6259476d67dd414a8be293d1025ccb8c"
    )

    # The incomplete_termination signal ref must also appear in signal_refs.
    assert any("incomplete_termination" in ref for ref in bundle.signal_refs)


def test_evidence_bundle_does_not_duplicate_incomplete_termination_on_second_call(setup):
    """Calling assemble_evidence_bundle twice does not create duplicate
    incomplete_termination verdicts (idempotency via record_incomplete_termination)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "graph_id": "graph-rit",
            "failure_reason": "exec_failed",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    orch.assemble_evidence_bundle("graph-rit")
    bundle2 = orch.assemble_evidence_bundle("graph-rit")

    incomplete_primaries = [
        r for r in bundle2.primary_refs if r.get("type") == "incomplete_termination"
    ]
    # Exactly one incomplete_termination entry — no duplicates.
    assert len(incomplete_primaries) == 1


# ---------------------------------------------------------------------------
# Error recovery mechanisms (evbundle_6ef398723414454ba7212973e08e05f5)
# Tests: retry logic, circuit breaker state transitions, graceful degradation,
#        state preservation under failure.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_failed_lane_retries_up_to_max_retries(setup):
    """A lane in exec_failed can be retried up to MAX_RETRIES times via reworking.
    After MAX_RETRIES the state machine rejects further rework transitions."""
    from xmuse_core.platform.state_machine import MAX_RETRIES, InvalidTransitionError

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "exec_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Exhaust all retries
    for _ in range(MAX_RETRIES):
        orch._sm.transition("lane-1", "reworking")
        orch._sm.transition("lane-1", "dispatched")
        orch._sm.transition("lane-1", "exec_failed")

    # One more rework attempt must be rejected
    with pytest.raises(InvalidTransitionError):
        orch._sm.transition("lane-1", "reworking")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "exec_failed"
    assert lane["retry_count"] == MAX_RETRIES


@pytest.mark.asyncio
async def test_gate_failed_lane_retries_up_to_max_retries(setup):
    """A lane in gate_failed can be retried up to MAX_RETRIES times.
    After MAX_RETRIES the state machine rejects further rework transitions."""
    from xmuse_core.platform.state_machine import MAX_RETRIES, InvalidTransitionError

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    for _ in range(MAX_RETRIES):
        orch._sm.transition("lane-1", "reworking")
        orch._sm.transition("lane-1", "dispatched")
        orch._sm.transition("lane-1", "executed")
        orch._sm.transition(
            "lane-1",
            "gate_failed",
            metadata={"failure_reason": "gate_failed"},
        )

    with pytest.raises(InvalidTransitionError):
        orch._sm.transition("lane-1", "reworking")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["retry_count"] == MAX_RETRIES


@pytest.mark.asyncio
async def test_retry_count_increments_on_each_rework_transition(setup):
    """retry_count increments by 1 on each reworking transition."""
    from xmuse_core.platform.state_machine import MAX_RETRIES

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "exec_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    for expected_count in range(1, MAX_RETRIES + 1):
        orch._sm.transition("lane-1", "reworking")
        lane = orch._sm.get_lane("lane-1")
        assert lane["retry_count"] == expected_count
        orch._sm.transition("lane-1", "dispatched")
        orch._sm.transition("lane-1", "exec_failed")


@pytest.mark.asyncio
async def test_review_retry_count_increments_on_reconcile_recovery(setup):
    """review_retry_count increments each time reconcile recovers a review failure."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_timeout",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock):
        await orch.reconcile_status_changes()

    lane = orch._sm.get_lane("lane-1")
    assert lane["review_retry_count"] == 1
    assert lane["review_recovered_from"] == "review_timeout"
    assert "failure_reason" not in lane


@pytest.mark.asyncio
async def test_review_retry_stops_after_max_review_retries(setup):
    """reconcile does not retry review when review_retry_count >= 2."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_timeout",
            "review_retry_count": 2,  # already at limit
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    review.assert_not_called()
    assert orch._sm.get_lane("lane-1")["status"] == "gate_failed"


@pytest.mark.asyncio
async def test_execution_god_non_zero_exit_marks_exec_failed_preserves_prompt(setup):
    """A non-zero exit from the execution god marks exec_failed and preserves
    the original lane prompt (no data corruption)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "dispatched",
            "prompt": "build the feature",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    fail_result = SpawnResult(exit_code=1, stdout="", stderr="error")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=fail_result):
        await orch._run_execution_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "exec_failed"
    assert lane["failure_reason"] == "non_zero_exit"
    # Prompt must be preserved
    assert lane["prompt"] == "build the feature"


@pytest.mark.asyncio
async def test_execution_god_timeout_preserves_lane_metadata(setup):
    """A timed-out execution god marks exec_failed and preserves all existing
    lane metadata (no data loss)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "dispatched",
            "prompt": "fix bug",
            "worktree": str(tmp_path),
            "graph_id": "graph-1",
            "resolution_id": "res-1",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    timeout_result = SpawnResult(exit_code=-1, stdout="", stderr="timeout", timed_out=True)

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=timeout_result):
        await orch._run_execution_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "exec_failed"
    assert lane["failure_reason"] == "timeout"
    # Metadata from before the failure must be intact
    assert lane["graph_id"] == "graph-1"
    assert lane["resolution_id"] == "res-1"
    assert lane["prompt"] == "fix bug"


@pytest.mark.asyncio
async def test_review_infra_unavailable_circuit_breaker_respects_backoff(setup):
    """When review_infra_unavailable is set with a future retry_after_at,
    reconcile does not retry (circuit breaker open)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_infra_unavailable",
            "review_retry_after_at": 9999999999,  # far future
            "review_retry_count": 0,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    review.assert_not_called()
    assert orch._sm.get_lane("lane-1")["status"] == "gate_failed"


@pytest.mark.asyncio
async def test_review_infra_unavailable_circuit_breaker_closes_after_backoff(setup):
    """When review_retry_after_at is in the past, reconcile retries (circuit breaker closed)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_infra_unavailable",
            "review_retry_after_at": 1,  # past
            "review_retry_count": 0,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    review.assert_awaited_once_with("lane-1")
    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gated"
    assert lane["review_retry_count"] == 1
    assert lane["review_recovered_from"] == "review_infra_unavailable"


@pytest.mark.asyncio
async def test_review_infra_unavailable_circuit_breaker_stops_at_40_retries(setup):
    """review_infra_unavailable retries stop at 40 (circuit breaker max)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
            "failure_reason": "review_infra_unavailable",
            "review_retry_after_at": 1,  # past
            "review_retry_count": 40,  # at limit
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_review_god", new_callable=AsyncMock) as review:
        await orch.reconcile_status_changes()

    review.assert_not_called()
    assert orch._sm.get_lane("lane-1")["status"] == "gate_failed"


@pytest.mark.asyncio
async def test_dispatch_lane_failure_does_not_corrupt_sibling_lanes(setup):
    """When one lane's execution god fails, sibling lanes in the same graph
    are not affected."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "pending",
            "prompt": "fix bug",
            "worktree": str(tmp_path),
        },
        {
            "feature_id": "lane-2",
            "status": "pending",
            "prompt": "add feature",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    fail_result = SpawnResult(exit_code=1, stdout="", stderr="error")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=fail_result):
        await orch.dispatch_lane("lane-1")

    lane1 = orch._sm.get_lane("lane-1")
    lane2 = orch._sm.get_lane("lane-2")
    assert lane1["status"] == "exec_failed"
    # lane-2 must be untouched
    assert lane2["status"] == "pending"
    assert lane2["prompt"] == "add feature"


@pytest.mark.asyncio
async def test_invalid_transition_does_not_corrupt_lane_state(setup):
    """An invalid state transition raises InvalidTransitionError and leaves
    the lane in its original state."""
    from xmuse_core.platform.state_machine import InvalidTransitionError

    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "pending",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with pytest.raises(InvalidTransitionError):
        orch._sm.transition("lane-1", "merged")  # pending → merged is invalid

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "pending"


@pytest.mark.asyncio
async def test_reconcile_handles_empty_lanes_without_error(setup):
    """reconcile_status_changes on an empty lane list completes without error."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": []}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    # Must not raise
    await orch.reconcile_status_changes()


@pytest.mark.asyncio
async def test_review_plane_error_does_not_prevent_lane_merge_on_reviewed(setup):
    """A review plane failure during on_lane_reviewed must not prevent the lane
    from transitioning to merged (graceful degradation)."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "reviewed",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "review_decision": "merge",
            "review_summary": "No findings.",
            "review_verdict_id": "verdict-error-recovery-1",
            # Deliberately omit review_task_id to trigger review plane error
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
        await orch.on_lane_reviewed("lane-1")

    # Lane must reach merged despite the review plane error
    assert orch._sm.get_lane("lane-1")["status"] == "merged"


@pytest.mark.asyncio
async def test_gate_failure_preserves_lane_prompt_and_graph_id(setup):
    """A gate failure must not overwrite the lane's prompt or graph_id."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "executed",
            "prompt": "build the feature",
            "worktree": str(tmp_path),
            "graph_id": "graph-preserve",
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(orch, "_run_gate", new_callable=AsyncMock, return_value=False):
        with patch.object(orch, "_run_review_god", new_callable=AsyncMock):
            await orch._on_lane_executed("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["prompt"] == "build the feature"
    assert lane["graph_id"] == "graph-preserve"


@pytest.mark.asyncio
async def test_concurrent_dispatch_does_not_double_transition_to_exec_failed(setup):
    """Concurrent dispatch calls for the same lane do not cause double transitions
    or corrupt the retry_count."""
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "pending",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    fail_result = SpawnResult(exit_code=1, stdout="", stderr="error")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=fail_result):
        # Only one dispatch should succeed (pending → dispatched is a valid
        # transition only once); the second will raise InvalidTransitionError
        # which the caller must handle.
        try:
            await asyncio.gather(
                orch.dispatch_lane("lane-1"),
                orch.dispatch_lane("lane-1"),
            )
        except Exception:
            pass

    lane = orch._sm.get_lane("lane-1")
    # The lane must be in a consistent terminal state, not in an intermediate one
    assert lane["status"] in ("exec_failed", "dispatched", "executed")
    # retry_count must not exceed 1 from a single failure cycle
    assert lane.get("retry_count", 0) <= 1


@pytest.mark.asyncio
async def test_execution_spawn_retries_transient_exception_and_records_recovery(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "dispatched",
            "prompt": "fix",
            "worktree": str(tmp_path),
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    orch._recovery.config = orch._recovery.config.__class__(
        max_attempts=2,
        initial_delay_s=0,
        max_delay_s=0,
    )

    with patch.object(
        orch._spawner,
        "spawn",
        new_callable=AsyncMock,
        side_effect=[
            TimeoutError("temporary spawn outage"),
            SpawnResult(exit_code=0, stdout="", stderr=""),
        ],
    ):
        with patch.object(orch, "_on_lane_executed", new_callable=AsyncMock):
            await orch._run_execution_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "executed"
    events = lane["recovery_events"]
    assert any(event["kind"] == "retry_scheduled" for event in events)


@pytest.mark.asyncio
async def test_review_spawn_retries_transient_result_and_records_recovery(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gated",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    orch._recovery.config = orch._recovery.config.__class__(
        max_attempts=2,
        initial_delay_s=0,
        max_delay_s=0,
    )

    with patch.object(
        orch._spawner,
        "spawn",
        new_callable=AsyncMock,
        side_effect=[
            SpawnResult(exit_code=1, stdout="", stderr="429 too many requests"),
            SpawnResult(exit_code=0, stdout="approved", stderr=""),
        ],
    ):
        with patch.object(orch, "on_lane_reviewed", new_callable=AsyncMock):
            await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "reviewed"
    assert any(event["kind"] == "retry_scheduled" for event in lane["recovery_events"])


@pytest.mark.asyncio
async def test_review_spawn_circuit_open_marks_infra_retry(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gated",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )
    orch._recovery.config = orch._recovery.config.__class__(
        max_attempts=1,
        circuit_failure_threshold=1,
        circuit_recovery_timeout_s=30,
    )
    orch._recovery.circuit("orchestrator.review_god").record_failure()

    await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_infra_unavailable"
    assert lane["review_infra_reason"] == "circuit_open"
    assert lane["degraded_component"] == "review_god"


@pytest.mark.asyncio
async def test_review_spawn_non_transient_failure_preserves_valid_state(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gated",
            "prompt": "fix",
            "worktree": str(tmp_path),
            "gate_passed": True,
        },
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path, xmuse_root=tmp_path, mcp_port=9999,
    )

    with patch.object(
        orch._spawner,
        "spawn",
        new_callable=AsyncMock,
        side_effect=RuntimeError("bad review command"),
    ):
        await orch._run_review_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_spawn_failed"
    assert lane["review_infra_reason"] == "RuntimeError"
