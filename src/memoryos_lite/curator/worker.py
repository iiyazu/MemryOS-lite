"""Background poller that drives ``Curator.run_session`` for active sessions."""

from __future__ import annotations

import logging
import threading

from memoryos_lite.curator.runner import Curator

logger = logging.getLogger(__name__)


class CuratorWorker:
    """Daemon thread polling for sessions with unprocessed messages.

    The worker only decides *when* to tick; ``run_session`` itself decides
    window and idle-flush eligibility, so direct callers and the worker share
    exactly one trigger implementation.
    """

    def __init__(self, curator: Curator, *, poll_s: float) -> None:
        self.curator = curator
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="memoryos-curator",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                logger.warning(
                    "curator worker tick failed: %s",
                    type(exc).__name__,
                )
            self._stop.wait(self.poll_s)

    def tick(self) -> int:
        """Run one poll pass; return the number of sessions that ran."""

        ran = 0
        for session_id in self.curator.store.list_curator_session_ids():
            try:
                result = self.curator.run_session(session_id)
            except Exception as exc:
                logger.warning(
                    "curator run failed for session %s: %s",
                    session_id,
                    type(exc).__name__,
                )
                continue
            if result.windows or result.status in {"failed", "skipped"}:
                ran += 1
        return ran
