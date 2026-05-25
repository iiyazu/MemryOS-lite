"""Unified dispatch worklist with dedup, depth limit, and abort signal.

Design reference: cat-cafe-tutorials/04-a2a-routing.md (F27 unification).
All agent routing converges through this single worklist to prevent
dual-fire, enforce depth limits, and propagate cancellation.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

MAX_DISPATCH_DEPTH = 15


@dataclass
class DispatchEntry:
    target_id: str
    source_id: str
    enqueued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    depth: int = 0


@dataclass
class DispatchChain:
    """Tracks dispatch depth and provides shared cancellation signal."""

    depth: int = 0
    max_depth: int = MAX_DISPATCH_DEPTH
    _abort: threading.Event = field(default_factory=threading.Event)

    def can_dispatch(self) -> bool:
        return self.depth < self.max_depth and not self._abort.is_set()

    def abort(self) -> None:
        self._abort.set()

    @property
    def aborted(self) -> bool:
        return self._abort.is_set()

    def child(self) -> DispatchChain:
        return DispatchChain(
            depth=self.depth + 1,
            max_depth=self.max_depth,
            _abort=self._abort,
        )


class Worklist:
    """Unified dispatch queue. All routing converges here.

    Thread-safe. Supports dedup, depth-guarded enqueue, and ordered consume.
    """

    def __init__(self, chain: DispatchChain | None = None) -> None:
        self._chain = chain or DispatchChain()
        self._queue: deque[DispatchEntry] = deque()
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self._history: list[dict[str, Any]] = []

    @property
    def chain(self) -> DispatchChain:
        return self._chain

    def enqueue(self, target_id: str, source_id: str) -> bool:
        """Add target to worklist. Returns False if deduped or depth exceeded."""
        with self._lock:
            if target_id in self._seen:
                return False
            if not self._chain.can_dispatch():
                return False
            entry = DispatchEntry(
                target_id=target_id,
                source_id=source_id,
                depth=self._chain.depth,
            )
            self._queue.append(entry)
            self._seen.add(target_id)
            return True

    def consume(self) -> DispatchEntry | None:
        """Pop next entry for execution. Returns None if empty or aborted."""
        with self._lock:
            if self._chain.aborted or not self._queue:
                return None
            entry = self._queue.popleft()
            self._history.append(
                {"target_id": entry.target_id, "source_id": entry.source_id, "depth": entry.depth}
            )
            return entry

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pending": len(self._queue),
                "seen": sorted(self._seen),
                "depth": self._chain.depth,
                "aborted": self._chain.aborted,
                "history": list(self._history),
            }
