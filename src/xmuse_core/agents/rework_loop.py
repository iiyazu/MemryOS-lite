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
    final_gate_result: Any | None = None


class ErrorKnowledgeLike(Protocol):
    def inject_context(self, prompt: str) -> str: ...


class QualityGateLike(Protocol):
    def check(
        self,
        worktree: Path,
        **kwargs: Any,
    ) -> GateResult | Awaitable[GateResult]: ...


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

            gate_result_or_awaitable = self._check_gate(gate, lane)
            if inspect.isawaitable(gate_result_or_awaitable):
                gate_result = await gate_result_or_awaitable
            else:
                gate_result = gate_result_or_awaitable

            if gate_result.passed:
                return LaneResult(
                    status="done",
                    attempts=attempt,
                    final_errors=[],
                    final_gate_result=gate_result,
                )

            current_errors = list(gate_result.errors)
            accumulated_errors.extend(current_errors)

        return LaneResult(
            status="failed",
            attempts=retry_count,
            final_errors=accumulated_errors,
        )

    def _check_gate(
        self,
        gate: QualityGateLike,
        lane: TaskDescriptor,
    ) -> GateResult | Awaitable[GateResult]:
        kwargs = {
            "feature_id": lane.feature_id,
            "gate_profile": lane.gate_profile,
            "gate_profiles": lane.gate_profiles,
            "base_head_sha": lane.base_head_sha,
        }
        signature = inspect.signature(gate.check)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        accepted = {
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind
            in {
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        }
        if accepts_kwargs or any(name in accepted for name in kwargs):
            filtered = (
                kwargs
                if accepts_kwargs
                else {key: value for key, value in kwargs.items() if key in accepted}
            )
            return gate.check(Path(lane.worktree), **filtered)
        return gate.check(Path(lane.worktree))

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
