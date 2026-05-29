"""Direct unit tests for ReviewPlaneController.

Lane: self-evolution-review_plane-res_e0fefabbce6c449799c942bfca91061a-graph-v1
Evidence bundle: evbundle_648180f3cce14c129fad244774d94f80
Track: review_plane

These tests verify the controller's own behaviour without going through
PlatformOrchestrator.  The orchestrator-level integration tests in
test_xmuse_platform_orchestrator.py already cover the end-to-end path;
this file covers the controller contract directly so that regressions in
the controller layer are caught independently of orchestrator changes.

Spec reference: blueprint-anchored self-evolution, "Run Terminal Aggregation"
and "Lineage queries" sections.  Hard Rule #10: run terminalization must be
computed through an explicit aggregation contract rather than guessed from
individual lane states.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.review_plane import ReviewPlaneController
from xmuse_core.structuring.models import (
    ReviewDecision,
    ReviewTaskStatus,
    ReviewVerdict,
    RunTerminalStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_controller(
    tmp_path: Path,
    lanes: list[dict],
    *,
    require_final_action_approval: bool = False,
) -> ReviewPlaneController:
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    store_path = tmp_path / "review_plane.json"
    final_actions_path = tmp_path / "final_actions.json"
    return ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=store_path,
        final_actions_path=final_actions_path,
        require_final_action_approval=require_final_action_approval,
    )


def _lane(
    feature_id: str,
    status: str,
    *,
    graph_id: str | None = None,
    source_lane_id: str | None = None,
    prompt: str = "do work",
) -> dict:
    lane: dict = {"feature_id": feature_id, "status": status, "prompt": prompt}
    if graph_id is not None:
        lane["graph_id"] = graph_id
    if source_lane_id is not None:
        lane["source_lane_id"] = source_lane_id
    return lane


# ---------------------------------------------------------------------------
# open_review_task
# ---------------------------------------------------------------------------


def test_open_review_task_creates_pending_task(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated", graph_id="graph-1")],
    )

    task = ctrl.open_review_task("lane-1")

    assert task.task_id.startswith("rtask_")
    assert task.lane_id == "lane-1"
    assert task.status == ReviewTaskStatus.PENDING
    assert task.graph_id == "graph-1"


def test_open_review_task_is_idempotent(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )

    task1 = ctrl.open_review_task("lane-1")
    task2 = ctrl.open_review_task("lane-1")

    assert task1.task_id == task2.task_id


def test_open_review_task_captures_gate_report_ref(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )

    task = ctrl.open_review_task("lane-1", gate_report_ref="logs/gates/lane-1/report.json")

    assert task.gate_report_ref == "logs/gates/lane-1/report.json"


def test_open_review_task_captures_lane_prompt(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated", prompt="Fix the auth bug")],
    )

    task = ctrl.open_review_task("lane-1")

    assert task.lane_prompt == "Fix the auth bug"


# ---------------------------------------------------------------------------
# cancel_review_task
# ---------------------------------------------------------------------------


def test_cancel_review_task_marks_task_cancelled(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )
    task = ctrl.open_review_task("lane-1")

    cancelled = ctrl.cancel_review_task(task.task_id)

    assert cancelled.status == ReviewTaskStatus.CANCELLED
    # Persisted correctly.
    stored = ctrl.store.get_task(task.task_id)
    assert stored.status == ReviewTaskStatus.CANCELLED


# ---------------------------------------------------------------------------
# ingest_verdict
# ---------------------------------------------------------------------------


def test_ingest_verdict_persists_verdict_and_updates_task(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )
    task = ctrl.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="No findings.",
    )

    result = ctrl.ingest_verdict(task.task_id, verdict)

    # Verdict persisted.
    stored_verdict = ctrl.store.get_verdict("verdict-1")
    assert stored_verdict.lane_id == "lane-1"
    assert stored_verdict.task_id == task.task_id

    # Task updated.
    stored_task = ctrl.store.get_task(task.task_id)
    assert stored_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert stored_task.verdict_id == "verdict-1"

    # Adapter result.
    assert result.transition_status == "reviewed"


def test_ingest_verdict_rework_returns_rejected_transition(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )
    task = ctrl.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-rework-1",
        lane_id="lane-1",
        decision=ReviewDecision.REWORK,
        summary="Missing tests.",
    )

    result = ctrl.ingest_verdict(task.task_id, verdict)

    assert result.transition_status == "rejected"
    assert result.final_action is None
    assert result.patch_lane is None


def test_ingest_verdict_patch_forward_returns_patch_lane(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )
    task = ctrl.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-pf-1",
        lane_id="lane-1",
        decision=ReviewDecision.PATCH_FORWARD,
        summary="Apply patch.",
        patch_instructions="Fix the import.",
    )

    result = ctrl.ingest_verdict(task.task_id, verdict)

    assert result.transition_status is None
    assert result.patch_lane is not None
    assert result.patch_lane["feature_id"] == "lane-1-patch-forward"
    assert result.patch_lane["source_lane_id"] == "lane-1"


def test_ingest_verdict_terminate_with_final_action_approval(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
        require_final_action_approval=True,
    )
    task = ctrl.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-term-1",
        lane_id="lane-1",
        decision=ReviewDecision.TERMINATE,
        summary="Terminate: unrecoverable.",
        terminate_reason="unrecoverable_failure",
    )

    result = ctrl.ingest_verdict(task.task_id, verdict)

    assert result.transition_status is None
    assert result.final_action is not None
    assert result.final_action.action == "terminate"


def test_ingest_verdict_stamps_task_id_on_verdict(tmp_path):
    """Verdict without task_id gets stamped with the task_id during ingestion."""
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "gated")],
    )
    task = ctrl.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-stamp-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="ok",
        task_id=None,
    )

    ctrl.ingest_verdict(task.task_id, verdict)

    stored = ctrl.store.get_verdict("verdict-stamp-1")
    assert stored.task_id == task.task_id


# ---------------------------------------------------------------------------
# verdict_lineage_for_lane
# ---------------------------------------------------------------------------


def test_verdict_lineage_for_lane_returns_empty_for_unknown_lane(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])

    lineage = ctrl.verdict_lineage_for_lane("lane-unknown")

    assert lineage == []


def test_verdict_lineage_for_lane_returns_task_without_verdict_when_pending(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])
    task = ctrl.open_review_task("lane-1")

    lineage = ctrl.verdict_lineage_for_lane("lane-1")

    assert len(lineage) == 1
    assert lineage[0]["task"]["task_id"] == task.task_id
    assert lineage[0]["verdict"] is None


def test_verdict_lineage_for_lane_returns_task_and_verdict_after_ingest(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])
    task = ctrl.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-lineage-lane-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="ok",
    )
    ctrl.ingest_verdict(task.task_id, verdict)

    lineage = ctrl.verdict_lineage_for_lane("lane-1")

    assert len(lineage) == 1
    assert lineage[0]["task"]["task_id"] == task.task_id
    assert lineage[0]["verdict"] is not None
    assert lineage[0]["verdict"]["id"] == "verdict-lineage-lane-1"
    assert lineage[0]["verdict"]["task_id"] == task.task_id


def test_verdict_lineage_for_lane_records_multiple_review_cycles(tmp_path):
    """A lane that goes through rework then merge has two task→verdict entries."""
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])

    # First review cycle: rework.
    task1 = ctrl.open_review_task("lane-1")
    ctrl.ingest_verdict(
        task1.task_id,
        ReviewVerdict(
            id="verdict-rework-cycle",
            lane_id="lane-1",
            decision=ReviewDecision.REWORK,
            summary="Missing tests.",
        ),
    )

    # Second review cycle: merge.
    task2 = ctrl.open_review_task("lane-1")
    ctrl.ingest_verdict(
        task2.task_id,
        ReviewVerdict(
            id="verdict-merge-cycle",
            lane_id="lane-1",
            decision=ReviewDecision.MERGE,
            summary="Tests added.",
        ),
    )

    lineage = ctrl.verdict_lineage_for_lane("lane-1")

    assert len(lineage) == 2
    decisions = {entry["verdict"]["decision"] for entry in lineage if entry["verdict"]}
    assert decisions == {"rework", "merge"}


# ---------------------------------------------------------------------------
# has_verdict_lineage
# ---------------------------------------------------------------------------


def test_has_verdict_lineage_false_before_any_verdict(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])
    ctrl.open_review_task("lane-1")

    assert ctrl.has_verdict_lineage("lane-1") is False


def test_has_verdict_lineage_true_after_merge_verdict(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])
    task = ctrl.open_review_task("lane-1")
    ctrl.ingest_verdict(
        task.task_id,
        ReviewVerdict(
            id="verdict-has-1",
            lane_id="lane-1",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )

    assert ctrl.has_verdict_lineage("lane-1") is True


def test_has_verdict_lineage_false_for_unknown_lane(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "gated")])

    assert ctrl.has_verdict_lineage("lane-unknown") is False


# ---------------------------------------------------------------------------
# verdict_lineage_for_run
# ---------------------------------------------------------------------------


def test_verdict_lineage_for_run_returns_empty_for_unknown_graph(tmp_path):
    ctrl = _make_controller(tmp_path, [_lane("lane-1", "merged", graph_id="graph-1")])

    lineage = ctrl.verdict_lineage_for_run("graph-unknown")

    assert lineage == []


def test_verdict_lineage_for_run_returns_entries_for_all_graph_lanes(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "merged", graph_id="graph-1"),
        ],
    )
    task1 = ctrl.open_review_task("lane-1")
    ctrl.ingest_verdict(
        task1.task_id,
        ReviewVerdict(
            id="verdict-run-lane-1",
            lane_id="lane-1",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )
    task2 = ctrl.open_review_task("lane-2")
    ctrl.ingest_verdict(
        task2.task_id,
        ReviewVerdict(
            id="verdict-run-lane-2",
            lane_id="lane-2",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )

    lineage = ctrl.verdict_lineage_for_run("graph-1")

    verdict_ids = {entry["verdict"]["id"] for entry in lineage if entry["verdict"]}
    assert "verdict-run-lane-1" in verdict_ids
    assert "verdict-run-lane-2" in verdict_ids


def test_verdict_lineage_for_run_includes_patch_forward_descendants(tmp_path):
    """Patch-forward descendants (source_lane_id lineage) are included."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "failed", graph_id="graph-1"),
            _lane("lane-1-patch-forward", "merged", source_lane_id="lane-1"),
        ],
    )
    task_pf = ctrl.open_review_task("lane-1-patch-forward")
    ctrl.ingest_verdict(
        task_pf.task_id,
        ReviewVerdict(
            id="verdict-pf-run",
            lane_id="lane-1-patch-forward",
            decision=ReviewDecision.MERGE,
            summary="patch merged",
        ),
    )

    lineage = ctrl.verdict_lineage_for_run("graph-1")

    verdict_ids = {entry["verdict"]["id"] for entry in lineage if entry["verdict"]}
    assert "verdict-pf-run" in verdict_ids


def test_verdict_lineage_for_run_excludes_lanes_from_other_graphs(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-other", "merged", graph_id="graph-2"),
        ],
    )
    task_other = ctrl.open_review_task("lane-other")
    ctrl.ingest_verdict(
        task_other.task_id,
        ReviewVerdict(
            id="verdict-other-graph",
            lane_id="lane-other",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )

    lineage = ctrl.verdict_lineage_for_run("graph-1")

    verdict_ids = {entry["verdict"]["id"] for entry in lineage if entry["verdict"]}
    assert "verdict-other-graph" not in verdict_ids


def test_verdict_lineage_for_run_omits_lanes_with_no_review_task(tmp_path):
    """Lanes with no review task are omitted from the run lineage."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "merged", graph_id="graph-1"),
        ],
    )
    # Only open a task for lane-1.
    task1 = ctrl.open_review_task("lane-1")
    ctrl.ingest_verdict(
        task1.task_id,
        ReviewVerdict(
            id="verdict-only-lane-1",
            lane_id="lane-1",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )

    lineage = ctrl.verdict_lineage_for_run("graph-1")

    # lane-2 has no task so it contributes no entries.
    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert "lane-1" in lane_ids
    assert "lane-2" not in lane_ids


# ---------------------------------------------------------------------------
# aggregate_run_terminal_status (direct controller tests)
# ---------------------------------------------------------------------------


def test_controller_aggregate_merged_when_all_lanes_merged(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "merged", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.MERGED
    assert result.open_lane_lineages == []
    assert result.failed_lineages == []
    assert result.open_final_action_holds == []


def test_controller_aggregate_in_progress_when_lane_pending(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "pending", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.IN_PROGRESS
    assert "lane-2" in result.open_lane_lineages


def test_controller_aggregate_terminated_when_lane_failed(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "failed", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.TERMINATED
    assert "lane-2" in result.failed_lineages
    assert result.open_lane_lineages == []


def test_controller_aggregate_terminated_for_exec_failed(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "exec_failed", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.TERMINATED
    assert "lane-2" in result.failed_lineages


def test_controller_aggregate_terminated_for_gate_failed_closed_lineage(tmp_path):
    """gate_failed is in _OPEN so a gate_failed lane keeps the run in_progress."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "gate_failed", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    # gate_failed is recoverable (retry path), so it is treated as open.
    assert result.status == RunTerminalStatus.IN_PROGRESS
    assert "lane-2" in result.open_lane_lineages


def test_controller_aggregate_blocked_for_input_with_pending_hold(tmp_path):
    """All lineages closed but a pending final-action hold → blocked_for_input."""
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps({"lanes": [_lane("lane-1", "merged", graph_id="graph-1")]}),
        encoding="utf-8",
    )
    store_path = tmp_path / "review_plane.json"
    final_actions_path = tmp_path / "final_actions.json"
    ctrl = ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=store_path,
        final_actions_path=final_actions_path,
    )
    # Create a pending hold for lane-1 directly in the final-action store.
    fa_store = FinalActionGateStore(final_actions_path)
    fa_store.create_hold(
        lane_id="lane-1",
        verdict_id="verdict-hold-1",
        action="merge",
        target_status="reviewed",
        summary="awaiting approval",
    )

    result = ctrl.aggregate_run_terminal_status("graph-1", final_action_store=fa_store)

    assert result.status == RunTerminalStatus.BLOCKED_FOR_INPUT
    assert len(result.open_final_action_holds) == 1


def test_controller_aggregate_empty_graph_returns_merged(tmp_path):
    ctrl = _make_controller(tmp_path, [])

    result = ctrl.aggregate_run_terminal_status("graph-empty")

    assert result.status == RunTerminalStatus.MERGED


def test_controller_aggregate_basis_records_key_inputs(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [_lane("lane-1", "merged", graph_id="graph-1")],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert "graph_id=graph-1" in result.basis
    assert "total_lane_lineages=1" in result.basis
    assert "open=0" in result.basis
    assert "failed=0" in result.basis


def test_controller_aggregate_includes_patch_forward_descendants(tmp_path):
    """Patch-forward descendants are included via source_lane_id closure."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "failed", graph_id="graph-1"),
            _lane("lane-1-pf", "pending", source_lane_id="lane-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.IN_PROGRESS
    assert "lane-1-pf" in result.open_lane_lineages


def test_controller_aggregate_patch_forward_merged_closes_lineage(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "failed", graph_id="graph-1"),
            _lane("lane-1-pf", "merged", source_lane_id="lane-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    # lane-1 is failed (terminated lineage), patch-forward is merged (closed ok).
    assert result.status == RunTerminalStatus.TERMINATED
    assert "lane-1" in result.failed_lineages
    assert result.open_lane_lineages == []


def test_controller_aggregate_ignores_lanes_from_other_graphs(tmp_path):
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-other", "pending", graph_id="graph-2"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.MERGED
    assert "lane-other" not in result.open_lane_lineages


def test_controller_aggregate_multi_level_patch_forward_closure(tmp_path):
    """Multi-level patch-forward chain: lane-1 → pf-1 → pf-2 (all merged)."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "failed", graph_id="graph-1"),
            _lane("lane-1-pf-1", "failed", source_lane_id="lane-1"),
            _lane("lane-1-pf-2", "merged", source_lane_id="lane-1-pf-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    # Both lane-1 and lane-1-pf-1 are failed; lane-1-pf-2 is merged.
    # All lineages closed; at least one via fail → terminated.
    assert result.status == RunTerminalStatus.TERMINATED
    assert "lane-1" in result.failed_lineages
    assert "lane-1-pf-1" in result.failed_lineages
    assert result.open_lane_lineages == []


def test_controller_aggregate_in_progress_for_reworking_lane(tmp_path):
    """A reworking lane is still open (in-flight)."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "merged", graph_id="graph-1"),
            _lane("lane-2", "reworking", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.IN_PROGRESS
    assert "lane-2" in result.open_lane_lineages


def test_controller_aggregate_in_progress_for_awaiting_final_action(tmp_path):
    """awaiting_final_action is still open (not yet resolved)."""
    ctrl = _make_controller(
        tmp_path,
        [
            _lane("lane-1", "awaiting_final_action", graph_id="graph-1"),
        ],
    )

    result = ctrl.aggregate_run_terminal_status("graph-1")

    assert result.status == RunTerminalStatus.IN_PROGRESS
    assert "lane-1" in result.open_lane_lineages
