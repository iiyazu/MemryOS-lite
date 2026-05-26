from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from xmuse_core.agents.registry import AgentRegistry, AgentRuntime

logger = logging.getLogger(__name__)


@dataclass
class TaskDescriptor:
    feature_id: str
    task_type: str
    prompt: str
    worktree: str = "."
    required_capabilities: list[str] = field(default_factory=lambda: ["code"])
    developed_by_runtime: AgentRuntime | None = None
    priority: int = 0


class WorklistConsumer:
    def __init__(
        self,
        registry: AgentRegistry,
        session_mgr,
        max_concurrent: int = 4,
        on_complete: Callable[[str, str], None] | None = None,
    ) -> None:
        self._queue: asyncio.Queue[TaskDescriptor] = asyncio.Queue()
        self._registry = registry
        self._session_mgr = session_mgr
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._in_flight: set[asyncio.Task[None]] = set()
        self._shutdown_event = asyncio.Event()
        self._running_task: asyncio.Task | None = None
        self._on_complete = on_complete

    async def run(self) -> None:
        self._running_task = asyncio.current_task()
        try:
            while not self._shutdown_event.is_set():
                try:
                    task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except TimeoutError:
                    if not self._in_flight and self._queue.empty():
                        break
                    continue
                lane_task = asyncio.create_task(self._dispatch_task(task))
                self._in_flight.add(lane_task)
                lane_task.add_done_callback(self._in_flight.discard)
        finally:
            await self.drain()

    async def _dispatch_task(self, task: TaskDescriptor) -> None:
        status = "failed"
        try:
            async with self._semaphore:
                agent = self._registry.select(
                    task.required_capabilities,
                    exclude_runtime=task.developed_by_runtime,
                )
                result = await self._session_mgr.dispatch_one_shot(
                    agent=agent,
                    feature_id=task.feature_id,
                    prompt=task.prompt,
                    worktree=Path(task.worktree),
                )
                status = "done" if result and result.status == "success" else "failed"
        except Exception:
            logger.exception("worklist dispatch failed for feature_id=%s", task.feature_id)
        finally:
            if self._on_complete:
                try:
                    self._on_complete(task.feature_id, status)
                except Exception:
                    logger.exception(
                        "worklist on_complete failed for feature_id=%s",
                        task.feature_id,
                    )

    async def dispatch_task(self, task: TaskDescriptor) -> str:
        """Public dispatch: run a single task and return status ('done'|'failed')."""
        status = "failed"
        try:
            async with self._semaphore:
                agent = self._registry.select(
                    task.required_capabilities,
                    exclude_runtime=task.developed_by_runtime,
                )
                result = await self._session_mgr.dispatch_one_shot(
                    agent=agent,
                    feature_id=task.feature_id,
                    prompt=task.prompt,
                    worktree=Path(task.worktree),
                )
                status = "done" if result and result.status == "success" else "failed"
        except Exception:
            logger.exception("dispatch_task failed for feature_id=%s", task.feature_id)
        return status

    async def drain(self) -> None:
        while self._in_flight:
            await asyncio.gather(*self._in_flight)

    async def enqueue(self, task: TaskDescriptor) -> None:
        await self._queue.put(task)

    def shutdown(self) -> None:
        self._shutdown_event.set()

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()
