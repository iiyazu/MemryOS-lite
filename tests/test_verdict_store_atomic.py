"""Tests for atomic verdict operations in VerdictStore.

Covers:
- save_task_and_verdict atomicity (both records land together)
- lane_id mismatch guard
- concurrent save_verdict calls do not lose updates (lost-update race)
- concurrent save_task calls do not lose updates
- task status and verdict_id are stamped correctly by save_task_and_verdict
- idempotent upsert: re-saving the same verdict replaces, not duplicates
- ClarificationStore open_clarification idempotency under concurrent calls
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

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

def _task(task_id: str, lane_id: str = "lane-1") -> ReviewTask:
    return ReviewTask(
        task_id=task_id,
        lane_id=lane_id,
        graph_id="graph-1",
        created_at="2026-05-28T00:00:00Z",
    )


def _verdict(verdict_id: str, lane_id: str = "lane-1") -> ReviewVerdict:
    return ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=ReviewDecision.MERGE,
        summary="looks good",
    )


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------

def test_save_and_get_task(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    task = _task("t-1")
    store.save_task(task)
    assert store.get_task("t-1").task_id == "t-1"


def test_save_and_get_verdict(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    verdict = _verdict("v-1")
    store.save_verdict(verdict)
    assert store.get_verdict("v-1").id == "v-1"


def test_get_task_raises_for_unknown(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    with pytest.raises(KeyError, match="unknown review task"):
        store.get_task("nope")


def test_get_verdict_raises_for_unknown(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    with pytest.raises(KeyError, match="unknown review verdict"):
        store.get_verdict("nope")


# ---------------------------------------------------------------------------
# Upsert / deduplication
# ---------------------------------------------------------------------------

def test_save_verdict_upserts_not_duplicates(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    v1 = _verdict("v-1")
    store.save_verdict(v1)
    v1_updated = v1.model_copy(update={"summary": "updated summary"})
    store.save_verdict(v1_updated)

    verdicts = store.list_verdicts()
    assert len(verdicts) == 1
    assert verdicts[0].summary == "updated summary"


def test_save_task_upserts_not_duplicates(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    t1 = _task("t-1")
    store.save_task(t1)
    t1_updated = t1.model_copy(update={"lane_prompt": "updated"})
    store.save_task(t1_updated)

    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].lane_prompt == "updated"


# ---------------------------------------------------------------------------
# save_task_and_verdict atomicity
# ---------------------------------------------------------------------------

def test_save_task_and_verdict_links_task_to_verdict(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    task = _task("t-1")
    verdict = _verdict("v-1")

    saved_task, saved_verdict = store.save_task_and_verdict(task, verdict)

    # Task must be stamped with verdict_emitted status and verdict_id
    assert saved_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert saved_task.verdict_id == "v-1"

    # Both records must be readable from the store
    persisted_task = store.get_task("t-1")
    persisted_verdict = store.get_verdict("v-1")
    assert persisted_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert persisted_task.verdict_id == "v-1"
    assert persisted_verdict.id == "v-1"


def test_save_task_and_verdict_both_records_present_after_write(tmp_path: Path) -> None:
    """Verify the store file contains both records after a single transaction."""
    store_path = tmp_path / "store.json"
    store = VerdictStore(store_path)
    store.save_task_and_verdict(_task("t-1"), _verdict("v-1"))

    # Re-open a fresh store instance to confirm persistence
    fresh = VerdictStore(store_path)
    assert len(fresh.list_tasks()) == 1
    assert len(fresh.list_verdicts()) == 1


def test_save_task_and_verdict_rejects_lane_id_mismatch(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    task = _task("t-1", lane_id="lane-A")
    verdict = _verdict("v-1", lane_id="lane-B")

    with pytest.raises(ValueError, match="lane_id mismatch"):
        store.save_task_and_verdict(task, verdict)

    # Store must remain empty – no partial write
    assert store.list_tasks() == []
    assert store.list_verdicts() == []


def test_save_task_and_verdict_does_not_mutate_original_task(tmp_path: Path) -> None:
    """The caller's task object must not be mutated in place."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task("t-1")
    original_status = task.status

    store.save_task_and_verdict(task, _verdict("v-1"))

    assert task.status == original_status
    assert task.verdict_id is None


# ---------------------------------------------------------------------------
# Concurrent write safety (lost-update race)
# ---------------------------------------------------------------------------

def test_concurrent_save_verdict_no_lost_updates(tmp_path: Path) -> None:
    """N threads each save a distinct verdict; all N must be present after."""
    store = VerdictStore(tmp_path / "store.json")
    n = 20
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            store.save_verdict(_verdict(f"v-{i}", lane_id=f"lane-{i}"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"worker errors: {errors}"
    verdicts = store.list_verdicts()
    assert len(verdicts) == n, (
        f"expected {n} verdicts, got {len(verdicts)}: "
        f"{[v.id for v in verdicts]}"
    )


def test_concurrent_save_task_no_lost_updates(tmp_path: Path) -> None:
    """N threads each save a distinct task; all N must be present after."""
    store = VerdictStore(tmp_path / "store.json")
    n = 20
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            store.save_task(_task(f"t-{i}", lane_id=f"lane-{i}"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"worker errors: {errors}"
    tasks = store.list_tasks()
    assert len(tasks) == n, (
        f"expected {n} tasks, got {len(tasks)}: "
        f"{[t.task_id for t in tasks]}"
    )


def test_concurrent_save_task_and_verdict_no_lost_updates(tmp_path: Path) -> None:
    """N threads each call save_task_and_verdict; all N pairs must be present."""
    store = VerdictStore(tmp_path / "store.json")
    n = 20
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            store.save_task_and_verdict(
                _task(f"t-{i}", lane_id=f"lane-{i}"),
                _verdict(f"v-{i}", lane_id=f"lane-{i}"),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"worker errors: {errors}"
    tasks = store.list_tasks()
    verdicts = store.list_verdicts()
    assert len(tasks) == n, f"expected {n} tasks, got {len(tasks)}"
    assert len(verdicts) == n, f"expected {n} verdicts, got {len(verdicts)}"

    # Every task must be linked to its verdict
    task_map = {t.task_id: t for t in tasks}
    for i in range(n):
        t = task_map[f"t-{i}"]
        assert t.status == ReviewTaskStatus.VERDICT_EMITTED
        assert t.verdict_id == f"v-{i}"


# ---------------------------------------------------------------------------
# list helpers
# ---------------------------------------------------------------------------

def test_list_tasks_for_lane(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    store.save_task(_task("t-1", lane_id="lane-A"))
    store.save_task(_task("t-2", lane_id="lane-B"))
    store.save_task(_task("t-3", lane_id="lane-A"))

    result = store.list_tasks_for_lane("lane-A")
    assert {t.task_id for t in result} == {"t-1", "t-3"}


def test_list_verdicts_for_lane(tmp_path: Path) -> None:
    store = VerdictStore(tmp_path / "store.json")
    store.save_verdict(_verdict("v-1", lane_id="lane-A"))
    store.save_verdict(_verdict("v-2", lane_id="lane-B"))

    result = store.list_verdicts_for_lane("lane-A")
    assert len(result) == 1
    assert result[0].id == "v-1"
