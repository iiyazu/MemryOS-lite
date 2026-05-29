"""Tests for review plane merge safety guards.

Covers:
- check_lineage_merge_completeness
- assert_termination_safe / IncompleteLineageTerminationError
- record_incomplete_termination (idempotency + content)
- ingest_verdict TERMINATE guard (blocks unsafe terminations)

Evidence bundle reference: evbundle_6259476d67dd414a8be293d1025ccb8c
Spec: blueprint-anchored self-evolution, "Merge guards" section.
Lane: self-evolution-reliability_hardening-res_e404647bc0cf4611b1f4e42c3c2b3466-
graph-v1-review-plane-merge-safety-test-merge-
"""
from __future__ import annotations

import json

import pytest

from xmuse_core.platform.review_plane import (
    IncompleteLineageTerminationError,
    LineageMergeReport,
    ReviewPlaneController,
)
from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_controller(tmp_path, lanes: list[dict]) -> ReviewPlaneController:
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": lanes}))
    store_path = tmp_path / "review_plane.json"
    final_actions_path = tmp_path / "final_actions.json"
    return ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=store_path,
        final_actions_path=final_actions_path,
    )


def _open_task(ctrl: ReviewPlaneController, lane_id: str) -> str:
    task = ctrl.open_review_task(lane_id)
    return task.task_id


# ---------------------------------------------------------------------------
# check_lineage_merge_completeness
# ---------------------------------------------------------------------------


def test_check_completeness_all_merged(tmp_path):
    """All lanes merged → is_complete=True, no open or unmerged lineages."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "merged", "prompt": "b", "graph_id": "g1"},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert isinstance(report, LineageMergeReport)
    assert report.graph_id == "g1"
    assert set(report.merged_lineages) == {"lane-a", "lane-b"}
    assert report.terminated_without_merge == []
    assert report.open_lineages == []
    assert report.is_complete is True


def test_check_completeness_failed_lane_without_merge_verdict(tmp_path):
    """A failed lane with no MERGE verdict → terminated_without_merge."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "failed", "prompt": "b", "graph_id": "g1"},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-b" in report.terminated_without_merge
    assert "lane-a" in report.merged_lineages
    assert report.open_lineages == []
    assert report.is_complete is False


def test_check_completeness_open_lane(tmp_path):
    """A pending lane → open_lineages, is_complete=False."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "pending", "prompt": "b", "graph_id": "g1"},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-b" in report.open_lineages
    assert report.terminated_without_merge == []
    assert report.is_complete is False


def test_check_completeness_dispatched_lane_is_open(tmp_path):
    """A dispatched lane is still open."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "dispatched", "prompt": "a", "graph_id": "g1"},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-a" in report.open_lineages
    assert report.is_complete is False


def test_check_completeness_exec_failed_is_terminated_without_merge(tmp_path):
    """exec_failed lane without MERGE verdict → terminated_without_merge."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "exec_failed", "prompt": "a", "graph_id": "g1"},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-a" in report.terminated_without_merge
    assert report.is_complete is False


def test_check_completeness_gate_failed_is_open_recoverable(tmp_path):
    """gate_failed lane is recoverable (retry/rework/re-gate) → open_lineages."""
    ctrl = _make_controller(tmp_path, [
        {
            "feature_id": "lane-a",
            "status": "gate_failed",
            "prompt": "a",
            "graph_id": "g1",
        },
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-a" in report.open_lineages
    assert "lane-a" not in report.terminated_without_merge
    assert report.is_complete is False


def test_check_completeness_failed_lane_with_merge_verdict_counts_as_merged(tmp_path):
    """A failed lane that has a finalized MERGE verdict counts as merged."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "failed", "prompt": "a", "graph_id": "g1"},
    ])
    # Inject a MERGE verdict directly into the store.
    verdict = ReviewVerdict(
        id="v-merge-a",
        lane_id="lane-a",
        decision=ReviewDecision.MERGE,
        status="finalized",
        summary="merged via patch-forward",
    )
    ctrl.store.save_verdict(verdict)

    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-a" in report.merged_lineages
    assert report.terminated_without_merge == []
    assert report.is_complete is True


def test_check_completeness_includes_source_lane_id_descendants(tmp_path):
    """Patch-forward descendants (source_lane_id) are included in the closure."""
    ctrl = _make_controller(tmp_path, [
        {
            "feature_id": "lane-a",
            "status": "failed",
            "prompt": "a",
            "graph_id": "g1",
            "failure_reason": "patch_forward_requested",
        },
        {
            "feature_id": "lane-a-patch",
            "status": "pending",
            "prompt": "patch",
            "source_lane_id": "lane-a",
        },
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    # lane-a is failed (terminated_without_merge), lane-a-patch is open.
    assert "lane-a" in report.terminated_without_merge
    assert "lane-a-patch" in report.open_lineages
    assert report.is_complete is False


def test_check_completeness_patch_forward_merged_closes_lineage(tmp_path):
    """When the patch-forward descendant merges, the lineage is complete."""
    ctrl = _make_controller(tmp_path, [
        {
            "feature_id": "lane-a",
            "status": "failed",
            "prompt": "a",
            "graph_id": "g1",
            "failure_reason": "patch_forward_requested",
        },
        {
            "feature_id": "lane-a-patch",
            "status": "merged",
            "prompt": "patch",
            "source_lane_id": "lane-a",
        },
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    # lane-a is failed (terminated_without_merge), lane-a-patch is merged.
    # is_complete is False because lane-a is still terminated_without_merge.
    assert "lane-a" in report.terminated_without_merge
    assert "lane-a-patch" in report.merged_lineages
    assert report.is_complete is False


def test_check_completeness_empty_graph(tmp_path):
    """A graph with no lanes is vacuously complete."""
    ctrl = _make_controller(tmp_path, [])
    report = ctrl.check_lineage_merge_completeness("g-empty")

    assert report.merged_lineages == []
    assert report.terminated_without_merge == []
    assert report.open_lineages == []
    assert report.is_complete is True


def test_check_completeness_ignores_other_graph_lanes(tmp_path):
    """Lanes from a different graph_id are not included."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "pending", "prompt": "b", "graph_id": "g2"},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")

    assert "lane-b" not in report.open_lineages
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# assert_termination_safe
# ---------------------------------------------------------------------------


def test_assert_termination_safe_passes_when_all_siblings_merged(tmp_path):
    """No exception when all sibling lineages are merged."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    # lane-b is the one being terminated; lane-a is merged → safe.
    ctrl.assert_termination_safe("lane-b", "g1")  # must not raise


def test_assert_termination_safe_raises_when_open_sibling_exists(tmp_path):
    """Raises IncompleteLineageTerminationError when a sibling is still open."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "pending", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-b", "g1")

    err = exc_info.value
    assert err.lane_id == "lane-b"
    assert err.graph_id == "g1"
    assert "lane-a" in err.open_lineages
    assert err.unmerged_lineages == []


def test_assert_termination_safe_raises_when_unmerged_sibling_exists(tmp_path):
    """Raises when a sibling terminated without a merge verdict."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "failed", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-b", "g1")

    err = exc_info.value
    assert "lane-a" in err.unmerged_lineages
    assert err.open_lineages == []


def test_assert_termination_safe_excludes_terminating_lane_from_sibling_check(tmp_path):
    """The lane being terminated is not counted as an open sibling."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        # lane-b is in-flight (gated) — it is the one being terminated.
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    # lane-b is in open_lineages but it's the one being terminated → excluded.
    ctrl.assert_termination_safe("lane-b", "g1")  # must not raise


def test_assert_termination_safe_raises_with_both_open_and_unmerged_siblings(tmp_path):
    """Raises with both open and unmerged siblings populated."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "pending", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "failed", "prompt": "b", "graph_id": "g1"},
        {"feature_id": "lane-c", "status": "gated", "prompt": "c", "graph_id": "g1"},
    ])
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-c", "g1")

    err = exc_info.value
    assert "lane-a" in err.open_lineages
    assert "lane-b" in err.unmerged_lineages


def test_assert_termination_safe_single_lane_graph_passes(tmp_path):
    """A single-lane graph with no siblings is always safe to terminate."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "gated", "prompt": "a", "graph_id": "g1"},
    ])
    ctrl.assert_termination_safe("lane-a", "g1")  # must not raise


# ---------------------------------------------------------------------------
# record_incomplete_termination
# ---------------------------------------------------------------------------


def test_record_incomplete_termination_creates_verdict(tmp_path):
    """Creates a synthetic TERMINATE verdict with status='incomplete_termination'."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "failed", "prompt": "a", "graph_id": "g1"},
    ])
    verdict = ctrl.record_incomplete_termination("lane-a", "g1", reason="merge_failed")

    assert verdict.lane_id == "lane-a"
    assert verdict.decision == ReviewDecision.TERMINATE
    assert verdict.status == "incomplete_termination"
    assert verdict.terminate_reason == "merge_failed"
    assert "lane-a" in verdict.summary
    assert "g1" in verdict.summary
    assert "evbundle_6259476d67dd414a8be293d1025ccb8c" in verdict.summary


def test_record_incomplete_termination_is_idempotent(tmp_path):
    """Second call returns the existing verdict without creating a duplicate."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "failed", "prompt": "a", "graph_id": "g1"},
    ])
    v1 = ctrl.record_incomplete_termination("lane-a", "g1")
    v2 = ctrl.record_incomplete_termination("lane-a", "g1")

    assert v1.id == v2.id
    # Only one incomplete_termination verdict should exist.
    incomplete = [
        v for v in ctrl.store.list_verdicts_for_lane("lane-a")
        if v.status == "incomplete_termination"
    ]
    assert len(incomplete) == 1


def test_record_incomplete_termination_default_reason(tmp_path):
    """Default reason is 'terminated_without_merge'."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "failed", "prompt": "a", "graph_id": "g1"},
    ])
    verdict = ctrl.record_incomplete_termination("lane-a", "g1")

    assert verdict.terminate_reason == "terminated_without_merge"


def test_record_incomplete_termination_verdict_id_has_prefix(tmp_path):
    """Verdict ID starts with 'incomplete-term_'."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "failed", "prompt": "a", "graph_id": "g1"},
    ])
    verdict = ctrl.record_incomplete_termination("lane-a", "g1")

    assert verdict.id.startswith("incomplete-term_")


# ---------------------------------------------------------------------------
# ingest_verdict TERMINATE guard
# ---------------------------------------------------------------------------


def test_ingest_verdict_terminate_blocked_when_sibling_open(tmp_path):
    """ingest_verdict raises IncompleteLineageTerminationError for TERMINATE
    when a sibling lineage is still open."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "pending", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    task_id = _open_task(ctrl, "lane-b")
    verdict = ReviewVerdict(
        id="v-terminate-b",
        lane_id="lane-b",
        decision=ReviewDecision.TERMINATE,
        summary="terminate lane-b",
    )

    with pytest.raises(IncompleteLineageTerminationError):
        ctrl.ingest_verdict(task_id, verdict)

    # Verdict must NOT have been persisted.
    with pytest.raises(KeyError):
        ctrl.store.get_verdict("v-terminate-b")


def test_ingest_verdict_terminate_allowed_when_all_siblings_merged(tmp_path):
    """ingest_verdict allows TERMINATE when all sibling lineages are merged."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "merged", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    task_id = _open_task(ctrl, "lane-b")
    verdict = ReviewVerdict(
        id="v-terminate-b-ok",
        lane_id="lane-b",
        decision=ReviewDecision.TERMINATE,
        summary="terminate lane-b safely",
    )

    result = ctrl.ingest_verdict(task_id, verdict)

    # Verdict must be persisted.
    stored = ctrl.store.get_verdict("v-terminate-b-ok")
    assert stored.decision == ReviewDecision.TERMINATE
    # Without require_final_action_approval the adapter returns transition_status="failed".
    assert result.transition_status == "failed"


def test_ingest_verdict_terminate_not_blocked_when_no_graph_id(tmp_path):
    """TERMINATE verdict for a lane with no graph_id skips the guard."""
    ctrl = _make_controller(tmp_path, [
        # No graph_id on this lane.
        {"feature_id": "lane-a", "status": "gated", "prompt": "a"},
    ])
    task_id = _open_task(ctrl, "lane-a")
    verdict = ReviewVerdict(
        id="v-terminate-no-graph",
        lane_id="lane-a",
        decision=ReviewDecision.TERMINATE,
        summary="terminate without graph",
    )

    # Must not raise — no graph_id means no sibling check.
    ctrl.ingest_verdict(task_id, verdict)

    stored = ctrl.store.get_verdict("v-terminate-no-graph")
    assert stored.decision == ReviewDecision.TERMINATE


def test_ingest_verdict_merge_not_blocked_by_guard(tmp_path):
    """MERGE verdicts are never blocked by the termination guard."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "pending", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    task_id = _open_task(ctrl, "lane-b")
    verdict = ReviewVerdict(
        id="v-merge-b",
        lane_id="lane-b",
        decision=ReviewDecision.MERGE,
        summary="merge lane-b",
    )

    # Must not raise even though lane-a is still open.
    ctrl.ingest_verdict(task_id, verdict)

    stored = ctrl.store.get_verdict("v-merge-b")
    assert stored.decision == ReviewDecision.MERGE


def test_ingest_verdict_rework_not_blocked_by_guard(tmp_path):
    """REWORK verdicts are never blocked by the termination guard."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "pending", "prompt": "a", "graph_id": "g1"},
        {"feature_id": "lane-b", "status": "gated", "prompt": "b", "graph_id": "g1"},
    ])
    task_id = _open_task(ctrl, "lane-b")
    verdict = ReviewVerdict(
        id="v-rework-b",
        lane_id="lane-b",
        decision=ReviewDecision.REWORK,
        summary="rework lane-b",
    )

    ctrl.ingest_verdict(task_id, verdict)

    stored = ctrl.store.get_verdict("v-rework-b")
    assert stored.decision == ReviewDecision.REWORK


# ---------------------------------------------------------------------------
# IncompleteLineageTerminationError attributes
# ---------------------------------------------------------------------------


def test_incomplete_lineage_termination_error_attributes():
    """IncompleteLineageTerminationError exposes lane_id, graph_id, and lists."""
    err = IncompleteLineageTerminationError(
        "lane-x",
        "graph-y",
        open_lineages=["lane-a", "lane-b"],
        unmerged_lineages=["lane-c"],
    )

    assert err.lane_id == "lane-x"
    assert err.graph_id == "graph-y"
    assert err.open_lineages == ["lane-a", "lane-b"]
    assert err.unmerged_lineages == ["lane-c"]
    assert "lane-x" in str(err)
    assert "graph-y" in str(err)


def test_incomplete_lineage_termination_error_is_runtime_error():
    """IncompleteLineageTerminationError is a RuntimeError subclass."""
    err = IncompleteLineageTerminationError(
        "lane-x", "graph-y", open_lineages=[], unmerged_lineages=["lane-z"]
    )
    assert isinstance(err, RuntimeError)
