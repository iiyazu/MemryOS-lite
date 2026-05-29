"""
Focused tests for the review_plane track — orchestrator integration improvements.

Covers:
- Rework verdict from stdout fallback is ingested through review plane
- Rework verdict lineage is preserved when lane is requeued after rejection
- verdict_lineage_for_run on orchestrator returns correct lineage for a graph
- verdict_lineage_for_run returns empty list for unknown graph
- verdict_lineage_for_run includes patch-forward descendants via source_lane_id
- Rework verdict ingestion is skipped gracefully when no review_task_id is set
- Rework verdict ingestion failure does not break the rejection path
- Multiple rework cycles produce multiple verdict entries in lineage
- verdict_lineage_for_run excludes lanes from other graphs
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from xmuse_core.platform.agent_spawner import SpawnResult
from xmuse_core.platform.orchestrator import PlatformOrchestrator
from xmuse_core.structuring.models import ReviewDecision, ReviewTaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_orchestrator(tmp_path: Path, lanes: list[dict]) -> PlatformOrchestrator:
    lanes_path = tmp_path / "feature_lanes.json"
    _write_json(lanes_path, {"lanes": lanes})
    (tmp_path / "error_knowledge.json").write_text(json.dumps({"entries": []}))
    (tmp_path / "xmuse" / "god_prompts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "xmuse" / "god_prompts" / "execution_god.md").write_text("exec")
    (tmp_path / "xmuse" / "god_prompts" / "review_god.md").write_text("review")
    return PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )


def _gated_lane(lane_id: str, **extra) -> dict:
    return {
        "feature_id": lane_id,
        "status": "gated",
        "prompt": f"Implement {lane_id}",
        "gate_passed": True,
        **extra,
    }


# ---------------------------------------------------------------------------
# Rework verdict ingestion via stdout fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rework_verdict_from_stdout_fallback_is_ingested_in_review_plane(
    tmp_path: Path,
) -> None:
    """When _run_review_god infers rework from stdout, the verdict is persisted."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-rw")])

    review_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: core behavior is incorrect.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=review_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            await orch._run_review_god("lane-rw")

    lane = orch._sm.get_lane("lane-rw")
    task_id = lane.get("review_task_id")
    assert task_id is not None, "review_task_id must be stamped on the lane"

    # The rework verdict must be persisted in the review plane store.
    task = orch._review_plane.store.get_task(task_id)
    assert task.verdict_id is not None, "task must have a verdict_id after rework"
    verdict = orch._review_plane.store.get_verdict(task.verdict_id)
    assert verdict.lane_id == "lane-rw"
    assert verdict.decision == ReviewDecision.REWORK
    assert task.status == ReviewTaskStatus.VERDICT_EMITTED


@pytest.mark.asyncio
async def test_rework_verdict_lineage_preserved_after_requeue(tmp_path: Path) -> None:
    """After a rework rejection, the original verdict is preserved in lineage."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-requeue")])

    rework_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: logic is wrong.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=rework_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            await orch._run_review_god("lane-requeue")

    lineage = orch.verdict_lineage_for_lane("lane-requeue")

    assert len(lineage) == 1
    entry = lineage[0]
    assert entry["verdict"] is not None
    assert entry["verdict"]["decision"] == "rework"
    assert entry["task"]["verdict_id"] == entry["verdict"]["id"]


@pytest.mark.asyncio
async def test_rework_verdict_ingestion_skipped_when_no_task_id(tmp_path: Path) -> None:
    """_ingest_rework_verdict_for_lane is a no-op when review_task_id is absent."""
    orch = _make_orchestrator(
        tmp_path,
        [
            {
                "feature_id": "lane-no-task",
                "status": "rejected",
                "prompt": "fix",
                "review_decision": "rework",
                "review_summary": "Needs rework.",
                # No review_task_id
            }
        ],
    )

    # Should not raise.
    orch._ingest_rework_verdict_for_lane("lane-no-task", "Needs rework.")

    # No tasks should exist in the store.
    tasks = orch._review_plane.store.list_tasks_for_lane("lane-no-task")
    assert tasks == []


@pytest.mark.asyncio
async def test_rework_verdict_ingestion_failure_does_not_break_rejection_path(
    tmp_path: Path,
) -> None:
    """A review plane failure during rework ingestion must not prevent lane rejection."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-fail-ingest")])

    rework_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: logic is wrong.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=rework_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            with patch.object(
                orch._review_plane,
                "ingest_verdict",
                side_effect=RuntimeError("store failure"),
            ):
                # Should not raise.
                await orch._run_review_god("lane-fail-ingest")

    lane = orch._sm.get_lane("lane-fail-ingest")
    assert lane["status"] == "reworking"


@pytest.mark.asyncio
async def test_multiple_rework_cycles_produce_multiple_verdict_entries(
    tmp_path: Path,
) -> None:
    """Two rework cycles produce two verdict entries in the lineage."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-multi-rw")])

    rework_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: logic is wrong.",
        stderr="",
    )

    # First rework cycle.
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=rework_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            await orch._run_review_god("lane-multi-rw")

    # Simulate lane returning to gated for second review via the reworking path.
    # After on_lane_rejected, lane is already in reworking state.
    # reworking -> dispatched -> executed -> gated
    orch._sm.transition("lane-multi-rw", "dispatched")
    orch._sm.transition("lane-multi-rw", "executed")
    orch._sm.transition("lane-multi-rw", "gated", metadata={"gate_passed": True})

    # Second rework cycle.
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=rework_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            await orch._run_review_god("lane-multi-rw")

    lineage = orch.verdict_lineage_for_lane("lane-multi-rw")

    assert len(lineage) == 2
    decisions = {entry["verdict"]["decision"] for entry in lineage if entry["verdict"]}
    assert decisions == {"rework"}


# ---------------------------------------------------------------------------
# verdict_lineage_for_run on orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verdict_lineage_for_run_returns_entries_for_graph_lanes(
    tmp_path: Path,
) -> None:
    """verdict_lineage_for_run returns lineage for all lanes in a graph."""
    graph_id = "graph-run-orch"
    lanes = [
        {**_gated_lane("lane-a"), "graph_id": graph_id},
        {**_gated_lane("lane-b"), "graph_id": graph_id},
    ]
    orch = _make_orchestrator(tmp_path, lanes)

    # Open tasks and ingest merge verdicts for both lanes.
    task_a = orch._review_plane.open_review_task("lane-a")
    task_b = orch._review_plane.open_review_task("lane-b")

    from xmuse_core.structuring.models import ReviewVerdict

    orch._review_plane.ingest_verdict(
        task_a.task_id,
        ReviewVerdict(
            id="verdict-run-a",
            lane_id="lane-a",
            decision=ReviewDecision.MERGE,
            summary="No findings.",
        ),
    )
    orch._review_plane.ingest_verdict(
        task_b.task_id,
        ReviewVerdict(
            id="verdict-run-b",
            lane_id="lane-b",
            decision=ReviewDecision.MERGE,
            summary="No findings.",
        ),
    )

    lineage = orch.verdict_lineage_for_run(graph_id)

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert lane_ids == {"lane-a", "lane-b"}
    verdict_ids = {entry["verdict"]["id"] for entry in lineage if entry["verdict"]}
    assert verdict_ids == {"verdict-run-a", "verdict-run-b"}


def test_verdict_lineage_for_run_returns_empty_for_unknown_graph(tmp_path: Path) -> None:
    """verdict_lineage_for_run returns [] for a graph with no review tasks."""
    orch = _make_orchestrator(
        tmp_path,
        [{**_gated_lane("lane-x"), "graph_id": "graph-x"}],
    )

    lineage = orch.verdict_lineage_for_run("graph-nonexistent")

    assert lineage == []


@pytest.mark.asyncio
async def test_verdict_lineage_for_run_excludes_lanes_from_other_graphs(
    tmp_path: Path,
) -> None:
    """verdict_lineage_for_run only returns lanes belonging to the requested graph."""
    lanes = [
        {**_gated_lane("lane-target"), "graph_id": "graph-target"},
        {**_gated_lane("lane-other"), "graph_id": "graph-other"},
    ]
    orch = _make_orchestrator(tmp_path, lanes)

    from xmuse_core.structuring.models import ReviewVerdict

    task_target = orch._review_plane.open_review_task("lane-target")
    task_other = orch._review_plane.open_review_task("lane-other")
    orch._review_plane.ingest_verdict(
        task_target.task_id,
        ReviewVerdict(
            id="verdict-target",
            lane_id="lane-target",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )
    orch._review_plane.ingest_verdict(
        task_other.task_id,
        ReviewVerdict(
            id="verdict-other",
            lane_id="lane-other",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )

    lineage = orch.verdict_lineage_for_run("graph-target")

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert lane_ids == {"lane-target"}
    assert "lane-other" not in lane_ids


@pytest.mark.asyncio
async def test_verdict_lineage_for_run_includes_patch_forward_descendants(
    tmp_path: Path,
) -> None:
    """Patch-forward lanes linked via source_lane_id appear in run lineage."""
    graph_id = "graph-pf-orch"
    lanes = [
        {**_gated_lane("lane-orig"), "graph_id": graph_id},
        {
            "feature_id": "lane-orig-patch-forward",
            "status": "gated",
            "prompt": "Fix edge case.",
            "graph_id": graph_id,
            "source_lane_id": "lane-orig",
            "gate_passed": True,
        },
    ]
    orch = _make_orchestrator(tmp_path, lanes)

    from xmuse_core.structuring.models import ReviewVerdict

    task_orig = orch._review_plane.open_review_task("lane-orig")
    task_pf = orch._review_plane.open_review_task("lane-orig-patch-forward")
    orch._review_plane.ingest_verdict(
        task_orig.task_id,
        ReviewVerdict(
            id="verdict-orig-pf",
            lane_id="lane-orig",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )
    orch._review_plane.ingest_verdict(
        task_pf.task_id,
        ReviewVerdict(
            id="verdict-pf-pf",
            lane_id="lane-orig-patch-forward",
            decision=ReviewDecision.MERGE,
            summary="ok",
        ),
    )

    lineage = orch.verdict_lineage_for_run(graph_id)

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert "lane-orig" in lane_ids
    assert "lane-orig-patch-forward" in lane_ids


# ---------------------------------------------------------------------------
# Rework verdict ingestion via on_lane_reviewed (existing path, regression guard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_lane_reviewed_with_rework_decision_ingests_verdict(
    tmp_path: Path,
) -> None:
    """on_lane_reviewed with a rework decision ingests the verdict through review plane.

    The rework path in on_lane_reviewed calls ingest_verdict before transitioning
    to rejected.  This test verifies the verdict is persisted even when the lane
    is in the gated state and the review GOD stdout fallback produces a rework.
    """
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-rw-reviewed")])

    # Simulate review GOD returning a rework verdict via stdout fallback.
    rework_result = SpawnResult(
        exit_code=0,
        stdout="**Findings**\n1. High: core behavior is incorrect.",
        stderr="",
    )

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=rework_result):
        with patch.object(orch, "dispatch_lane", new_callable=AsyncMock):
            await orch._run_review_god("lane-rw-reviewed")

    lane = orch._sm.get_lane("lane-rw-reviewed")
    task_id = lane.get("review_task_id")
    assert task_id is not None

    # The verdict must be persisted with the rework decision.
    task = orch._review_plane.store.get_task(task_id)
    assert task.verdict_id is not None
    verdict = orch._review_plane.store.get_verdict(task.verdict_id)
    assert verdict.decision == ReviewDecision.REWORK
    assert verdict.task_id == task_id
