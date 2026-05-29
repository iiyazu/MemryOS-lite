"""
Focused tests for the review_plane track — merge verdict lineage via stdout fallback.

Covers the blueprint acceptance signal:
  "a merged lane has a verdict lineage"

Specifically tests that when _run_review_god infers a merge decision from stdout
(the fallback path), the verdict is persisted in the review plane store with a
stable ID that matches the review_verdict_id stamped on the lane.

Covers:
- Merge verdict from stdout fallback is ingested through review plane
- Merged lane has a verdict lineage (blueprint acceptance signal)
- has_verdict_lineage is True after a stdout-fallback merge
- Merge verdict ID matches review_verdict_id stamped on the lane
- Merge verdict is persisted before on_lane_reviewed is called
- Merge verdict ingestion failure does not break the merge path
- Stable verdict ID is deterministic within a single review cycle
- Stable verdict ID uses review_task_id when available
- Merge verdict lineage is preserved in verdict_lineage_for_run
- Merge verdict lineage is preserved across multiple lanes in a graph
- Merge verdict ingestion is skipped gracefully when no review_task_id is set
- on_lane_reviewed does not double-ingest when verdict already in store
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


_MERGE_STDOUT = "No findings. Approved for merge."
_REWORK_STDOUT = "**Findings**\n1. High: core behavior is incorrect."


# ---------------------------------------------------------------------------
# Merge verdict from stdout fallback is ingested through review plane
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_verdict_from_stdout_fallback_is_ingested_in_review_plane(
    tmp_path: Path,
) -> None:
    """When _run_review_god infers merge from stdout, the verdict is persisted."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-merge-fb")])

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-merge-fb")

    lane = orch._sm.get_lane("lane-merge-fb")
    task_id = lane.get("review_task_id")
    assert task_id is not None, "review_task_id must be stamped on the lane"

    task = orch._review_plane.store.get_task(task_id)
    assert task.verdict_id is not None, "task must have a verdict_id after merge"
    verdict = orch._review_plane.store.get_verdict(task.verdict_id)
    assert verdict.lane_id == "lane-merge-fb"
    assert verdict.decision == ReviewDecision.MERGE
    assert task.status == ReviewTaskStatus.VERDICT_EMITTED


@pytest.mark.asyncio
async def test_merged_lane_has_verdict_lineage(tmp_path: Path) -> None:
    """Blueprint acceptance signal: a merged lane has a verdict lineage."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-merged-lineage")])

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-merged-lineage")

    assert orch.has_verdict_lineage("lane-merged-lineage") is True


@pytest.mark.asyncio
async def test_merge_verdict_id_matches_review_verdict_id_on_lane(tmp_path: Path) -> None:
    """The stored verdict ID must match the review_verdict_id stamped on the lane."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-id-match")])

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-id-match")

    lane = orch._sm.get_lane("lane-id-match")
    review_verdict_id = lane.get("review_verdict_id")
    assert review_verdict_id is not None, "review_verdict_id must be stamped on the lane"

    # The stored verdict must have the same ID.
    verdict = orch._review_plane.store.get_verdict(review_verdict_id)
    assert verdict.id == review_verdict_id
    assert verdict.decision == ReviewDecision.MERGE


@pytest.mark.asyncio
async def test_merge_verdict_lineage_entry_has_correct_decision(tmp_path: Path) -> None:
    """The verdict lineage entry for a merged lane shows decision=merge."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-merge-decision")])

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-merge-decision")

    lineage = orch.verdict_lineage_for_lane("lane-merge-decision")

    assert len(lineage) >= 1
    merge_entries = [
        entry for entry in lineage
        if entry.get("verdict") and entry["verdict"]["decision"] == "merge"
    ]
    assert len(merge_entries) >= 1, "at least one merge verdict entry must exist in lineage"


@pytest.mark.asyncio
async def test_merge_verdict_ingestion_failure_does_not_break_merge_path(
    tmp_path: Path,
) -> None:
    """A review plane failure during merge ingestion must not prevent lane merge."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-merge-fail-ingest")])

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            with patch.object(
                orch._review_plane,
                "ingest_verdict",
                side_effect=RuntimeError("store failure"),
            ):
                # Should not raise.
                await orch._run_review_god("lane-merge-fail-ingest")

    lane = orch._sm.get_lane("lane-merge-fail-ingest")
    assert lane["status"] == "merged"


# ---------------------------------------------------------------------------
# Stable verdict ID
# ---------------------------------------------------------------------------


def test_stable_verdict_id_uses_review_task_id(tmp_path: Path) -> None:
    """_stable_verdict_id_for_lane uses review_task_id when available."""
    orch = _make_orchestrator(
        tmp_path,
        [_gated_lane("lane-stable-id", review_task_id="rtask_abc123")],
    )

    verdict_id = orch._stable_verdict_id_for_lane("lane-stable-id")

    assert verdict_id == "verdict-merge-rtask_abc123"


def test_stable_verdict_id_falls_back_to_lane_id(tmp_path: Path) -> None:
    """_stable_verdict_id_for_lane falls back to lane_id when no task_id."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-no-task-id")])

    verdict_id = orch._stable_verdict_id_for_lane("lane-no-task-id")

    assert verdict_id == "verdict-merge-lane-no-task-id"


def test_stable_verdict_id_is_deterministic(tmp_path: Path) -> None:
    """_stable_verdict_id_for_lane returns the same value on repeated calls."""
    orch = _make_orchestrator(
        tmp_path,
        [_gated_lane("lane-det", review_task_id="rtask_det")],
    )

    id1 = orch._stable_verdict_id_for_lane("lane-det")
    id2 = orch._stable_verdict_id_for_lane("lane-det")

    assert id1 == id2


# ---------------------------------------------------------------------------
# _ingest_merge_verdict_for_lane
# ---------------------------------------------------------------------------


def test_ingest_merge_verdict_for_lane_is_noop_when_no_task_id(tmp_path: Path) -> None:
    """_ingest_merge_verdict_for_lane is a no-op when review_task_id is absent."""
    orch = _make_orchestrator(
        tmp_path,
        [
            {
                "feature_id": "lane-no-task-merge",
                "status": "reviewed",
                "prompt": "fix",
                "review_decision": "merge",
                "review_summary": "Approved.",
                # No review_task_id
            }
        ],
    )

    # Should not raise.
    orch._ingest_merge_verdict_for_lane("lane-no-task-merge", "Approved.")

    tasks = orch._review_plane.store.list_tasks_for_lane("lane-no-task-merge")
    assert tasks == []


def test_ingest_merge_verdict_for_lane_persists_verdict(tmp_path: Path) -> None:
    """_ingest_merge_verdict_for_lane persists a merge verdict in the store."""
    orch = _make_orchestrator(
        tmp_path,
        [_gated_lane("lane-ingest-merge", review_task_id="rtask_ingest")],
    )
    # Open a task so the store has a task record.
    task = orch._review_plane.open_review_task("lane-ingest-merge")
    # Stamp the task_id on the lane.
    orch._sm.update_metadata("lane-ingest-merge", {"review_task_id": task.task_id})

    orch._ingest_merge_verdict_for_lane("lane-ingest-merge", "Approved.")

    updated_task = orch._review_plane.store.get_task(task.task_id)
    assert updated_task.verdict_id is not None
    verdict = orch._review_plane.store.get_verdict(updated_task.verdict_id)
    assert verdict.decision == ReviewDecision.MERGE
    assert verdict.lane_id == "lane-ingest-merge"


# ---------------------------------------------------------------------------
# Merge verdict lineage in verdict_lineage_for_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_verdict_lineage_preserved_in_verdict_lineage_for_run(
    tmp_path: Path,
) -> None:
    """verdict_lineage_for_run includes merge verdicts for all lanes in a graph."""
    graph_id = "graph-merge-run"
    lanes = [
        {**_gated_lane("lane-run-a"), "graph_id": graph_id},
        {**_gated_lane("lane-run-b"), "graph_id": graph_id},
    ]
    orch = _make_orchestrator(tmp_path, lanes)

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-run-a")
            await orch._run_review_god("lane-run-b")

    lineage = orch.verdict_lineage_for_run(graph_id)

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert "lane-run-a" in lane_ids
    assert "lane-run-b" in lane_ids
    decisions = {
        entry["verdict"]["decision"]
        for entry in lineage
        if entry.get("verdict")
    }
    assert "merge" in decisions


@pytest.mark.asyncio
async def test_on_lane_reviewed_does_not_duplicate_verdict_when_already_ingested(
    tmp_path: Path,
) -> None:
    """on_lane_reviewed upserts the verdict; no duplicate entries in the store."""
    orch = _make_orchestrator(tmp_path, [_gated_lane("lane-no-dup")])

    merge_result = SpawnResult(exit_code=0, stdout=_MERGE_STDOUT, stderr="")

    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock, return_value=merge_result):
        with patch.object(orch, "_auto_merge", new_callable=AsyncMock, return_value=True):
            await orch._run_review_god("lane-no-dup")

    # The store must have exactly one verdict for this lane.
    verdicts = orch._review_plane.store.list_verdicts_for_lane("lane-no-dup")
    assert len(verdicts) == 1
    assert verdicts[0].decision == ReviewDecision.MERGE
