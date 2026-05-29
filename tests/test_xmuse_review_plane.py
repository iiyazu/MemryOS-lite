"""
Focused tests for the review_plane track of xmuse self-evolution.

Covers:
- ReviewTask is created when a lane enters review
- open_review_task is idempotent for pending tasks
- ReviewVerdict is persisted with task_id lineage stamp
- Task transitions to verdict_emitted after ingest_verdict
- ingest_verdict returns VerdictAdapterResult with correct transition_status
- merge verdict without final-action approval produces reviewed transition
- merge verdict with final-action approval produces final_action hold
- rework verdict produces rejected transition
- patch-forward verdict produces patch_lane (no transition_status)
- terminate verdict with final-action approval produces final_action hold
- verdict_lineage_for_lane returns task→verdict chain
- has_verdict_lineage is True after a finalized verdict
- has_verdict_lineage is False before any verdict
- cancel_review_task marks task as cancelled
- multiple verdicts for same lane all appear in lineage
- patch-forward verdict preserves source_lane_id in patch_lane
- final-action hold is persisted to FinalActionGateStore on ingest
- requeued lane preserves original verdict relation in lineage
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.review_plane import ReviewPlaneController
from xmuse_core.structuring.models import (
    ReviewDecision,
    ReviewTask,
    ReviewTaskStatus,
    ReviewVerdict,
)
from xmuse_core.structuring.verdict_store import VerdictStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_lanes(tmp_path: Path, lanes: list[dict]) -> Path:
    lanes_path = tmp_path / "feature_lanes.json"
    _write_json(lanes_path, {"lanes": lanes})
    return lanes_path


def _make_controller(
    tmp_path: Path,
    lanes: list[dict],
    *,
    require_final_action_approval: bool = False,
) -> ReviewPlaneController:
    lanes_path = _make_lanes(tmp_path, lanes)
    store_path = tmp_path / "review_plane.json"
    final_actions_path = tmp_path / "final_actions.json"
    return ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=store_path,
        final_actions_path=final_actions_path,
        require_final_action_approval=require_final_action_approval,
    )


def _gated_lane(lane_id: str, **extra) -> dict:
    return {
        "feature_id": lane_id,
        "status": "gated",
        "prompt": f"Implement {lane_id}",
        "gate_passed": True,
        **extra,
    }


def _merge_verdict(lane_id: str, verdict_id: str = "verdict-1") -> ReviewVerdict:
    return ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=ReviewDecision.MERGE,
        summary="No findings. Ready to merge.",
        evidence_refs=[f"gate://{lane_id}"],
    )


# ---------------------------------------------------------------------------
# ReviewTask creation
# ---------------------------------------------------------------------------


def test_open_review_task_creates_pending_task(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-a")])

    task = controller.open_review_task("lane-a")

    assert isinstance(task, ReviewTask)
    assert task.lane_id == "lane-a"
    assert task.status == ReviewTaskStatus.PENDING
    assert task.task_id.startswith("rtask_")
    assert task.created_at is not None


def test_open_review_task_captures_lane_prompt(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-b", prompt="Build the widget")],
    )

    task = controller.open_review_task("lane-b")

    assert task.lane_prompt == "Build the widget"


def test_open_review_task_captures_graph_and_resolution_ids(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-c", graph_id="graph-1", resolution_id="res-1")],
    )

    task = controller.open_review_task("lane-c")

    assert task.graph_id == "graph-1"
    assert task.resolution_id == "res-1"


def test_open_review_task_is_idempotent_for_pending_task(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-d")])

    task1 = controller.open_review_task("lane-d")
    task2 = controller.open_review_task("lane-d")

    assert task1.task_id == task2.task_id


def test_open_review_task_persists_to_store(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-e")])

    task = controller.open_review_task("lane-e")

    stored = controller.store.list_tasks_for_lane("lane-e")
    assert any(t.task_id == task.task_id for t in stored)


def test_open_review_task_records_gate_report_ref(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-f")])

    task = controller.open_review_task("lane-f", gate_report_ref="logs/gates/lane-f/report.json")

    assert task.gate_report_ref == "logs/gates/lane-f/report.json"


# ---------------------------------------------------------------------------
# Verdict ingestion – merge (no final-action approval)
# ---------------------------------------------------------------------------


def test_ingest_merge_verdict_returns_reviewed_transition(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-merge")],
        require_final_action_approval=False,
    )
    task = controller.open_review_task("lane-merge")

    result = controller.ingest_verdict(task.task_id, _merge_verdict("lane-merge"))

    assert result.transition_status == "reviewed"
    assert result.final_action is None
    assert result.patch_lane is None


def test_ingest_verdict_persists_verdict_with_task_id(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-persist")])
    task = controller.open_review_task("lane-persist")

    controller.ingest_verdict(task.task_id, _merge_verdict("lane-persist", "verdict-persist"))

    verdict = controller.store.get_verdict("verdict-persist")
    assert verdict.task_id == task.task_id
    assert verdict.lane_id == "lane-persist"


def test_ingest_verdict_stamps_created_at_when_absent(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-ts")])
    task = controller.open_review_task("lane-ts")
    verdict = ReviewVerdict(
        id="verdict-ts",
        lane_id="lane-ts",
        decision=ReviewDecision.MERGE,
        summary="ok",
    )

    controller.ingest_verdict(task.task_id, verdict)

    stored = controller.store.get_verdict("verdict-ts")
    assert stored.created_at is not None


def test_ingest_verdict_transitions_task_to_verdict_emitted(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-status")])
    task = controller.open_review_task("lane-status")

    controller.ingest_verdict(task.task_id, _merge_verdict("lane-status", "verdict-status"))

    updated_task = controller.store.get_task(task.task_id)
    assert updated_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert updated_task.verdict_id == "verdict-status"
    assert updated_task.updated_at is not None


# ---------------------------------------------------------------------------
# Verdict ingestion – merge with final-action approval
# ---------------------------------------------------------------------------


def test_ingest_merge_verdict_with_final_action_approval_produces_hold(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-hold")],
        require_final_action_approval=True,
    )
    task = controller.open_review_task("lane-hold")

    result = controller.ingest_verdict(task.task_id, _merge_verdict("lane-hold", "verdict-hold"))

    assert result.transition_status is None
    assert result.final_action is not None
    assert result.final_action.action == "merge"
    assert result.final_action.verdict_id == "verdict-hold"


def test_ingest_merge_verdict_persists_final_action_hold(tmp_path: Path) -> None:
    final_actions_path = tmp_path / "final_actions.json"
    lanes_path = _make_lanes(tmp_path, [_gated_lane("lane-hold-persist")])
    controller = ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=tmp_path / "review_plane.json",
        final_actions_path=final_actions_path,
        require_final_action_approval=True,
    )
    task = controller.open_review_task("lane-hold-persist")

    controller.ingest_verdict(
        task.task_id,
        _merge_verdict("lane-hold-persist", "verdict-hold-persist"),
    )

    gate_store = FinalActionGateStore(final_actions_path)
    holds = gate_store.list_actions()
    assert any(h.verdict_id == "verdict-hold-persist" for h in holds)
    assert any(h.action == "merge" for h in holds)


# ---------------------------------------------------------------------------
# Verdict ingestion – rework
# ---------------------------------------------------------------------------


def test_ingest_rework_verdict_returns_rejected_transition(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-rework")])
    task = controller.open_review_task("lane-rework")
    verdict = ReviewVerdict(
        id="verdict-rework",
        lane_id="lane-rework",
        decision=ReviewDecision.REWORK,
        summary="Core behavior is incorrect.",
    )

    result = controller.ingest_verdict(task.task_id, verdict)

    assert result.transition_status == "rejected"
    assert result.final_action is None
    assert result.metadata["review_decision"] == "rework"


def test_ingest_rework_verdict_is_persisted(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-rework-persist")])
    task = controller.open_review_task("lane-rework-persist")
    verdict = ReviewVerdict(
        id="verdict-rework-persist",
        lane_id="lane-rework-persist",
        decision=ReviewDecision.REWORK,
        summary="Needs rework.",
    )

    controller.ingest_verdict(task.task_id, verdict)

    stored = controller.store.get_verdict("verdict-rework-persist")
    assert stored.decision == ReviewDecision.REWORK
    assert stored.task_id == task.task_id


# ---------------------------------------------------------------------------
# Verdict ingestion – patch-forward
# ---------------------------------------------------------------------------


def test_ingest_patch_forward_verdict_produces_patch_lane(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-pf", graph_id="graph-pf", resolution_id="res-pf")],
    )
    task = controller.open_review_task("lane-pf")
    verdict = ReviewVerdict(
        id="verdict-pf",
        lane_id="lane-pf",
        decision=ReviewDecision.PATCH_FORWARD,
        summary="Core is correct; fix edge case.",
        patch_instructions="Fix the edge case without broad refactors.",
    )

    result = controller.ingest_verdict(task.task_id, verdict)

    assert result.transition_status is None
    assert result.final_action is None
    assert result.patch_lane is not None
    assert result.patch_lane["feature_id"] == "lane-pf-patch-forward"
    assert result.patch_lane["source_lane_id"] == "lane-pf"


def test_patch_forward_patch_lane_inherits_graph_context(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-pf-ctx", graph_id="graph-ctx", resolution_id="res-ctx")],
    )
    task = controller.open_review_task("lane-pf-ctx")
    verdict = ReviewVerdict(
        id="verdict-pf-ctx",
        lane_id="lane-pf-ctx",
        decision=ReviewDecision.PATCH_FORWARD,
        summary="Fix edge case.",
        patch_instructions="Fix it.",
    )

    result = controller.ingest_verdict(task.task_id, verdict)

    assert result.patch_lane is not None
    assert result.patch_lane.get("graph_id") == "graph-ctx"
    assert result.patch_lane.get("resolution_id") == "res-ctx"


# ---------------------------------------------------------------------------
# Verdict ingestion – terminate
# ---------------------------------------------------------------------------


def test_ingest_terminate_verdict_with_final_action_approval_produces_hold(
    tmp_path: Path,
) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-term")],
        require_final_action_approval=True,
    )
    task = controller.open_review_task("lane-term")
    verdict = ReviewVerdict(
        id="verdict-term",
        lane_id="lane-term",
        decision=ReviewDecision.TERMINATE,
        summary="Scope is invalid.",
        terminate_reason="Out of blueprint scope.",
    )

    result = controller.ingest_verdict(task.task_id, verdict)

    assert result.transition_status is None
    assert result.final_action is not None
    assert result.final_action.action == "terminate"
    assert result.final_action.target_status == "failed"


def test_ingest_terminate_verdict_without_final_action_approval_returns_failed(
    tmp_path: Path,
) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-term-direct")],
        require_final_action_approval=False,
    )
    task = controller.open_review_task("lane-term-direct")
    verdict = ReviewVerdict(
        id="verdict-term-direct",
        lane_id="lane-term-direct",
        decision=ReviewDecision.TERMINATE,
        summary="Scope is invalid.",
        terminate_reason="Out of blueprint scope.",
    )

    result = controller.ingest_verdict(task.task_id, verdict)

    assert result.transition_status == "failed"
    assert result.final_action is None


# ---------------------------------------------------------------------------
# Lineage queries
# ---------------------------------------------------------------------------


def test_verdict_lineage_for_lane_returns_task_and_verdict(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-lineage")])
    task = controller.open_review_task("lane-lineage")
    controller.ingest_verdict(task.task_id, _merge_verdict("lane-lineage", "verdict-lineage"))

    lineage = controller.verdict_lineage_for_lane("lane-lineage")

    assert len(lineage) == 1
    entry = lineage[0]
    assert entry["task"]["task_id"] == task.task_id
    assert entry["verdict"] is not None
    assert entry["verdict"]["id"] == "verdict-lineage"


def test_verdict_lineage_for_lane_includes_pending_task_without_verdict(
    tmp_path: Path,
) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-pending-lineage")])
    task = controller.open_review_task("lane-pending-lineage")

    lineage = controller.verdict_lineage_for_lane("lane-pending-lineage")

    assert len(lineage) == 1
    assert lineage[0]["task"]["task_id"] == task.task_id
    assert lineage[0]["verdict"] is None


def test_has_verdict_lineage_is_true_after_finalized_verdict(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-has-verdict")])
    task = controller.open_review_task("lane-has-verdict")
    controller.ingest_verdict(task.task_id, _merge_verdict("lane-has-verdict"))

    assert controller.has_verdict_lineage("lane-has-verdict") is True


def test_has_verdict_lineage_is_false_before_any_verdict(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-no-verdict")])
    controller.open_review_task("lane-no-verdict")

    assert controller.has_verdict_lineage("lane-no-verdict") is False


def test_has_verdict_lineage_is_false_for_unknown_lane(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-known")])

    assert controller.has_verdict_lineage("lane-unknown") is False


# ---------------------------------------------------------------------------
# Multiple verdicts (requeue preserves original verdict relation)
# ---------------------------------------------------------------------------


def test_multiple_verdicts_for_same_lane_all_appear_in_lineage(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-multi")])

    # First review: rework
    task1 = controller.open_review_task("lane-multi")
    rework_verdict = ReviewVerdict(
        id="verdict-rework-multi",
        lane_id="lane-multi",
        decision=ReviewDecision.REWORK,
        summary="Needs rework.",
    )
    controller.ingest_verdict(task1.task_id, rework_verdict)

    # Second review (after rework): merge
    task2 = controller.open_review_task("lane-multi")
    merge_verdict = ReviewVerdict(
        id="verdict-merge-multi",
        lane_id="lane-multi",
        decision=ReviewDecision.MERGE,
        summary="No findings.",
    )
    controller.ingest_verdict(task2.task_id, merge_verdict)

    lineage = controller.verdict_lineage_for_lane("lane-multi")

    assert len(lineage) == 2
    decisions = {entry["verdict"]["decision"] for entry in lineage if entry["verdict"]}
    assert decisions == {"rework", "merge"}


def test_requeued_lane_original_verdict_preserved_in_lineage(tmp_path: Path) -> None:
    """A requeued lane must preserve the original rework verdict in lineage."""
    controller = _make_controller(tmp_path, [_gated_lane("lane-requeue")])

    task = controller.open_review_task("lane-requeue")
    rework_verdict = ReviewVerdict(
        id="verdict-original-rework",
        lane_id="lane-requeue",
        decision=ReviewDecision.REWORK,
        summary="Needs rework.",
    )
    controller.ingest_verdict(task.task_id, rework_verdict)

    lineage = controller.verdict_lineage_for_lane("lane-requeue")

    assert len(lineage) == 1
    assert lineage[0]["verdict"]["id"] == "verdict-original-rework"
    assert lineage[0]["verdict"]["decision"] == "rework"
    # task is linked to the verdict
    assert lineage[0]["task"]["verdict_id"] == "verdict-original-rework"


# ---------------------------------------------------------------------------
# Task cancellation
# ---------------------------------------------------------------------------


def test_cancel_review_task_marks_task_cancelled(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-cancel")])
    task = controller.open_review_task("lane-cancel")

    cancelled = controller.cancel_review_task(task.task_id)

    assert cancelled.status == ReviewTaskStatus.CANCELLED
    assert cancelled.updated_at is not None


def test_cancelled_task_does_not_block_new_pending_task(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-cancel-new")])
    task1 = controller.open_review_task("lane-cancel-new")
    controller.cancel_review_task(task1.task_id)

    task2 = controller.open_review_task("lane-cancel-new")

    assert task2.task_id != task1.task_id
    assert task2.status == ReviewTaskStatus.PENDING


# ---------------------------------------------------------------------------
# VerdictStore direct tests
# ---------------------------------------------------------------------------


def test_verdict_store_save_and_retrieve_verdict(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "verdicts.json")
    verdict = ReviewVerdict(
        id="v-direct",
        lane_id="lane-direct",
        decision=ReviewDecision.MERGE,
        summary="ok",
        created_at="2026-05-28T00:00:00Z",
    )

    store.save_verdict(verdict)
    retrieved = store.get_verdict("v-direct")

    assert retrieved.id == "v-direct"
    assert retrieved.decision == ReviewDecision.MERGE


def test_verdict_store_upserts_verdict(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "verdicts.json")
    verdict = ReviewVerdict(
        id="v-upsert",
        lane_id="lane-upsert",
        decision=ReviewDecision.REWORK,
        summary="first",
    )
    store.save_verdict(verdict)

    updated = verdict.model_copy(update={"summary": "updated"})
    store.save_verdict(updated)

    assert len(store.list_verdicts()) == 1
    assert store.get_verdict("v-upsert").summary == "updated"


def test_verdict_store_list_verdicts_for_lane(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "verdicts.json")
    store.save_verdict(
        ReviewVerdict(id="v-a1", lane_id="lane-a", decision=ReviewDecision.MERGE, summary="ok")
    )
    store.save_verdict(
        ReviewVerdict(id="v-b1", lane_id="lane-b", decision=ReviewDecision.REWORK, summary="no")
    )
    store.save_verdict(
        ReviewVerdict(id="v-a2", lane_id="lane-a", decision=ReviewDecision.MERGE, summary="ok2")
    )

    lane_a_verdicts = store.list_verdicts_for_lane("lane-a")

    assert len(lane_a_verdicts) == 2
    assert all(v.lane_id == "lane-a" for v in lane_a_verdicts)


def test_verdict_store_raises_on_unknown_verdict(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "verdicts.json")

    with pytest.raises(KeyError, match="unknown review verdict"):
        store.get_verdict("nonexistent")


def test_verdict_store_raises_on_unknown_task(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "verdicts.json")

    with pytest.raises(KeyError, match="unknown review task"):
        store.get_task("nonexistent")
