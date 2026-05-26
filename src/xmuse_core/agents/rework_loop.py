from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from xmuse_core.agents.consumer import TaskDescriptor
from xmuse_core.agents.quality_gate import GateResult


@dataclass
class LaneResult:
    status: Literal["done", "failed"]
    attempts: int
    final_errors: list[str] = field(default_factory=list)


class ErrorKnowledgeLike(Protocol):
    def inject_context(self, prompt: str) -> str: ...


class QualityGateLike(Protocol):
    def check(self, worktree: Path) -> GateResult | Awaitable[GateResult]: ...


class ReworkLoop:
    def __init__(self, error_knowledge: ErrorKnowledgeLike | None = None) -> None:
        self._error_knowledge = error_knowledge

    async def run(
        self,
        lane: TaskDescriptor,
        initial_gate_result: GateResult,
        dispatch_fn: Callable[[str, str], Any],
        gate: QualityGateLike,
        max_retries: int = 3,
    ) -> LaneResult:
        accumulated_errors = list(initial_gate_result.errors)
        current_errors = list(initial_gate_result.errors)
        retry_count = max(0, max_retries)

        for attempt in range(1, retry_count + 1):
            rework_prompt = self._build_rework_prompt(lane.prompt, current_errors, attempt)
            dispatch_result = dispatch_fn(rework_prompt, lane.worktree)
            if inspect.isawaitable(dispatch_result):
                await dispatch_result

            gate_result_or_awaitable = gate.check(Path(lane.worktree))
            if inspect.isawaitable(gate_result_or_awaitable):
                gate_result = await gate_result_or_awaitable
            else:
                gate_result = gate_result_or_awaitable

            if gate_result.passed:
                return LaneResult(status="done", attempts=attempt, final_errors=[])

            current_errors = list(gate_result.errors)
            accumulated_errors.extend(current_errors)

        return LaneResult(
            status="failed",
            attempts=retry_count,
            final_errors=accumulated_errors,
        )

    def _build_rework_prompt(
        self,
        original_prompt: str,
        gate_errors: list[str],
        attempt: int,
    ) -> str:
        formatted_errors = "\n".join(f"- {error}" for error in gate_errors) or "- <none>"
        prompt = (
            f"Original prompt:\n{original_prompt}\n\n"
            f"Attempt {attempt}\n\n"
            f"Gate errors:\n{formatted_errors}\n\n"
            "Rework the lane so the quality gate passes."
        )
        if self._error_knowledge is None:
            return prompt
        return self._error_knowledge.inject_context(prompt)
