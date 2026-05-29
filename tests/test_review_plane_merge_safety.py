"""Tests for graph lineage merge scenarios in ReviewPlaneController.

Covers the merge guards introduced in evbundle_6259476d67dd414a8be293d1025ccb8c:

- check_lineage_merge_completeness: classifies each lane as merged /
  terminated_without_merge / open.
- assert_termination_safe: blocks TERMINATE verdicts when siblings are open or
  already terminated without a merge verdict.
- record_incomplete_termination: writes a synthetic incomplete-termination
  signal that is idempotent and picked up by assemble_evidence_bundle.

Test matrix
-----------
1.  Normal merge flow — single lane, MERGE verdict → is_complete True.
2.  Multiple lineages all merged → is_complete True.
3.  Multiple lineages, one open → is_complete False, open_lineages populated.
4.  Multiple lineages, one terminated without merge → terminated_without_merge
    populated, is_complete False.
5.  assert_termination_safe passes when all siblings are merged.
6.  assert_termination_safe raises when a sibling is still open.
7.  assert_termination_safe raises when a sibling already terminated without
    merge.
8.  assert_termination_safe excludes the lane being terminated from sibling
    checks (self-exclusion).
9.  record_incomplete_termination persists a synthetic TERMINATE verdict with
    status="incomplete_termination".
10. record_incomplete_termination is idempotent — second call returns the same
    verdict without creating a duplicate.
11. Incomplete-termination signal appears in assemble_evidence_bundle
    signal_refs and primary_refs.
12. Lineage that terminates without merge is NOT counted as merged even if the
    lane status is "failed" (no merge verdict present).
13. Patch-forward descendant with merged status is counted as merged.
14. Multi-hop patch-forward chain — all hops merged → is_complete True.
15. Graph with no lanes → is_complete True (vacuously complete).
16. Lane referenced in graph but not yet projected (missing from lane file) →
    counted as open.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.platform.review_plane import (
    IncompleteLineageTerminationError,
    LineageMergeReport,
    ReviewPlaneController,
)
from xmuse_core.structuring.models import (
    ReviewDecision,
    ReviewVerdict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_controller(tmp_path: Path, lanes: list[dict]) -> ReviewPlaneController:
    """Build a ReviewPlaneController backed by tmp_path with the given lanes."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    store_path = tmp_path / "review_plane.json"
    final_actions_path = tmp_path / "final_actions.json"
    return ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=store_path,
        final_actions_path=final_actions_path,
    )


def _merged_lane(feature_id: str, graph_id: str, **extra) -> dict:
    return {
        "feature_id": feature_id,
        "status": "merged",
        "prompt": f"work for {feature_id}",
        "worktree": "/tmp/wt",
        "graph_id": graph_id,
        **extra,
    }


def _failed_lane(feature_id: str, graph_id: str, reason: str = "exec_failed", **extra) -> dict:
    return {
        "feature_id": feature_id,
        "status": "failed",
        "prompt": f"work for {feature_id}",
        "worktree": "/tmp/wt",
        "graph_id": graph_id,
        "failure_reason": reason,
        **extra,
    }


def _open_lane(feature_id: str, graph_id: str, status: str = "pending", **extra) -> dict:
    return {
        "feature_id": feature_id,
        "status": status,
        "prompt": f"work for {feature_id}",
        "worktree": "/tmp/wt",
        "graph_id": graph_id,
        **extra,
    }


def _save_merge_verdict(ctrl: ReviewPlaneController, lane_id: str, verdict_id: str) -> None:
    """Persist a finalized MERGE verdict for lane_id."""
    verdict = ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=ReviewDecision.MERGE,
        status="finalized",
        summary="Looks good.",
    )
    ctrl.store.save_verdict(verdict)


# ---------------------------------------------------------------------------
# 1. Normal merge flow — single lane with MERGE verdict
# ---------------------------------------------------------------------------


def test_single_lane_merge_flow_is_complete(tmp_path):
    """A single lane with a finalized MERGE verdict produces is_complete=True."""
    ctrl = _make_controller(tmp_path, [_merged_lane("lane-1", "graph-1")])
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert isinstance(report, LineageMergeReport)
    assert report.graph_id == "graph-1"
    assert "lane-1" in report.merged_lineages
    assert report.terminated_without_merge == []
    assert report.open_lineages == []
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# 2. Multiple lineages all merged
# ---------------------------------------------------------------------------


def test_multiple_lineages_all_merged_is_complete(tmp_path):
    """All lanes merged → is_complete True, no open or unmerged lineages."""
    lanes = [
        _merged_lane("lane-1", "graph-1"),
        _merged_lane("lane-2", "graph-1"),
        _merged_lane("lane-3", "graph-1"),
    ]
    ctrl = _make_controller(tmp_path, lanes)
    for i in range(1, 4):
        _save_merge_verdict(ctrl, f"lane-{i}", f"verdict-{i}")

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert set(report.merged_lineages) == {"lane-1", "lane-2", "lane-3"}
    assert report.terminated_without_merge == []
    assert report.open_lineages == []
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# 3. Multiple lineages, one still open
# ---------------------------------------------------------------------------


def test_multiple_lineages_one_open_is_not_complete(tmp_path):
    """An open sibling lane makes is_complete False."""
    lanes = [
        _merged_lane("lane-1", "graph-1"),
        _open_lane("lane-2", "graph-1", status="dispatched"),
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.merged_lineages
    assert "lane-2" in report.open_lineages
    assert report.terminated_without_merge == []
    assert report.is_complete is False


# ---------------------------------------------------------------------------
# 4. Multiple lineages, one terminated without merge
# ---------------------------------------------------------------------------


def test_multiple_lineages_one_terminated_without_merge(tmp_path):
    """A failed lane without a MERGE verdict appears in terminated_without_merge."""
    lanes = [
        _merged_lane("lane-1", "graph-1"),
        _failed_lane("lane-2", "graph-1", reason="gate_failed"),
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")
    # lane-2 has no merge verdict — only a failed status.

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.merged_lineages
    assert "lane-2" in report.terminated_without_merge
    assert report.open_lineages == []
    assert report.is_complete is False


# ---------------------------------------------------------------------------
# 5. assert_termination_safe passes when all siblings are merged
# ---------------------------------------------------------------------------


def test_assert_termination_safe_passes_when_siblings_merged(tmp_path):
    """No exception when all sibling lanes are merged."""
    lanes = [
        _merged_lane("lane-1", "graph-1"),
        _open_lane("lane-2", "graph-1", status="pending"),  # the lane being terminated
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")

    # lane-2 is the one being terminated; lane-1 is merged → safe.
    ctrl.assert_termination_safe("lane-2", "graph-1")  # must not raise


# ---------------------------------------------------------------------------
# 6. assert_termination_safe raises when a sibling is still open
# ---------------------------------------------------------------------------


def test_assert_termination_safe_raises_for_open_sibling(tmp_path):
    """IncompleteLineageTerminationError raised when a sibling is still open."""
    lanes = [
        _open_lane("lane-1", "graph-1", status="dispatched"),  # open sibling
        _open_lane("lane-2", "graph-1", status="pending"),     # lane being terminated
    ]
    ctrl = _make_controller(tmp_path, lanes)

    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-2", "graph-1")

    err = exc_info.value
    assert err.lane_id == "lane-2"
    assert err.graph_id == "graph-1"
    assert "lane-1" in err.open_lineages
    assert err.unmerged_lineages == []


# ---------------------------------------------------------------------------
# 7. assert_termination_safe raises when a sibling already terminated without merge
# ---------------------------------------------------------------------------


def test_assert_termination_safe_raises_for_unmerged_sibling(tmp_path):
    """IncompleteLineageTerminationError raised when a sibling terminated without merge."""
    lanes = [
        _failed_lane("lane-1", "graph-1", reason="exec_failed"),  # unmerged sibling
        _open_lane("lane-2", "graph-1", status="pending"),         # lane being terminated
    ]
    ctrl = _make_controller(tmp_path, lanes)
    # lane-1 has no merge verdict.

    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-2", "graph-1")

    err = exc_info.value
    assert "lane-1" in err.unmerged_lineages
    assert err.open_lineages == []


# ---------------------------------------------------------------------------
# 8. assert_termination_safe self-exclusion
# ---------------------------------------------------------------------------


def test_assert_termination_safe_excludes_self_from_sibling_checks(tmp_path):
    """The lane being terminated is excluded from the open/unmerged sibling lists."""
    # lane-1 is the only lane in the graph and it is the one being terminated.
    # It is currently open (pending), but since it is the terminating lane itself
    # it should not block its own termination.
    lanes = [_open_lane("lane-1", "graph-1", status="pending")]
    ctrl = _make_controller(tmp_path, lanes)

    # Should not raise — lane-1 is excluded from sibling checks.
    ctrl.assert_termination_safe("lane-1", "graph-1")


# ---------------------------------------------------------------------------
# 9. record_incomplete_termination persists a synthetic verdict
# ---------------------------------------------------------------------------


def test_record_incomplete_termination_persists_verdict(tmp_path):
    """record_incomplete_termination writes a synthetic TERMINATE verdict."""
    lanes = [_failed_lane("lane-1", "graph-1")]
    ctrl = _make_controller(tmp_path, lanes)

    verdict = ctrl.record_incomplete_termination("lane-1", "graph-1", reason="gate_failed")

    assert verdict.lane_id == "lane-1"
    assert verdict.decision == ReviewDecision.TERMINATE
    assert verdict.status == "incomplete_termination"
    assert verdict.terminate_reason == "gate_failed"
    assert "lane-1" in verdict.summary
    assert "graph-1" in verdict.summary
    assert "evbundle_6259476d67dd414a8be293d1025ccb8c" in verdict.summary

    # Verify it is retrievable from the store.
    stored = ctrl.store.get_verdict(verdict.id)
    assert stored.id == verdict.id
    assert stored.status == "incomplete_termination"


# ---------------------------------------------------------------------------
# 10. record_incomplete_termination is idempotent
# ---------------------------------------------------------------------------


def test_record_incomplete_termination_is_idempotent(tmp_path):
    """Calling record_incomplete_termination twice returns the same verdict."""
    lanes = [_failed_lane("lane-1", "graph-1")]
    ctrl = _make_controller(tmp_path, lanes)

    first = ctrl.record_incomplete_termination("lane-1", "graph-1")
    second = ctrl.record_incomplete_termination("lane-1", "graph-1")

    assert first.id == second.id
    # Only one incomplete-termination verdict should exist.
    incomplete = [
        v for v in ctrl.store.list_verdicts_for_lane("lane-1")
        if v.status == "incomplete_termination"
    ]
    assert len(incomplete) == 1


# ---------------------------------------------------------------------------
# 11. Incomplete-termination signal appears in assemble_evidence_bundle
# ---------------------------------------------------------------------------


def test_incomplete_termination_signal_in_evidence_bundle(tmp_path):
    """record_incomplete_termination signal is picked up by assemble_evidence_bundle."""
    lanes = [
        _merged_lane("lane-1", "graph-1"),
        _failed_lane("lane-2", "graph-1", reason="exec_failed"),
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")
    ctrl.record_incomplete_termination("lane-2", "graph-1", reason="exec_failed")

    bundle = ctrl.assemble_evidence_bundle("graph-1")

    # lane-2 is a failed lineage → negative signal ref.
    assert any("lane-2" in ref for ref in bundle.signal_refs)
    neg_primaries = [r for r in bundle.primary_refs if r.get("type") == "negative_signal"]
    assert any(r["lane_id"] == "lane-2" for r in neg_primaries)


# ---------------------------------------------------------------------------
# 12. Failed lane without merge verdict is NOT counted as merged
# ---------------------------------------------------------------------------


def test_failed_lane_without_merge_verdict_is_not_merged(tmp_path):
    """A lane with status=failed and no MERGE verdict goes to terminated_without_merge."""
    lanes = [_failed_lane("lane-1", "graph-1", reason="gate_failed")]
    ctrl = _make_controller(tmp_path, lanes)
    # Deliberately do NOT save a merge verdict.

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.terminated_without_merge
    assert report.merged_lineages == []
    assert report.is_complete is False


# ---------------------------------------------------------------------------
# 13. Patch-forward descendant with merged status is counted as merged
# ---------------------------------------------------------------------------


def test_patch_forward_descendant_merged_counts_as_merged(tmp_path):
    """A patch-forward descendant with status=merged is classified as merged."""
    lanes = [
        _failed_lane("lane-1", "graph-1", reason="patch_forward_requested"),
        {
            "feature_id": "lane-1-patch",
            "status": "merged",
            "prompt": "patch forward",
            "worktree": "/tmp/wt",
            "source_lane_id": "lane-1",
            # No graph_id — discovered via source_lane_id closure.
        },
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _save_merge_verdict(ctrl, "lane-1-patch", "verdict-patch-1")

    report = ctrl.check_lineage_merge_completeness("graph-1")

    # lane-1 failed without merge verdict → terminated_without_merge.
    assert "lane-1" in report.terminated_without_merge
    # lane-1-patch is a descendant and is merged.
    assert "lane-1-patch" in report.merged_lineages


# ---------------------------------------------------------------------------
# 14. Multi-hop patch-forward chain — all hops merged → is_complete True
# ---------------------------------------------------------------------------


def test_multi_hop_patch_forward_all_merged_is_complete(tmp_path):
    """A two-hop patch-forward chain where every hop is merged → is_complete True."""
    lanes = [
        _merged_lane("lane-1", "graph-1"),
        {
            "feature_id": "lane-1-patch",
            "status": "merged",
            "prompt": "patch hop 1",
            "worktree": "/tmp/wt",
            "source_lane_id": "lane-1",
        },
        {
            "feature_id": "lane-1-patch-2",
            "status": "merged",
            "prompt": "patch hop 2",
            "worktree": "/tmp/wt",
            "source_lane_id": "lane-1-patch",
        },
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")
    _save_merge_verdict(ctrl, "lane-1-patch", "verdict-patch-1")
    _save_merge_verdict(ctrl, "lane-1-patch-2", "verdict-patch-2")

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert set(report.merged_lineages) == {"lane-1", "lane-1-patch", "lane-1-patch-2"}
    assert report.terminated_without_merge == []
    assert report.open_lineages == []
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# 15. Graph with no lanes → is_complete True (vacuously complete)
# ---------------------------------------------------------------------------


def test_empty_graph_is_complete(tmp_path):
    """A graph with no lanes is vacuously complete."""
    ctrl = _make_controller(tmp_path, [])

    report = ctrl.check_lineage_merge_completeness("graph-empty")

    assert report.graph_id == "graph-empty"
    assert report.merged_lineages == []
    assert report.terminated_without_merge == []
    assert report.open_lineages == []
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# 16. All open statuses are classified as open lineages
# ---------------------------------------------------------------------------


def test_all_open_statuses_classified_as_open(tmp_path):
    """Every status in _OPEN_STATUSES is classified as an open lineage."""
    open_statuses = [
        "pending", "dispatched", "executed", "gated",
        "reviewed", "reworking", "awaiting_final_action", "rejected",
    ]
    for status in open_statuses:
        lanes = [{
            "feature_id": "lane-1",
            "status": status,
            "prompt": "work",
            "worktree": "/tmp/wt",
            "graph_id": "graph-1",
        }]
        ctrl = _make_controller(tmp_path / status, lanes)

        report = ctrl.check_lineage_merge_completeness("graph-1")

        assert "lane-1" in report.open_lineages, (
            f"Expected lane-1 to be open for status={status!r}"
        )
        assert report.is_complete is False


# ---------------------------------------------------------------------------
# Merge failure recovery: ingest_verdict after failed merge attempt
# ---------------------------------------------------------------------------


def test_merge_failure_recovery_via_rework_then_merge(tmp_path):
    """A lane that fails review and is reworked can still reach a merged state."""
    lanes = [_open_lane("lane-1", "graph-1", status="reviewed")]
    ctrl = _make_controller(tmp_path, lanes)

    # Open a review task.
    task = ctrl.open_review_task("lane-1")

    # First verdict: REWORK (review failure).
    # adapt_review_verdict maps REWORK → transition_status="rejected".
    rework_verdict = ReviewVerdict(
        id="verdict-rework-1",
        lane_id="lane-1",
        decision=ReviewDecision.REWORK,
        status="finalized",
        summary="Needs changes.",
    )
    result = ctrl.ingest_verdict(task.task_id, rework_verdict)
    assert result.transition_status == "rejected"

    # Simulate lane going through rework cycle and reaching reviewed again.
    lanes_path = tmp_path / "feature_lanes.json"
    data = json.loads(lanes_path.read_text())
    data["lanes"][0]["status"] = "reviewed"
    lanes_path.write_text(json.dumps(data))

    # Open a new task for the reworked lane.
    task2 = ctrl.open_review_task("lane-1")

    # Second verdict: MERGE (recovery).
    # adapt_review_verdict maps MERGE (no final-action approval) → "reviewed".
    merge_verdict = ReviewVerdict(
        id="verdict-merge-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        status="finalized",
        summary="All good now.",
    )
    result2 = ctrl.ingest_verdict(task2.task_id, merge_verdict)
    assert result2.transition_status == "reviewed"

    # Simulate the state machine applying the merge transition.
    data = json.loads(lanes_path.read_text())
    data["lanes"][0]["status"] = "merged"
    lanes_path.write_text(json.dumps(data))

    # Now the lineage should be complete.
    report = ctrl.check_lineage_merge_completeness("graph-1")
    assert "lane-1" in report.merged_lineages
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# Edge case: lane with status in _MERGED_STATUSES but no explicit verdict
# ---------------------------------------------------------------------------


def test_lane_with_merged_status_but_no_verdict_counts_as_merged(tmp_path):
    """A lane with status='merged' is classified as merged even without a verdict."""
    lanes = [_merged_lane("lane-1", "graph-1")]
    ctrl = _make_controller(tmp_path, lanes)
    # No verdict saved — status alone is sufficient.

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.merged_lineages
    assert report.is_complete is True


def test_lane_with_done_status_counts_as_merged(tmp_path):
    """A lane with status='done' is classified as merged."""
    lanes = [{
        "feature_id": "lane-1",
        "status": "done",
        "prompt": "work",
        "worktree": "/tmp/wt",
        "graph_id": "graph-1",
    }]
    ctrl = _make_controller(tmp_path, lanes)

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.merged_lineages
    assert report.is_complete is True


def test_lane_with_completed_status_counts_as_merged(tmp_path):
    """A lane with status='completed' is classified as merged."""
    lanes = [{
        "feature_id": "lane-1",
        "status": "completed",
        "prompt": "work",
        "worktree": "/tmp/wt",
        "graph_id": "graph-1",
    }]
    ctrl = _make_controller(tmp_path, lanes)

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.merged_lineages
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# Edge case: failed lane WITH a merge verdict is counted as merged
# ---------------------------------------------------------------------------


def test_failed_lane_with_merge_verdict_counts_as_merged(tmp_path):
    """A lane with status=failed but a finalized MERGE verdict is still merged."""
    lanes = [_failed_lane("lane-1", "graph-1", reason="exec_failed")]
    ctrl = _make_controller(tmp_path, lanes)
    # Save a MERGE verdict — the merge happened despite the failed status.
    _save_merge_verdict(ctrl, "lane-1", "verdict-1")

    report = ctrl.check_lineage_merge_completeness("graph-1")

    assert "lane-1" in report.merged_lineages
    assert report.terminated_without_merge == []
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# IncompleteLineageTerminationError attributes
# ---------------------------------------------------------------------------


def test_incomplete_lineage_termination_error_attributes(tmp_path):
    """IncompleteLineageTerminationError exposes lane_id, graph_id, and lists."""
    lanes = [
        _open_lane("lane-sibling", "graph-1", status="dispatched"),
        _open_lane("lane-target", "graph-1", status="pending"),
    ]
    ctrl = _make_controller(tmp_path, lanes)

    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-target", "graph-1")

    err = exc_info.value
    assert err.lane_id == "lane-target"
    assert err.graph_id == "graph-1"
    assert isinstance(err.open_lineages, list)
    assert isinstance(err.unmerged_lineages, list)
    assert "lane-sibling" in err.open_lineages
    # Error message should mention the lane and graph.
    assert "lane-target" in str(err)
    assert "graph-1" in str(err)


# ---------------------------------------------------------------------------
# assert_termination_safe with both open and unmerged siblings
# ---------------------------------------------------------------------------


def test_assert_termination_safe_raises_with_both_open_and_unmerged(tmp_path):
    """Error is raised and both open and unmerged siblings are reported."""
    lanes = [
        _open_lane("lane-open", "graph-1", status="dispatched"),
        _failed_lane("lane-unmerged", "graph-1", reason="gate_failed"),
        _open_lane("lane-target", "graph-1", status="pending"),
    ]
    ctrl = _make_controller(tmp_path, lanes)
    # lane-unmerged has no merge verdict.

    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-target", "graph-1")

    err = exc_info.value
    assert "lane-open" in err.open_lineages
    assert "lane-unmerged" in err.unmerged_lineages
