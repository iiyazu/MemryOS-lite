from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Generator

from xmuse_core.structuring.models import (
    ClarificationObject,
    ClarificationStatus,
    ReviewTask,
    ReviewTaskStatus,
    ReviewVerdict,
    StructuredEvidenceBundle,
)

# ---------------------------------------------------------------------------
# Cross-process advisory file locking (POSIX only; no-op on Windows)
# ---------------------------------------------------------------------------
try:
    import fcntl as _fcntl

    def _flock_exclusive(fd: Any) -> None:  # type: ignore[misc]
        _fcntl.flock(fd, _fcntl.LOCK_EX)

    def _flock_release(fd: Any) -> None:  # type: ignore[misc]
        _fcntl.flock(fd, _fcntl.LOCK_UN)

except ImportError:  # pragma: no cover – Windows
    def _flock_exclusive(fd: Any) -> None:  # type: ignore[misc]
        pass

    def _flock_release(fd: Any) -> None:  # type: ignore[misc]
        pass


# ---------------------------------------------------------------------------
# Per-path in-process locks (prevents intra-process races without fork)
# ---------------------------------------------------------------------------
_STORE_LOCKS: dict[str, threading.Lock] = {}
_STORE_LOCKS_GUARD = threading.Lock()


def _get_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _STORE_LOCKS_GUARD:
        if key not in _STORE_LOCKS:
            _STORE_LOCKS[key] = threading.Lock()
        return _STORE_LOCKS[key]


@contextmanager
def _locked(path: Path) -> Generator[None, None, None]:
    """Acquire both the in-process threading lock and a POSIX advisory flock."""
    thread_lock = _get_lock(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with thread_lock:
        lock_fd = lock_path.open("a")
        try:
            _flock_exclusive(lock_fd)
            try:
                yield
            finally:
                _flock_release(lock_fd)
        finally:
            lock_fd.close()


class VerdictStore:
    """Persistent store for ReviewVerdict and ReviewTask objects.

    Both collections live in a single JSON file so that the task→verdict
    relation is always co-located and readable without cross-file joins.

    Atomicity guarantees
    --------------------
    Every mutating operation acquires an in-process ``threading.Lock`` *and* a
    POSIX advisory ``flock`` on a companion ``.lock`` file before reading the
    current snapshot, applying the mutation, and writing the result via an
    atomic ``rename``.  This prevents:

    * **Lost-update races** – two concurrent ``save_verdict`` calls cannot
      silently overwrite each other.
    * **Partial-write corruption** – the ``NamedTemporaryFile`` + ``replace``
      pattern ensures readers never see a half-written file.
    * **Task/verdict split-brain** – :meth:`save_task_and_verdict` writes both
      records in a single locked transaction; a crash between the two
      individual saves can no longer leave the graph in an inconsistent state.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    # ------------------------------------------------------------------
    # ReviewTask
    # ------------------------------------------------------------------

    def save_task(self, task: ReviewTask) -> ReviewTask:
        with _locked(self._path):
            data = self._read_unsafe()
            tasks = data.setdefault("review_tasks", [])
            data["review_tasks"] = [
                row for row in tasks
                if isinstance(row, dict) and row.get("task_id") != task.task_id
            ]
            data["review_tasks"].append(task.model_dump(mode="json"))
            self._write_unsafe(data)
        return task

    def cancel_task(self, task_id: str, *, updated_at: str) -> ReviewTask:
        """Atomically mark *task_id* as cancelled.

        The read-modify-write is performed inside a single lock acquisition so
        a concurrent ``save_task_and_verdict`` call cannot silently overwrite
        the cancellation (and vice-versa).

        Raises:
            KeyError: If *task_id* does not exist in the store.
        """
        with _locked(self._path):
            data = self._read_unsafe()
            tasks = data.get("review_tasks", [])
            target: dict | None = None
            for row in tasks:
                if isinstance(row, dict) and row.get("task_id") == task_id:
                    target = row
                    break
            if target is None:
                raise KeyError(f"unknown review task: {task_id}")
            target["status"] = ReviewTaskStatus.CANCELLED
            target["updated_at"] = updated_at
            self._write_unsafe(data)
            return ReviewTask.model_validate(target)

    def get_task(self, task_id: str) -> ReviewTask:
        for row in self._read().get("review_tasks", []):
            if isinstance(row, dict) and row.get("task_id") == task_id:
                return ReviewTask.model_validate(row)
        raise KeyError(f"unknown review task: {task_id}")

    def list_tasks(self) -> list[ReviewTask]:
        return [
            ReviewTask.model_validate(row)
            for row in self._read().get("review_tasks", [])
            if isinstance(row, dict)
        ]

    def list_tasks_for_lane(self, lane_id: str) -> list[ReviewTask]:
        return [t for t in self.list_tasks() if t.lane_id == lane_id]

    # ------------------------------------------------------------------
    # ReviewVerdict
    # ------------------------------------------------------------------

    def save_verdict(self, verdict: ReviewVerdict) -> ReviewVerdict:
        with _locked(self._path):
            data = self._read_unsafe()
            verdicts = data.setdefault("review_verdicts", [])
            data["review_verdicts"] = [
                row for row in verdicts
                if isinstance(row, dict) and row.get("id") != verdict.id
            ]
            data["review_verdicts"].append(verdict.model_dump(mode="json"))
            self._write_unsafe(data)
        return verdict

    def get_verdict(self, verdict_id: str) -> ReviewVerdict:
        for row in self._read().get("review_verdicts", []):
            if isinstance(row, dict) and row.get("id") == verdict_id:
                return ReviewVerdict.model_validate(row)
        raise KeyError(f"unknown review verdict: {verdict_id}")

    def list_verdicts(self) -> list[ReviewVerdict]:
        return [
            ReviewVerdict.model_validate(row)
            for row in self._read().get("review_verdicts", [])
            if isinstance(row, dict)
        ]

    def list_verdicts_for_lane(self, lane_id: str) -> list[ReviewVerdict]:
        return [v for v in self.list_verdicts() if v.lane_id == lane_id]

    # ------------------------------------------------------------------
    # Atomic task + verdict transaction
    # ------------------------------------------------------------------

    def save_task_and_verdict(
        self,
        task: ReviewTask,
        verdict: ReviewVerdict,
    ) -> tuple[ReviewTask, ReviewVerdict]:
        """Persist *task* and *verdict* atomically in a single locked write.

        This is the preferred entry-point for Review GOD when emitting a
        verdict.  It guarantees that:

        1. The task's ``status`` is set to ``verdict_emitted`` and its
           ``verdict_id`` is linked to ``verdict.id`` before the write.
        2. Both records land in the store together – there is no window where
           the task claims ``verdict_emitted`` but the verdict does not yet
           exist, or vice versa.
        3. If the write fails for any reason the store is left unchanged
           (the temp-file rename is the commit point).

        Args:
            task: The :class:`ReviewTask` to upsert.  Its ``status`` and
                ``verdict_id`` fields will be overwritten to reflect the
                emitted verdict.
            verdict: The :class:`ReviewVerdict` to upsert.

        Returns:
            A ``(task, verdict)`` tuple with the final persisted state.

        Raises:
            ValueError: If ``verdict.lane_id != task.lane_id``.
        """
        if verdict.lane_id != task.lane_id:
            raise ValueError(
                f"lane_id mismatch: task.lane_id={task.lane_id!r} "
                f"verdict.lane_id={verdict.lane_id!r}"
            )

        # Stamp the task as verdict_emitted and link it to the verdict.
        linked_task = task.model_copy(
            update={
                "status": ReviewTaskStatus.VERDICT_EMITTED,
                "verdict_id": verdict.id,
            }
        )

        with _locked(self._path):
            data = self._read_unsafe()

            # Upsert task
            tasks = data.setdefault("review_tasks", [])
            data["review_tasks"] = [
                row for row in tasks
                if isinstance(row, dict) and row.get("task_id") != linked_task.task_id
            ]
            data["review_tasks"].append(linked_task.model_dump(mode="json"))

            # Upsert verdict
            verdicts = data.setdefault("review_verdicts", [])
            data["review_verdicts"] = [
                row for row in verdicts
                if isinstance(row, dict) and row.get("id") != verdict.id
            ]
            data["review_verdicts"].append(verdict.model_dump(mode="json"))

            # Single atomic write – this is the commit point.
            self._write_unsafe(data)

        return linked_task, verdict

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        """Thread-safe read (acquires lock internally)."""
        with _locked(self._path):
            return self._read_unsafe()

    def _read_unsafe(self) -> dict[str, Any]:
        """Read without acquiring the lock – caller must hold it."""
        if not self._path.exists():
            return {"review_tasks": [], "review_verdicts": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"review_tasks": [], "review_verdicts": []}
        return (
            payload
            if isinstance(payload, dict)
            else {"review_tasks": [], "review_verdicts": []}
        )

    def _write_unsafe(self, data: dict[str, Any]) -> None:
        """Write without acquiring the lock – caller must hold it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f"{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self._path)


class ClarificationStore:
    """Persistent store for ClarificationObject records.

    A clarification object represents a blocked-for-input state for a lane
    that cannot proceed without external information.  The store is the
    authoritative source for open clarifications used by the run-level
    terminal aggregation contract.

    Records are append-only: resolving or cancelling a clarification updates
    its status in place rather than removing it, preserving the full audit
    trail.

    All mutating operations are serialised via the same two-layer locking
    scheme used by :class:`VerdictStore` (in-process ``threading.Lock`` +
    POSIX advisory ``flock``).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def open_clarification(
        self,
        *,
        clarification_id: str,
        lane_id: str,
        question: str,
        graph_id: str | None = None,
        resolution_id: str | None = None,
        context: dict | None = None,
        created_at: str,
    ) -> ClarificationObject:
        """Create and persist a new open clarification for *lane_id*.

        If a clarification with the same *clarification_id* already exists it
        is returned as-is (idempotent).
        """
        with _locked(self._path):
            data = self._read_unsafe()
            for row in data.get("clarifications", []):
                if (
                    isinstance(row, dict)
                    and row.get("clarification_id") == clarification_id
                ):
                    return ClarificationObject.model_validate(row)

            obj = ClarificationObject(
                clarification_id=clarification_id,
                lane_id=lane_id,
                graph_id=graph_id,
                resolution_id=resolution_id,
                question=question,
                context=context or {},
                status=ClarificationStatus.OPEN,
                created_at=created_at,
            )
            data.setdefault("clarifications", []).append(obj.model_dump(mode="json"))
            self._write_unsafe(data)
        return obj

    def resolve(
        self,
        clarification_id: str,
        *,
        answer: str,
        resolved_by: str | None = None,
        updated_at: str,
    ) -> ClarificationObject:
        """Mark a clarification as resolved with the provided *answer*."""
        with _locked(self._path):
            data = self._read_unsafe()
            for row in data.get("clarifications", []):
                if isinstance(row, dict) and row.get("clarification_id") == clarification_id:
                    row["status"] = ClarificationStatus.RESOLVED
                    row["answer"] = answer
                    row["resolved_by"] = resolved_by
                    row["updated_at"] = updated_at
                    self._write_unsafe(data)
                    return ClarificationObject.model_validate(row)
        raise KeyError(f"unknown clarification: {clarification_id}")

    def cancel(
        self,
        clarification_id: str,
        *,
        updated_at: str,
    ) -> ClarificationObject:
        """Mark a clarification as cancelled (e.g. lane was terminated)."""
        with _locked(self._path):
            data = self._read_unsafe()
            for row in data.get("clarifications", []):
                if isinstance(row, dict) and row.get("clarification_id") == clarification_id:
                    row["status"] = ClarificationStatus.CANCELLED
                    row["updated_at"] = updated_at
                    self._write_unsafe(data)
                    return ClarificationObject.model_validate(row)
        raise KeyError(f"unknown clarification: {clarification_id}")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, clarification_id: str) -> ClarificationObject:
        obj = self._find(clarification_id)
        if obj is None:
            raise KeyError(f"unknown clarification: {clarification_id}")
        return obj

    def list_open_for_lane(self, lane_id: str) -> list[ClarificationObject]:
        """Return all open clarifications for *lane_id*."""
        return [
            c for c in self._list_all()
            if c.lane_id == lane_id and c.status == ClarificationStatus.OPEN
        ]

    def list_open_for_graph(self, graph_id: str) -> list[ClarificationObject]:
        """Return all open clarifications for any lane in *graph_id*.

        Also includes clarifications whose lane belongs to the graph via
        ``graph_id`` on the clarification object itself.  Callers that need
        full lineage closure (patch-forward descendants) should use
        :meth:`list_open_for_lane_set` with the expanded lane ID set.
        """
        return [
            c for c in self._list_all()
            if c.graph_id == graph_id and c.status == ClarificationStatus.OPEN
        ]

    def list_open_for_lane_set(self, lane_ids: set[str]) -> list[ClarificationObject]:
        """Return all open clarifications whose lane_id is in *lane_ids*."""
        return [
            c for c in self._list_all()
            if c.lane_id in lane_ids and c.status == ClarificationStatus.OPEN
        ]

    def list_all(self) -> list[ClarificationObject]:
        return self._list_all()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find(self, clarification_id: str) -> ClarificationObject | None:
        for row in self._read().get("clarifications", []):
            if isinstance(row, dict) and row.get("clarification_id") == clarification_id:
                return ClarificationObject.model_validate(row)
        return None

    def _list_all(self) -> list[ClarificationObject]:
        return [
            ClarificationObject.model_validate(row)
            for row in self._read().get("clarifications", [])
            if isinstance(row, dict)
        ]

    def _read(self) -> dict[str, Any]:
        with _locked(self._path):
            return self._read_unsafe()

    def _read_unsafe(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"clarifications": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"clarifications": []}
        return payload if isinstance(payload, dict) else {"clarifications": []}

    def _write_unsafe(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f"{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self._path)


class EvidenceBundleStore:
    """Persistent store for StructuredEvidenceBundle objects.

    Bundles are append-only: saving a bundle with an existing ``bundle_id``
    replaces the prior record (idempotent upsert), but the store never
    silently drops older bundles for the same run.

    All mutating operations are serialised via the same two-layer locking
    scheme used by :class:`VerdictStore`.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def save(self, bundle: StructuredEvidenceBundle) -> StructuredEvidenceBundle:
        with _locked(self._path):
            data = self._read_unsafe()
            bundles = data.setdefault("evidence_bundles", [])
            data["evidence_bundles"] = [
                row for row in bundles
                if isinstance(row, dict) and row.get("bundle_id") != bundle.bundle_id
            ]
            data["evidence_bundles"].append(bundle.model_dump(mode="json"))
            self._write_unsafe(data)
        return bundle

    def get(self, bundle_id: str) -> StructuredEvidenceBundle:
        for row in self._read().get("evidence_bundles", []):
            if isinstance(row, dict) and row.get("bundle_id") == bundle_id:
                return StructuredEvidenceBundle.model_validate(row)
        raise KeyError(f"unknown evidence bundle: {bundle_id}")

    def list_for_run(self, source_run_id: str) -> list[StructuredEvidenceBundle]:
        return [
            StructuredEvidenceBundle.model_validate(row)
            for row in self._read().get("evidence_bundles", [])
            if isinstance(row, dict) and row.get("source_run_id") == source_run_id
        ]

    def list_all(self) -> list[StructuredEvidenceBundle]:
        return [
            StructuredEvidenceBundle.model_validate(row)
            for row in self._read().get("evidence_bundles", [])
            if isinstance(row, dict)
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        with _locked(self._path):
            return self._read_unsafe()

    def _read_unsafe(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"evidence_bundles": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"evidence_bundles": []}
        return payload if isinstance(payload, dict) else {"evidence_bundles": []}

    def _write_unsafe(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f"{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self._path)
