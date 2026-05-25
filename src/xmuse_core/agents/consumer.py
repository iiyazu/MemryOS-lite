from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from xmuse_core.agents.registry import AgentRegistry, AgentRuntime


@dataclass
class TaskDescriptor:
    feature_id: str
    task_type: Literal["execute", "review", "rework"]
    prompt: str
    worktree: str = "."
    required_capabilities: list[str] = field(default_factory=lambda: ["code"])
    developed_by_runtime: AgentRuntime | None = None


class WorklistConsumer:
    def __init__(
        self,
        registry: AgentRegistry,
        session_mgr,
        max_concurrent: int = 4,
    ) -> None:
        self._queue: asyncio.Queue[TaskDescriptor] = asyncio.Queue()
        self._registry = registry
        self._session_mgr = session_mgr
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._shutdown_event = asyncio.Event()
        self._running_task: asyncio.Task | None = None

    async def run(self) -> None:
        self._running_task = asyncio.current_task()
        while not self._shutdown_event.is_set():
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            async with self._semaphore:
                agent = self._registry.select(
                    task.required_capabilities,
                    exclude_runtime=task.developed_by_runtime,
                )
                await self._session_mgr.dispatch_one_shot(
                    agent=agent,
                    feature_id=task.feature_id,
                    prompt=task.prompt,
                    worktree=Path(task.worktree),
                )

    async def enqueue(self, task: TaskDescriptor) -> None:
        await self._queue.put(task)

    def shutdown(self) -> None:
        self._shutdown_event.set()

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()
