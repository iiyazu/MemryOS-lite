"""Tests for review_plane merge guards (evbundle_6259476d67dd414a8be293d1025ccb8c).

Covers:
- check_lineage_merge_completeness classifies lanes correctly.
- assert_termination_safe raises IncompleteLineageTerminationError when
  sibling lineages are open or already terminated without a merge verdict.
- assert_termination_safe passes when all siblings are merged.
- ingest_verdict blocks TERMINATE verdicts when termination is unsafe.
- ingest_verdict allows TERMINATE verdicts when all siblings are merged.
- record_incomplete_termination is idempotent.
- assemble_evidence_bundle calls record_incomplete_termination for failed
  lineages that lack a merge verdict and includes the signal in signal_refs.
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
from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_lanes(path: Path, lanes: list[dict]) -> None:
    path.write_text(json.dumps({"lanes": lanes}, indent=2), encoding="utf-8")


def _make_controller(tmp_path: Path, lanes: list[dict]) -> ReviewPlaneController:
    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(lanes_path, lanes)
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
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "merged", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "merged", "prompt": ""},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")
    assert isinstance(report, LineageMergeReport)
    assert report.is_complete
    assert set(report.merged_lineages) == {"lane-a", "lane-b"}
    assert report.terminated_without_merge == []
    assert report.open_lineages == []


def test_check_completeness_failed_without_merge(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "merged", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "failed", "prompt": ""},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")
    assert not report.is_complete
    assert "lane-b" in report.terminated_without_merge
    assert "lane-a" in report.merged_lineages


def test_check_completeness_open_lane(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "merged", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "gated", "prompt": ""},
    ])
    report = ctrl.check_lineage_merge_completeness("g1")
    assert not report.is_complete
    assert "lane-b" in report.open_lineages


def test_check_completeness_failed_with_merge_verdict(tmp_path):
    """A failed lane that has a MERGE verdict is classified as merged."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "failed", "prompt": ""},
    ])
    # Inject a merge verdict directly into the store.
    verdict = ReviewVerdict(
        id="v-merge-1",
        lane_id="lane-a",
        decision=ReviewDecision.MERGE,
        summary="merged via patch-forward",
        status="finalized",
    )
    ctrl.store.save_verdict(verdict)

    report = ctrl.check_lineage_merge_completeness("g1")
    assert "lane-a" in report.merged_lineages
    assert report.terminated_without_merge == []


# ---------------------------------------------------------------------------
# assert_termination_safe
# ---------------------------------------------------------------------------

def test_assert_termination_safe_passes_when_all_siblings_merged(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "gated", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "merged", "prompt": ""},
    ])
    # lane-a is the one being terminated; lane-b is merged — should not raise.
    ctrl.assert_termination_safe("lane-a", "g1")  # no exception


def test_assert_termination_safe_raises_when_sibling_is_open(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "gated", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "dispatched", "prompt": ""},
    ])
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-a", "g1")
    err = exc_info.value
    assert err.lane_id == "lane-a"
    assert err.graph_id == "g1"
    assert "lane-b" in err.open_lineages


def test_assert_termination_safe_raises_when_sibling_terminated_without_merge(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "gated", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "failed", "prompt": ""},
    ])
    with pytest.raises(IncompleteLineageTerminationError) as exc_info:
        ctrl.assert_termination_safe("lane-a", "g1")
    err = exc_info.value
    assert "lane-b" in err.unmerged_lineages


def test_assert_termination_safe_single_lane_graph_passes(tmp_path):
    """A single-lane graph has no siblings; termination is always safe."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "gated", "prompt": ""},
    ])
    ctrl.assert_termination_safe("lane-a", "g1")  # no exception


# ---------------------------------------------------------------------------
# ingest_verdict — TERMINATE guard
# ---------------------------------------------------------------------------

def test_ingest_terminate_verdict_blocked_when_sibling_open(tmp_path):
    """ingest_verdict must raise before persisting when termination is unsafe."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "gated", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "dispatched", "prompt": ""},
    ])
    task_id = _open_task(ctrl, "lane-a")
    verdict = ReviewVerdict(
        id="v-term-1",
        lane_id="lane-a",
        decision=ReviewDecision.TERMINATE,
        summary="terminate lane-a",
    )
    with pytest.raises(IncompleteLineageTerminationError):
        ctrl.ingest_verdict(task_id, verdict)

    # Verdict must NOT have been persisted.
    verdicts = ctrl.store.list_verdicts_for_lane("lane-a")
    assert not any(v.id == "v-term-1" for v in verdicts)


def test_ingest_terminate_verdict_allowed_when_all_siblings_merged(tmp_path):
    """ingest_verdict must allow TERMINATE when all siblings are merged."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "gated", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "merged", "prompt": ""},
    ])
    task_id = _open_task(ctrl, "lane-a")
    verdict = ReviewVerdict(
        id="v-term-2",
        lane_id="lane-a",
        decision=ReviewDecision.TERMINATE,
        summary="terminate lane-a safely",
    )
    # Should not raise.
    ctrl.ingest_verdict(task_id, verdict)

    verdicts = ctrl.store.list_verdicts_for_lane("lane-a")
    assert any(v.id == "v-term-2" for v in verdicts)


def test_ingest_terminate_verdict_no_graph_id_skips_guard(tmp_path):
    """Lanes without a graph_id bypass the termination guard (no siblings)."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "status": "gated", "prompt": ""},
    ])
    task_id = _open_task(ctrl, "lane-a")
    verdict = ReviewVerdict(
        id="v-term-3",
        lane_id="lane-a",
        decision=ReviewDecision.TERMINATE,
        summary="terminate standalone lane",
    )
    ctrl.ingest_verdict(task_id, verdict)  # no exception

    verdicts = ctrl.store.list_verdicts_for_lane("lane-a")
    assert any(v.id == "v-term-3" for v in verdicts)


def test_ingest_non_terminate_verdict_not_guarded(tmp_path):
    """MERGE verdicts are never blocked by the termination guard."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "reviewed", "prompt": ""},
        {"feature_id": "lane-b", "graph_id": "g1", "status": "dispatched", "prompt": ""},
    ])
    task_id = _open_task(ctrl, "lane-a")
    verdict = ReviewVerdict(
        id="v-merge-ok",
        lane_id="lane-a",
        decision=ReviewDecision.MERGE,
        summary="merge lane-a",
    )
    ctrl.ingest_verdict(task_id, verdict)  # no exception

    verdicts = ctrl.store.list_verdicts_for_lane("lane-a")
    assert any(v.id == "v-merge-ok" for v in verdicts)


# ---------------------------------------------------------------------------
# record_incomplete_termination
# ---------------------------------------------------------------------------

def test_record_incomplete_termination_persists_verdict(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "failed", "prompt": ""},
    ])
    verdict = ctrl.record_incomplete_termination("lane-a", "g1", reason="merge_failed")
    assert verdict.decision == ReviewDecision.TERMINATE
    assert verdict.status == "incomplete_termination"
    assert "lane-a" in verdict.summary
    assert "evbundle_6259476d67dd414a8be293d1025ccb8c" in verdict.summary


def test_record_incomplete_termination_is_idempotent(tmp_path):
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "failed", "prompt": ""},
    ])
    v1 = ctrl.record_incomplete_termination("lane-a", "g1")
    v2 = ctrl.record_incomplete_termination("lane-a", "g1")
    assert v1.id == v2.id

    incomplete = [
        v for v in ctrl.store.list_verdicts_for_lane("lane-a")
        if v.status == "incomplete_termination"
    ]
    assert len(incomplete) == 1


# ---------------------------------------------------------------------------
# assemble_evidence_bundle — incomplete-termination signal
# ---------------------------------------------------------------------------

def test_assemble_evidence_bundle_records_incomplete_termination(tmp_path):
    """Failed lineages without a merge verdict get an incomplete-termination signal."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "merged", "prompt": ""},
        {
            "feature_id": "lane-b",
            "graph_id": "g1",
            "status": "failed",
            "failure_reason": "merge_failed",
            "prompt": "",
        },
    ])
    bundle = ctrl.assemble_evidence_bundle("g1")

    # signal_refs must contain both the negative signal and the
    # incomplete-termination signal for lane-b.
    negative_refs = [r for r in bundle.signal_refs if r.startswith("negative:lane:lane-b")]
    incomplete_refs = [r for r in bundle.signal_refs if r.startswith("incomplete_termination:lane:lane-b")]
    assert negative_refs, "expected a negative signal ref for lane-b"
    assert incomplete_refs, "expected an incomplete-termination signal ref for lane-b"

    # primary_refs must include an incomplete_termination entry.
    incomplete_primary = [
        p for p in bundle.primary_refs
        if p.get("type") == "incomplete_termination" and p.get("lane_id") == "lane-b"
    ]
    assert incomplete_primary
    assert incomplete_primary[0]["evidence_bundle_ref"] == "evbundle_6259476d67dd414a8be293d1025ccb8c"

    # The verdict must have been persisted in the store.
    incomplete_verdicts = [
        v for v in ctrl.store.list_verdicts_for_lane("lane-b")
        if v.status == "incomplete_termination"
    ]
    assert incomplete_verdicts


def test_assemble_evidence_bundle_no_incomplete_signal_when_merged(tmp_path):
    """Lanes that merged cleanly must not get an incomplete-termination signal."""
    ctrl = _make_controller(tmp_path, [
        {"feature_id": "lane-a", "graph_id": "g1", "status": "merged", "prompt": ""},
    ])
    bundle = ctrl.assemble_evidence_bundle("g1")

    incomplete_refs = [r for r in bundle.signal_refs if "incomplete_termination" in r]
    assert not incomplete_refs


def test_assemble_evidence_bundle_no_duplicate_incomplete_signal(tmp_path):
    """Calling assemble_evidence_bundle twice must not duplicate the signal."""
    ctrl = _make_controller(tmp_path, [
        {
            "feature_id": "lane-a",
            "graph_id": "g1",
            "status": "failed",
            "failure_reason": "gate_failed",
            "prompt": "",
        },
    ])
    ctrl.assemble_evidence_bundle("g1")
    bundle2 = ctrl.assemble_evidence_bundle("g1")

    incomplete_verdicts = [
        v for v in ctrl.store.list_verdicts_for_lane("lane-a")
        if v.status == "incomplete_termination"
    ]
    assert len(incomplete_verdicts) == 1, "record_incomplete_termination must be idempotent"

    incomplete_refs = [r for r in bundle2.signal_refs if "incomplete_termination" in r]
    assert len(incomplete_refs) == 1
