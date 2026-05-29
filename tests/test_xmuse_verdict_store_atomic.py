"""Tests for VerdictStore atomic consistency guarantees.

Lane: self-evolution-reliability_hardening-res_e404647bc0cf4611b1f4e42c3c2b3466
      -graph-v1-verdict-store-consistency-impl-atomic

Covers:
- save_task_and_verdict writes both records in a single locked transaction.
- cancel_task is atomic: a concurrent verdict emission cannot silently
  overwrite the cancellation.
- ingest_verdict in ReviewPlaneController uses save_task_and_verdict so the
  primary call site is also atomic (single _write_unsafe call).
"""
from __future__ import annotations

import json
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

def _task(task_id: str = "rtask_abc", lane_id: str = "lane-1") -> ReviewTask:
    return ReviewTask(
        task_id=task_id,
        lane_id=lane_id,
        status=ReviewTaskStatus.PENDING,
        created_at="2026-01-01T00:00:00Z",
    )


def _verdict(verdict_id: str = "verdict-1", lane_id: str = "lane-1") -> ReviewVerdict:
    return ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=ReviewDecision.MERGE,
        summary="No findings.",
    )


# ---------------------------------------------------------------------------
# save_task_and_verdict
# ---------------------------------------------------------------------------


def test_save_task_and_verdict_persists_both_records(tmp_path: Path) -> None:
    """Both task and verdict are readable after a single atomic write."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task()
    verdict = _verdict()

    returned_task, returned_verdict = store.save_task_and_verdict(task, verdict)

    assert returned_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert returned_task.verdict_id == verdict.id

    stored_task = store.get_task(task.task_id)
    assert stored_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert stored_task.verdict_id == verdict.id

    stored_verdict = store.get_verdict(verdict.id)
    assert stored_verdict.lane_id == "lane-1"
    assert stored_verdict.decision == ReviewDecision.MERGE


def test_save_task_and_verdict_rejects_lane_id_mismatch(tmp_path: Path) -> None:
    """save_task_and_verdict raises ValueError when lane_ids differ."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task(lane_id="lane-A")
    verdict = _verdict(lane_id="lane-B")

    with pytest.raises(ValueError, match="lane_id mismatch"):
        store.save_task_and_verdict(task, verdict)


def test_save_task_and_verdict_is_idempotent(tmp_path: Path) -> None:
    """Calling save_task_and_verdict twice with the same IDs upserts cleanly."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task()
    verdict = _verdict()

    store.save_task_and_verdict(task, verdict)
    store.save_task_and_verdict(task, verdict)

    assert len(store.list_tasks()) == 1
    assert len(store.list_verdicts()) == 1


def test_save_task_and_verdict_single_write_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """save_task_and_verdict calls _write_unsafe exactly once (atomic transaction)."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task()
    verdict = _verdict()

    write_calls: list[int] = []
    original_write = store._write_unsafe

    def counting_write(data):  # type: ignore[no-untyped-def]
        write_calls.append(1)
        original_write(data)

    monkeypatch.setattr(store, "_write_unsafe", counting_write)

    store.save_task_and_verdict(task, verdict)

    assert len(write_calls) == 1, (
        f"Expected 1 write (atomic), got {len(write_calls)}"
    )


def test_save_task_and_verdict_concurrent_writes_do_not_corrupt(
    tmp_path: Path,
) -> None:
    """Concurrent save_task_and_verdict calls from multiple threads stay consistent."""
    store = VerdictStore(tmp_path / "store.json")
    errors: list[Exception] = []

    def write_pair(n: int) -> None:
        try:
            task = _task(task_id=f"rtask_{n}", lane_id=f"lane-{n}")
            verdict = _verdict(verdict_id=f"verdict-{n}", lane_id=f"lane-{n}")
            store.save_task_and_verdict(task, verdict)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write_pair, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent writes raised: {errors}"

    tasks = {t.task_id: t for t in store.list_tasks()}
    verdicts = {v.id: v for v in store.list_verdicts()}
    assert len(tasks) == 10
    assert len(verdicts) == 10
    for n in range(10):
        t = tasks[f"rtask_{n}"]
        assert t.status == ReviewTaskStatus.VERDICT_EMITTED
        assert t.verdict_id == f"verdict-{n}"
        assert f"verdict-{n}" in verdicts


# ---------------------------------------------------------------------------
# cancel_task
# ---------------------------------------------------------------------------


def test_cancel_task_marks_task_cancelled(tmp_path: Path) -> None:
    """cancel_task transitions the task to CANCELLED atomically."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task()
    store.save_task(task)

    cancelled = store.cancel_task(task.task_id, updated_at="2026-01-02T00:00:00Z")

    assert cancelled.status == ReviewTaskStatus.CANCELLED
    assert cancelled.updated_at == "2026-01-02T00:00:00Z"

    stored = store.get_task(task.task_id)
    assert stored.status == ReviewTaskStatus.CANCELLED


def test_cancel_task_raises_for_unknown_task(tmp_path: Path) -> None:
    """cancel_task raises KeyError for a task that does not exist."""
    store = VerdictStore(tmp_path / "store.json")

    with pytest.raises(KeyError, match="unknown review task"):
        store.cancel_task("nonexistent", updated_at="2026-01-01T00:00:00Z")


def test_cancel_task_single_write_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cancel_task calls _write_unsafe exactly once (atomic read-modify-write)."""
    store = VerdictStore(tmp_path / "store.json")
    task = _task()
    store.save_task(task)

    write_calls: list[int] = []
    original_write = store._write_unsafe

    def counting_write(data):  # type: ignore[no-untyped-def]
        write_calls.append(1)
        original_write(data)

    monkeypatch.setattr(store, "_write_unsafe", counting_write)

    store.cancel_task(task.task_id, updated_at="2026-01-02T00:00:00Z")

    assert len(write_calls) == 1


# ---------------------------------------------------------------------------
# ingest_verdict uses save_task_and_verdict (integration)
# ---------------------------------------------------------------------------


def test_ingest_verdict_is_atomic_via_review_plane(tmp_path: Path) -> None:
    """ReviewPlaneController.ingest_verdict uses save_task_and_verdict atomically.

    After ingest_verdict the task must be in verdict_emitted state and the
    verdict must exist — both in a single consistent snapshot.
    """
    from xmuse_core.platform.review_plane import ReviewPlaneController

    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps({"lanes": [
            {"feature_id": "lane-1", "status": "gated", "prompt": "fix"},
        ]})
    )
    controller = ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=tmp_path / "review_plane.json",
        final_actions_path=tmp_path / "final_actions.json",
    )

    task = controller.open_review_task("lane-1")
    verdict = ReviewVerdict(
        id="verdict-atomic-1",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="No findings.",
    )

    controller.ingest_verdict(task.task_id, verdict)

    stored_task = controller.store.get_task(task.task_id)
    assert stored_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert stored_task.verdict_id == "verdict-atomic-1"

    stored_verdict = controller.store.get_verdict("verdict-atomic-1")
    assert stored_verdict.task_id == task.task_id
    assert stored_verdict.decision == ReviewDecision.MERGE


def test_ingest_verdict_single_write_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ingest_verdict calls _write_unsafe exactly once (atomic transaction)."""
    from xmuse_core.platform.review_plane import ReviewPlaneController

    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps({"lanes": [
            {"feature_id": "lane-1", "status": "gated", "prompt": "fix"},
        ]})
    )
    controller = ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=tmp_path / "review_plane.json",
        final_actions_path=tmp_path / "final_actions.json",
    )
    task = controller.open_review_task("lane-1")

    write_calls: list[int] = []
    original_write = controller.store._write_unsafe

    def counting_write(data):  # type: ignore[no-untyped-def]
        write_calls.append(1)
        original_write(data)

    monkeypatch.setattr(controller.store, "_write_unsafe", counting_write)
    write_calls.clear()  # discard any writes from open_review_task

    verdict = ReviewVerdict(
        id="verdict-single-write",
        lane_id="lane-1",
        decision=ReviewDecision.MERGE,
        summary="ok",
    )
    controller.ingest_verdict(task.task_id, verdict)

    assert len(write_calls) == 1, (
        f"Expected 1 write (atomic), got {len(write_calls)}"
    )
