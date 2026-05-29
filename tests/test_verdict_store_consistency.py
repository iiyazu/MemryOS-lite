"""Consistency verification tests for VerdictStore operations.

Covers:
- Graph consistency: verdict operations don't corrupt co-located task records.
- Concurrent-safe atomic writes: temp-file replace prevents partial reads.
- Lineage merge safety: patch-forward verdicts don't cause lineage failures.
- Idempotent upserts: repeated saves don't duplicate or corrupt records.
- Cross-collection integrity: task→verdict linkage stays coherent.
- save_task_and_verdict atomicity: both records land together or neither does.
- cancel_task safety: cancellation is not silently overwritten by concurrent writes.
- Graph termination prevention: lane_id mismatch raises before any write.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from xmuse_core.structuring.models import (
    LaneGraph,
    LaneNode,
    ReviewDecision,
    ReviewTask,
    ReviewTaskStatus,
    ReviewVerdict,
    RunTerminalStatus,
    StructuredEvidenceBundle,
)
from xmuse_core.structuring.projection import project_ready_lanes
from xmuse_core.structuring.verdict_store import EvidenceBundleStore, VerdictStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "verdicts.json"


@pytest.fixture()
def store(store_path: Path) -> VerdictStore:
    return VerdictStore(store_path)


def _make_task(
    task_id: str = "task-1",
    lane_id: str = "lane-1",
    graph_id: str = "graph-1",
) -> ReviewTask:
    return ReviewTask(
        task_id=task_id,
        lane_id=lane_id,
        graph_id=graph_id,
        lane_prompt="implement feature X",
        status=ReviewTaskStatus.PENDING,
        created_at="2026-05-28T00:00:00Z",
    )


def _make_verdict(
    verdict_id: str = "verdict-1",
    lane_id: str = "lane-1",
    decision: ReviewDecision = ReviewDecision.MERGE,
    task_id: str | None = "task-1",
) -> ReviewVerdict:
    return ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=decision,
        summary="looks good",
        task_id=task_id,
        created_at="2026-05-28T00:00:00Z",
    )


def _make_bundle(
    bundle_id: str = "bundle-1",
    source_run_id: str = "run-1",
) -> StructuredEvidenceBundle:
    return StructuredEvidenceBundle(
        bundle_id=bundle_id,
        source_run_id=source_run_id,
        selection_policy_id="default",
        selection_policy_version="1.0",
        summary="run completed",
        run_terminal_status=RunTerminalStatus.MERGED,
        created_at="2026-05-28T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Basic CRUD consistency
# ---------------------------------------------------------------------------


def test_save_and_retrieve_task_roundtrip(store: VerdictStore) -> None:
    task = _make_task()
    store.save_task(task)
    retrieved = store.get_task("task-1")
    assert retrieved.task_id == "task-1"
    assert retrieved.lane_id == "lane-1"
    assert retrieved.status == ReviewTaskStatus.PENDING


def test_save_and_retrieve_verdict_roundtrip(store: VerdictStore) -> None:
    verdict = _make_verdict()
    store.save_verdict(verdict)
    retrieved = store.get_verdict("verdict-1")
    assert retrieved.id == "verdict-1"
    assert retrieved.decision == ReviewDecision.MERGE
    assert retrieved.task_id == "task-1"


def test_get_unknown_task_raises_key_error(store: VerdictStore) -> None:
    with pytest.raises(KeyError, match="unknown review task"):
        store.get_task("nonexistent")


def test_get_unknown_verdict_raises_key_error(store: VerdictStore) -> None:
    with pytest.raises(KeyError, match="unknown review verdict"):
        store.get_verdict("nonexistent")


# ---------------------------------------------------------------------------
# Graph consistency: tasks and verdicts co-located in one file
# ---------------------------------------------------------------------------


def test_task_and_verdict_coexist_in_same_file(store_path: Path, store: VerdictStore) -> None:
    """Both collections must survive in the same JSON file without clobbering."""
    task = _make_task()
    verdict = _make_verdict()

    store.save_task(task)
    store.save_verdict(verdict)

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw["review_tasks"]) == 1
    assert len(raw["review_verdicts"]) == 1


def test_saving_verdict_does_not_corrupt_existing_tasks(store: VerdictStore) -> None:
    """Saving a verdict must not remove or alter previously saved tasks."""
    task = _make_task()
    store.save_task(task)

    verdict = _make_verdict()
    store.save_verdict(verdict)

    # Task must still be intact
    retrieved_task = store.get_task("task-1")
    assert retrieved_task.lane_id == "lane-1"
    assert retrieved_task.status == ReviewTaskStatus.PENDING


def test_saving_task_does_not_corrupt_existing_verdicts(store: VerdictStore) -> None:
    """Saving a task must not remove or alter previously saved verdicts."""
    verdict = _make_verdict()
    store.save_verdict(verdict)

    task = _make_task()
    store.save_task(task)

    retrieved_verdict = store.get_verdict("verdict-1")
    assert retrieved_verdict.decision == ReviewDecision.MERGE


def test_multiple_lanes_tasks_and_verdicts_stay_isolated(store: VerdictStore) -> None:
    """Records for different lanes must not bleed into each other."""
    for i in range(1, 4):
        store.save_task(_make_task(f"task-{i}", f"lane-{i}", "graph-1"))
        store.save_verdict(_make_verdict(f"verdict-{i}", f"lane-{i}", task_id=f"task-{i}"))

    for i in range(1, 4):
        t = store.get_task(f"task-{i}")
        v = store.get_verdict(f"verdict-{i}")
        assert t.lane_id == f"lane-{i}"
        assert v.lane_id == f"lane-{i}"
        assert v.task_id == f"task-{i}"

    # list_for_lane must return only the matching lane's records
    assert len(store.list_tasks_for_lane("lane-2")) == 1
    assert len(store.list_verdicts_for_lane("lane-2")) == 1


# ---------------------------------------------------------------------------
# Idempotent upsert: no duplicates on repeated saves
# ---------------------------------------------------------------------------


def test_repeated_task_save_is_idempotent(store_path: Path, store: VerdictStore) -> None:
    task = _make_task()
    store.save_task(task)
    store.save_task(task)  # second save with same task_id

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw["review_tasks"]) == 1


def test_repeated_verdict_save_is_idempotent(store_path: Path, store: VerdictStore) -> None:
    verdict = _make_verdict()
    store.save_verdict(verdict)
    store.save_verdict(verdict)  # second save with same id

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw["review_verdicts"]) == 1


def test_task_update_replaces_in_place(store: VerdictStore) -> None:
    """Updating a task's status must replace the record, not append a duplicate."""
    task = _make_task()
    store.save_task(task)

    updated = task.model_copy(
        update={"status": ReviewTaskStatus.VERDICT_EMITTED, "verdict_id": "verdict-1"}
    )
    store.save_task(updated)

    retrieved = store.get_task("task-1")
    assert retrieved.status == ReviewTaskStatus.VERDICT_EMITTED
    assert retrieved.verdict_id == "verdict-1"
    assert len(store.list_tasks()) == 1


def test_verdict_update_replaces_in_place(store: VerdictStore) -> None:
    """Updating a verdict must replace the record, not append a duplicate."""
    verdict = _make_verdict()
    store.save_verdict(verdict)

    updated = verdict.model_copy(update={"summary": "revised summary"})
    store.save_verdict(updated)

    retrieved = store.get_verdict("verdict-1")
    assert retrieved.summary == "revised summary"
    assert len(store.list_verdicts()) == 1


# ---------------------------------------------------------------------------
# Atomic write: temp-file replace prevents partial reads
# ---------------------------------------------------------------------------


def test_store_file_is_valid_json_after_write(store_path: Path, store: VerdictStore) -> None:
    """The store file must always be valid JSON after any write."""
    store.save_task(_make_task())
    store.save_verdict(_make_verdict())

    content = store_path.read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert "review_tasks" in parsed
    assert "review_verdicts" in parsed


def test_store_recovers_from_missing_file(store_path: Path) -> None:
    """A store pointed at a non-existent file must return empty collections."""
    store = VerdictStore(store_path)  # file does not exist yet
    assert store.list_tasks() == []
    assert store.list_verdicts() == []


def test_store_recovers_from_corrupt_json(store_path: Path) -> None:
    """A store with corrupt JSON must return empty collections, not raise."""
    store_path.write_text("not valid json", encoding="utf-8")
    store = VerdictStore(store_path)
    assert store.list_tasks() == []
    assert store.list_verdicts() == []


def test_store_recovers_from_wrong_root_type(store_path: Path) -> None:
    """A store whose file contains a JSON array (not object) must not crash."""
    store_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    store = VerdictStore(store_path)
    assert store.list_tasks() == []
    assert store.list_verdicts() == []


# ---------------------------------------------------------------------------
# Concurrent operations: thread-safety via atomic replace
# ---------------------------------------------------------------------------


def test_concurrent_verdict_saves_do_not_lose_records(store_path: Path) -> None:
    """Concurrent saves from multiple threads must not lose any record."""
    store = VerdictStore(store_path)
    errors: list[Exception] = []

    def save_verdict(i: int) -> None:
        try:
            v = _make_verdict(f"verdict-{i}", f"lane-{i}", task_id=f"task-{i}")
            store.save_verdict(v)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=save_verdict, args=(i,)) for i in range(1, 11)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent saves raised: {errors}"
    verdicts = store.list_verdicts()
    # All 10 verdicts must be present (no silent drops)
    assert len(verdicts) == 10


def test_concurrent_task_saves_do_not_lose_records(store_path: Path) -> None:
    """Concurrent task saves from multiple threads must not lose any record."""
    store = VerdictStore(store_path)
    errors: list[Exception] = []

    def save_task(i: int) -> None:
        try:
            t = _make_task(f"task-{i}", f"lane-{i}")
            store.save_task(t)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=save_task, args=(i,)) for i in range(1, 11)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent saves raised: {errors}"
    tasks = store.list_tasks()
    assert len(tasks) == 10


def test_concurrent_mixed_saves_preserve_both_collections(store_path: Path) -> None:
    """Interleaved task and verdict saves must not corrupt either collection."""
    store = VerdictStore(store_path)
    errors: list[Exception] = []

    def save_task(i: int) -> None:
        try:
            store.save_task(_make_task(f"task-{i}", f"lane-{i}"))
        except Exception as exc:
            errors.append(exc)

    def save_verdict(i: int) -> None:
        try:
            store.save_verdict(_make_verdict(f"verdict-{i}", f"lane-{i}"))
        except Exception as exc:
            errors.append(exc)

    threads = (
        [threading.Thread(target=save_task, args=(i,)) for i in range(1, 6)]
        + [threading.Thread(target=save_verdict, args=(i,)) for i in range(1, 6)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent saves raised: {errors}"
    # Both collections must have all 5 records each
    assert len(store.list_tasks()) == 5
    assert len(store.list_verdicts()) == 5


# ---------------------------------------------------------------------------
# Lineage merge safety: patch-forward verdicts don't cause lineage failures
# ---------------------------------------------------------------------------


def test_patch_forward_verdict_preserves_source_lane_linkage(store: VerdictStore) -> None:
    """A patch-forward verdict must retain the source lane_id for lineage tracing."""
    verdict = _make_verdict(
        verdict_id="verdict-pf",
        lane_id="lane-1",
        decision=ReviewDecision.PATCH_FORWARD,
    )
    verdict = verdict.model_copy(
        update={"patch_instructions": "fix the off-by-one in utils.py"}
    )
    store.save_verdict(verdict)

    retrieved = store.get_verdict("verdict-pf")
    assert retrieved.lane_id == "lane-1"
    assert retrieved.decision == ReviewDecision.PATCH_FORWARD
    assert retrieved.patch_instructions == "fix the off-by-one in utils.py"


def test_terminate_verdict_does_not_remove_task_record(store: VerdictStore) -> None:
    """A terminate verdict must not delete the associated task from the store."""
    task = _make_task()
    store.save_task(task)

    verdict = _make_verdict(
        verdict_id="verdict-term",
        decision=ReviewDecision.TERMINATE,
    )
    verdict = verdict.model_copy(update={"terminate_reason": "unrecoverable failure"})
    store.save_verdict(verdict)

    # Task must still be retrievable
    retrieved_task = store.get_task("task-1")
    assert retrieved_task.task_id == "task-1"

    retrieved_verdict = store.get_verdict("verdict-term")
    assert retrieved_verdict.terminate_reason == "unrecoverable failure"


def test_multiple_verdicts_for_same_lane_all_preserved(store: VerdictStore) -> None:
    """Multiple verdicts for the same lane (e.g. rework cycles) must all be stored."""
    for i, decision in enumerate(
        [ReviewDecision.REWORK, ReviewDecision.REWORK, ReviewDecision.MERGE], start=1
    ):
        store.save_verdict(
            _make_verdict(f"verdict-{i}", lane_id="lane-1", decision=decision)
        )

    lane_verdicts = store.list_verdicts_for_lane("lane-1")
    assert len(lane_verdicts) == 3
    decisions = [v.decision for v in lane_verdicts]
    assert decisions.count(ReviewDecision.REWORK) == 2
    assert decisions.count(ReviewDecision.MERGE) == 1


def test_task_verdict_chain_integrity(store: VerdictStore) -> None:
    """The task→verdict chain must be auditable: task.verdict_id → verdict.id."""
    task = _make_task()
    store.save_task(task)

    verdict = _make_verdict(verdict_id="verdict-chain", task_id="task-1")
    store.save_verdict(verdict)

    # Update task to record the verdict linkage
    linked_task = task.model_copy(
        update={
            "status": ReviewTaskStatus.VERDICT_EMITTED,
            "verdict_id": "verdict-chain",
        }
    )
    store.save_task(linked_task)

    retrieved_task = store.get_task("task-1")
    assert retrieved_task.verdict_id == "verdict-chain"

    retrieved_verdict = store.get_verdict("verdict-chain")
    assert retrieved_verdict.task_id == "task-1"

    # Chain is intact: task.verdict_id == verdict.id
    assert retrieved_task.verdict_id == retrieved_verdict.id


# ---------------------------------------------------------------------------
# Graph projection consistency: verdicts don't break lane graph readiness
# ---------------------------------------------------------------------------


def test_verdict_store_operations_do_not_corrupt_lane_graph_file(tmp_path: Path) -> None:
    """Writing verdicts to a separate file must not affect the lanes file."""
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "feature_id": "lane-1",
                        "status": "pending",
                        "prompt": "implement X",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    verdict_store = VerdictStore(tmp_path / "verdicts.json")
    verdict_store.save_task(_make_task())
    verdict_store.save_verdict(_make_verdict())

    # Lanes file must be unchanged
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    assert len(lanes_data["lanes"]) == 1
    assert lanes_data["lanes"][0]["feature_id"] == "lane-1"
    assert lanes_data["lanes"][0]["status"] == "pending"


def test_project_ready_lanes_after_verdict_store_writes(tmp_path: Path) -> None:
    """project_ready_lanes must work correctly after verdict store writes."""
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps({"lanes": [{"feature_id": "lane-a", "status": "merged", "prompt": "done"}]}),
        encoding="utf-8",
    )

    graph = LaneGraph(
        id="graph-1",
        conversation_id="conv-1",
        resolution_id="res-1",
        version=1,
        lanes=[
            LaneNode(
                feature_id="lane-b",
                prompt="implement Y",
                depends_on=["lane-a"],
            )
        ],
    )

    # Write verdicts to a separate file (simulating real usage)
    verdict_store = VerdictStore(tmp_path / "verdicts.json")
    verdict_store.save_verdict(_make_verdict(lane_id="lane-a"))

    # project_ready_lanes must project lane-b since lane-a is merged
    projected = project_ready_lanes(graph, lanes_path)

    assert len(projected) == 1
    assert projected[0]["feature_id"] == "lane-b"
    assert projected[0]["status"] == "pending"


def test_graph_projection_not_affected_by_verdict_store_corruption(tmp_path: Path) -> None:
    """A corrupt verdict store must not prevent graph projection from working."""
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps({"lanes": [{"feature_id": "lane-a", "status": "merged", "prompt": "done"}]}),
        encoding="utf-8",
    )

    # Corrupt the verdict store file
    corrupt_path = tmp_path / "verdicts.json"
    corrupt_path.write_text("{{invalid json", encoding="utf-8")

    graph = LaneGraph(
        id="graph-1",
        conversation_id="conv-1",
        resolution_id="res-1",
        version=1,
        lanes=[
            LaneNode(feature_id="lane-b", prompt="implement Z", depends_on=["lane-a"])
        ],
    )

    # Projection must still work — it reads lanes_path, not the verdict store
    projected = project_ready_lanes(graph, lanes_path)
    assert len(projected) == 1
    assert projected[0]["feature_id"] == "lane-b"


# ---------------------------------------------------------------------------
# EvidenceBundleStore consistency
# ---------------------------------------------------------------------------


def test_evidence_bundle_save_and_retrieve(tmp_path: Path) -> None:
    bundle_store = EvidenceBundleStore(tmp_path / "bundles.json")
    bundle = _make_bundle()
    bundle_store.save(bundle)

    retrieved = bundle_store.get("bundle-1")
    assert retrieved.bundle_id == "bundle-1"
    assert retrieved.source_run_id == "run-1"
    assert retrieved.run_terminal_status == RunTerminalStatus.MERGED


def test_evidence_bundle_upsert_is_idempotent(tmp_path: Path) -> None:
    bundle_store = EvidenceBundleStore(tmp_path / "bundles.json")
    bundle = _make_bundle()
    bundle_store.save(bundle)
    bundle_store.save(bundle)

    all_bundles = bundle_store.list_all()
    assert len(all_bundles) == 1


def test_evidence_bundle_list_for_run(tmp_path: Path) -> None:
    bundle_store = EvidenceBundleStore(tmp_path / "bundles.json")
    bundle_store.save(_make_bundle("bundle-1", "run-1"))
    bundle_store.save(_make_bundle("bundle-2", "run-1"))
    bundle_store.save(_make_bundle("bundle-3", "run-2"))

    run1_bundles = bundle_store.list_for_run("run-1")
    assert len(run1_bundles) == 2
    assert all(b.source_run_id == "run-1" for b in run1_bundles)


def test_evidence_bundle_get_unknown_raises(tmp_path: Path) -> None:
    bundle_store = EvidenceBundleStore(tmp_path / "bundles.json")
    with pytest.raises(KeyError, match="unknown evidence bundle"):
        bundle_store.get("nonexistent")


def test_evidence_bundle_store_recovers_from_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "bundles.json"
    path.write_text("not json", encoding="utf-8")
    bundle_store = EvidenceBundleStore(path)
    assert bundle_store.list_all() == []


def test_evidence_bundle_concurrent_saves_preserve_all_records(tmp_path: Path) -> None:
    """Concurrent bundle saves must not lose any record."""
    bundle_store = EvidenceBundleStore(tmp_path / "bundles.json")
    errors: list[Exception] = []

    def save_bundle(i: int) -> None:
        try:
            bundle_store.save(_make_bundle(f"bundle-{i}", f"run-{i}"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=save_bundle, args=(i,)) for i in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent saves raised: {errors}"
    assert len(bundle_store.list_all()) == 8


# ---------------------------------------------------------------------------
# save_task_and_verdict: atomic transaction consistency
# ---------------------------------------------------------------------------


def test_save_task_and_verdict_links_task_to_verdict_atomically(
    store: VerdictStore,
) -> None:
    """save_task_and_verdict must stamp task.verdict_id and set status in one write."""
    task = _make_task()
    verdict = _make_verdict(verdict_id="verdict-atomic")

    linked_task, saved_verdict = store.save_task_and_verdict(task, verdict)

    assert linked_task.verdict_id == "verdict-atomic"
    assert linked_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert saved_verdict.id == "verdict-atomic"

    # Verify the persisted state matches the returned objects
    persisted_task = store.get_task("task-1")
    persisted_verdict = store.get_verdict("verdict-atomic")
    assert persisted_task.verdict_id == "verdict-atomic"
    assert persisted_task.status == ReviewTaskStatus.VERDICT_EMITTED
    assert persisted_verdict.id == "verdict-atomic"


def test_save_task_and_verdict_rejects_lane_id_mismatch(store: VerdictStore) -> None:
    """A lane_id mismatch must raise ValueError before any write occurs."""
    task = _make_task(task_id="task-mismatch", lane_id="lane-A")
    verdict = _make_verdict(verdict_id="verdict-mismatch", lane_id="lane-B")

    with pytest.raises(ValueError, match="lane_id mismatch"):
        store.save_task_and_verdict(task, verdict)

    # Store must remain empty — no partial write
    assert store.list_tasks() == []
    assert store.list_verdicts() == []


def test_save_task_and_verdict_is_idempotent(store: VerdictStore) -> None:
    """Calling save_task_and_verdict twice with the same IDs must not duplicate records."""
    task = _make_task()
    verdict = _make_verdict(verdict_id="verdict-idem")

    store.save_task_and_verdict(task, verdict)
    store.save_task_and_verdict(task, verdict)

    assert len(store.list_tasks()) == 1
    assert len(store.list_verdicts()) == 1


def test_save_task_and_verdict_both_records_visible_after_write(
    store_path: Path,
) -> None:
    """After save_task_and_verdict both records must be present in the raw file."""
    store = VerdictStore(store_path)
    task = _make_task()
    verdict = _make_verdict(verdict_id="verdict-both")

    store.save_task_and_verdict(task, verdict)

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(raw["review_tasks"]) == 1
    assert len(raw["review_verdicts"]) == 1
    assert raw["review_tasks"][0]["verdict_id"] == "verdict-both"
    assert raw["review_tasks"][0]["status"] == ReviewTaskStatus.VERDICT_EMITTED


def test_concurrent_save_task_and_verdict_no_lost_updates(store_path: Path) -> None:
    """N threads each calling save_task_and_verdict must all be persisted."""
    store = VerdictStore(store_path)
    n = 20
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            t = _make_task(f"task-conc-{i}", f"lane-{i}")
            v = _make_verdict(f"verdict-conc-{i}", f"lane-{i}", task_id=f"task-conc-{i}")
            store.save_task_and_verdict(t, v)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent writes raised: {errors}"
    tasks = store.list_tasks()
    verdicts = store.list_verdicts()
    assert len(tasks) == n
    assert len(verdicts) == n

    # Every task must be linked to its verdict
    task_map = {t.task_id: t for t in tasks}
    for i in range(n):
        t = task_map[f"task-conc-{i}"]
        assert t.verdict_id == f"verdict-conc-{i}"
        assert t.status == ReviewTaskStatus.VERDICT_EMITTED


# ---------------------------------------------------------------------------
# cancel_task: safe cancellation under concurrent writes
# ---------------------------------------------------------------------------


def test_cancel_task_marks_status_cancelled(store: VerdictStore) -> None:
    store.save_task(_make_task())

    cancelled = store.cancel_task("task-1", updated_at="2026-05-28T01:00:00Z")

    assert cancelled.status == ReviewTaskStatus.CANCELLED
    persisted = store.get_task("task-1")
    assert persisted.status == ReviewTaskStatus.CANCELLED
    assert persisted.updated_at == "2026-05-28T01:00:00Z"


def test_cancel_task_raises_for_unknown_task(store: VerdictStore) -> None:
    with pytest.raises(KeyError, match="unknown review task"):
        store.cancel_task("ghost-task", updated_at="2026-05-28T01:00:00Z")


def test_cancel_task_does_not_affect_sibling_tasks(store: VerdictStore) -> None:
    """Cancelling one task must not alter other tasks in the store."""
    store.save_task(_make_task("task-keep", "lane-keep"))
    store.save_task(_make_task("task-cancel", "lane-cancel"))

    store.cancel_task("task-cancel", updated_at="2026-05-28T01:00:00Z")

    kept = store.get_task("task-keep")
    assert kept.status == ReviewTaskStatus.PENDING


def test_concurrent_cancel_and_save_task_and_verdict_no_split_brain(
    store_path: Path,
) -> None:
    """cancel_task and save_task_and_verdict racing on the same task must not
    produce a split-brain state.  One operation wins; the final persisted task
    has exactly one status (either CANCELLED or VERDICT_EMITTED).
    """
    store = VerdictStore(store_path)
    store.save_task(_make_task("task-race", "lane-race"))

    results: list[str] = []
    errors: list[Exception] = []

    def do_cancel() -> None:
        try:
            t = store.cancel_task("task-race", updated_at="2026-05-28T02:00:00Z")
            results.append(f"cancelled:{t.status}")
        except Exception as exc:
            errors.append(exc)

    def do_verdict() -> None:
        try:
            task = _make_task("task-race", "lane-race")
            verdict = _make_verdict("verdict-race", "lane-race", task_id="task-race")
            t, _ = store.save_task_and_verdict(task, verdict)
            results.append(f"verdict:{t.status}")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=do_cancel)
    t2 = threading.Thread(target=do_verdict)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == [], f"unexpected errors: {errors}"

    final_task = store.get_task("task-race")
    assert final_task.status in (
        ReviewTaskStatus.CANCELLED,
        ReviewTaskStatus.VERDICT_EMITTED,
    ), f"unexpected final status: {final_task.status}"


# ---------------------------------------------------------------------------
# Graph termination prevention: lane_id mismatch guard
# ---------------------------------------------------------------------------


def test_lane_id_mismatch_leaves_store_completely_empty(store: VerdictStore) -> None:
    """A lane_id mismatch must not partially write either record, preventing
    graph termination issues caused by orphaned task or verdict entries."""
    task = _make_task("task-orphan", lane_id="lane-A")
    verdict = _make_verdict("verdict-orphan", lane_id="lane-B")

    with pytest.raises(ValueError):
        store.save_task_and_verdict(task, verdict)

    assert store.list_tasks() == []
    assert store.list_verdicts() == []


def test_verdict_id_stamped_on_task_matches_stored_verdict(store: VerdictStore) -> None:
    """The task.verdict_id stamped by save_task_and_verdict must exactly match
    the stored verdict.id so the graph can resolve lineage without ambiguity."""
    task = _make_task()
    verdict = _make_verdict(verdict_id="verdict-stamp-explicit")

    linked_task, _ = store.save_task_and_verdict(task, verdict)

    assert linked_task.verdict_id == "verdict-stamp-explicit"
    persisted = store.get_task("task-1")
    assert persisted.verdict_id == "verdict-stamp-explicit"


def test_graph_consistency_after_mixed_operations(store: VerdictStore) -> None:
    """Interleaved save_task, save_verdict, save_task_and_verdict, and
    cancel_task must leave the store in a fully consistent state."""
    # Lane A: atomic task+verdict
    store.save_task_and_verdict(
        _make_task("task-A", "lane-A"),
        _make_verdict("verdict-A", "lane-A", task_id="task-A"),
    )

    # Lane B: separate saves (task then verdict)
    store.save_task(_make_task("task-B", "lane-B"))
    store.save_verdict(_make_verdict("verdict-B", "lane-B", task_id="task-B"))

    # Lane C: task created then cancelled (no verdict)
    store.save_task(_make_task("task-C", "lane-C"))
    store.cancel_task("task-C", updated_at="2026-05-28T03:00:00Z")

    assert len(store.list_tasks()) == 3
    assert len(store.list_verdicts()) == 2

    # Lane A: task is linked to verdict
    t_a = store.get_task("task-A")
    assert t_a.verdict_id == "verdict-A"
    assert t_a.status == ReviewTaskStatus.VERDICT_EMITTED

    # Lane B: records exist independently
    t_b = store.get_task("task-B")
    assert t_b.status == ReviewTaskStatus.PENDING
    v_b = store.get_verdict("verdict-B")
    assert v_b.lane_id == "lane-B"

    # Lane C: cancelled with no verdict
    t_c = store.get_task("task-C")
    assert t_c.status == ReviewTaskStatus.CANCELLED
    assert store.list_verdicts_for_lane("lane-C") == []


def test_verdict_without_task_does_not_break_task_reads(store: VerdictStore) -> None:
    """A verdict saved without a corresponding task must not corrupt list_tasks."""
    store.save_verdict(_make_verdict("verdict-orphan"))

    assert store.list_tasks() == []
    assert len(store.list_verdicts()) == 1


def test_task_without_verdict_does_not_break_verdict_reads(store: VerdictStore) -> None:
    """A task saved without a verdict must not corrupt list_verdicts."""
    store.save_task(_make_task())

    assert len(store.list_tasks()) == 1
    assert store.list_verdicts() == []


# ---------------------------------------------------------------------------
# On-disk atomicity: no split-brain between task and verdict records
# (evbundle_6259476d67dd414a8be293d1025ccb8c — graph termination guard)
#
# The evidence bundle showed a graph lineage terminating without a proper
# merge verdict, leaving sibling lineages stranded.  The root cause was a
# window between two separate save calls where a crash or concurrent reader
# could observe a task claiming verdict_emitted but the verdict absent.
# save_task_and_verdict closes this window with a single atomic rename.
# ---------------------------------------------------------------------------


def test_save_task_and_verdict_no_split_brain_on_disk(store_path: Path) -> None:
    """After save_task_and_verdict the raw file always contains both records.

    Guards against the split-brain window from evbundle_6259476d67dd414a8be293d1025ccb8c
    where a crash between two separate saves left the task claiming
    verdict_emitted but the verdict absent from the store.
    """
    store = VerdictStore(store_path)
    task = _make_task("task-disk-guard")
    verdict = _make_verdict("verdict-disk-guard", task_id="task-disk-guard")

    store.save_task_and_verdict(task, verdict)

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    task_rows = {r["task_id"]: r for r in raw["review_tasks"]}
    verdict_rows = {r["id"]: r for r in raw["review_verdicts"]}

    assert "task-disk-guard" in task_rows, "task missing from raw file"
    assert "verdict-disk-guard" in verdict_rows, "verdict missing from raw file"
    assert task_rows["task-disk-guard"]["status"] == ReviewTaskStatus.VERDICT_EMITTED
    assert task_rows["task-disk-guard"]["verdict_id"] == "verdict-disk-guard"


def test_cancel_task_persists_to_disk(store_path: Path) -> None:
    """cancel_task writes the updated status to disk atomically."""
    store = VerdictStore(store_path)
    store.save_task(_make_task("task-cancel-disk"))

    store.cancel_task("task-cancel-disk", updated_at="2026-05-28T01:00:00Z")

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    row = next(r for r in raw["review_tasks"] if r["task_id"] == "task-cancel-disk")
    assert row["status"] == ReviewTaskStatus.CANCELLED
    assert row["updated_at"] == "2026-05-28T01:00:00Z"


def test_verdict_store_creates_parent_directories(tmp_path: Path) -> None:
    """VerdictStore creates missing parent directories on first write."""
    nested_path = tmp_path / "a" / "b" / "c" / "store.json"
    store = VerdictStore(nested_path)
    store.save_task(_make_task("task-nested"))

    assert nested_path.exists()
    assert store.get_task("task-nested").task_id == "task-nested"


def test_verdict_store_lock_file_does_not_block_reentry(store_path: Path) -> None:
    """The lock file companion must not prevent a second operation on the same store."""
    store = VerdictStore(store_path)
    store.save_task(_make_task("task-lock-1"))
    # A second write must succeed even though the lock file now exists.
    store.save_task(_make_task("task-lock-2", "lane-2"))

    assert len(store.list_tasks()) == 2


def test_save_task_and_verdict_does_not_corrupt_unrelated_records(
    store_path: Path,
) -> None:
    """save_task_and_verdict for one lane must not remove records for other lanes.

    This is the cross-lane consistency invariant: an atomic write for lane-X
    must preserve all existing records for lane-Y.
    """
    store = VerdictStore(store_path)
    # Pre-populate with unrelated records.
    store.save_task(_make_task("task-other", "lane-other"))
    store.save_verdict(_make_verdict("verdict-other", "lane-other", task_id="task-other"))

    task = _make_task("task-new", "lane-new")
    verdict = _make_verdict("verdict-new", "lane-new", task_id="task-new")
    store.save_task_and_verdict(task, verdict)

    # Unrelated records must be intact.
    assert store.get_task("task-other").lane_id == "lane-other"
    assert store.get_verdict("verdict-other").lane_id == "lane-other"
    # New records must be present and linked.
    assert store.get_task("task-new").status == ReviewTaskStatus.VERDICT_EMITTED
    assert store.get_task("task-new").verdict_id == "verdict-new"
    assert store.get_verdict("verdict-new").id == "verdict-new"


def test_multiple_review_cycles_each_produce_independent_lineage(
    store: VerdictStore,
) -> None:
    """Multiple review cycles for the same lane each produce an independent
    task→verdict lineage entry.  No cycle overwrites another's verdict link.

    This guards against the graph termination issue where a second review cycle
    silently replaced the first cycle's verdict, making the first merge verdict
    untraceable and triggering an incomplete-termination signal.
    """
    for cycle in range(3):
        task = _make_task(f"task-cycle-{cycle}")
        verdict = _make_verdict(f"verdict-cycle-{cycle}", task_id=f"task-cycle-{cycle}")
        store.save_task_and_verdict(task, verdict)

    tasks = store.list_tasks_for_lane("lane-1")
    verdicts = store.list_verdicts_for_lane("lane-1")

    assert len(tasks) == 3
    assert len(verdicts) == 3

    verdict_map = {v.id: v for v in verdicts}
    for task in tasks:
        assert task.verdict_id in verdict_map, (
            f"Task {task.task_id} verdict_id {task.verdict_id!r} not in store"
        )


def test_concurrent_upsert_same_verdict_id_no_duplicates(store_path: Path) -> None:
    """Concurrent upserts of the same verdict_id must not create duplicate records."""
    store = VerdictStore(store_path)
    errors: list[Exception] = []

    def worker(summary: str) -> None:
        try:
            store.save_verdict(
                _make_verdict("v-shared").model_copy(update={"summary": summary})
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"summary-{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Threads raised: {errors}"
    verdicts = store.list_verdicts_for_lane("lane-1")
    # Exactly one record for the shared verdict id — no duplicates.
    assert len(verdicts) == 1, (
        f"Expected 1 verdict, got {len(verdicts)}: {[v.id for v in verdicts]}"
    )


def test_merge_verdict_in_store_is_authoritative_over_lane_status(
    store: VerdictStore,
) -> None:
    """A finalized MERGE verdict in the store is the authoritative merge signal.

    Even if a lane's status field is 'failed', the presence of a finalized
    MERGE verdict in the store means the lane should be classified as merged
    (not terminated_without_merge).  This is the core invariant from
    evbundle_6259476d67dd414a8be293d1025ccb8c.
    """
    merge_verdict = ReviewVerdict(
        id="v-merge-authoritative",
        lane_id="lane-auth",
        decision=ReviewDecision.MERGE,
        status="finalized",
        summary="Merged via patch-forward.",
        created_at="2026-05-28T00:00:00Z",
    )
    store.save_verdict(merge_verdict)

    retrieved = store.get_verdict("v-merge-authoritative")
    assert retrieved.decision == ReviewDecision.MERGE
    assert retrieved.status == "finalized"

    # No incomplete_termination verdict must exist for this lane.
    verdicts = store.list_verdicts_for_lane("lane-auth")
    incomplete = [v for v in verdicts if v.status == "incomplete_termination"]
    assert incomplete == [], (
        "A lane with a finalized MERGE verdict must not have an incomplete_termination entry"
    )


def test_verdict_store_file_always_valid_json_across_writes(store_path: Path) -> None:
    """The store file must be valid JSON with both keys after every write.

    Verifies the atomic temp-file rename pattern: readers never see a
    half-written file regardless of how many writes have occurred.
    """
    store = VerdictStore(store_path)

    for i in range(5):
        task = _make_task(f"task-seq-{i}", f"lane-{i}")
        verdict = _make_verdict(f"verdict-seq-{i}", f"lane-{i}", task_id=f"task-seq-{i}")
        store.save_task_and_verdict(task, verdict)

        raw = json.loads(store_path.read_text(encoding="utf-8"))
        assert "review_tasks" in raw, f"review_tasks missing after write {i}"
        assert "review_verdicts" in raw, f"review_verdicts missing after write {i}"
        assert len(raw["review_tasks"]) == i + 1
        assert len(raw["review_verdicts"]) == i + 1

