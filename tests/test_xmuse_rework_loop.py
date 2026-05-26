from __future__ import annotations

import pytest

from xmuse_core.agents.consumer import TaskDescriptor
from xmuse_core.agents.quality_gate import GateResult
from xmuse_core.agents.rework_loop import ReworkLoop


class FakeGate:
    def __init__(self, results: list[GateResult]) -> None:
        self._results = results
        self.checked_worktrees: list[str] = []

    def check(self, worktree: str | Path) -> GateResult:
        self.checked_worktrees.append(str(worktree))
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_rework_loop_retries_until_gate_passes() -> None:
    lane = TaskDescriptor(
        feature_id="feature-1",
        task_type="rework",
        prompt="Implement the parser.",
        worktree="/tmp/worktree",
    )
    dispatched: list[tuple[str, str]] = []

    async def dispatch_fn(prompt: str, worktree: str) -> None:
        dispatched.append((prompt, worktree))

    gate = FakeGate([
        GateResult(passed=False, errors=["missing test"]),
        GateResult(passed=True, errors=[]),
    ])

    result = await ReworkLoop().run(
        lane=lane,
        initial_gate_result=GateResult(passed=False, errors=["ruff failed"]),
        dispatch_fn=dispatch_fn,
        gate=gate,
        max_retries=3,
    )

    assert result.status == "done"
    assert result.attempts == 2
    assert result.final_errors == []
    assert len(dispatched) == 2
    assert dispatched[0][1] == "/tmp/worktree"
    assert "Implement the parser." in dispatched[0][0]
    assert "ruff failed" in dispatched[0][0]
    assert "Attempt 1" in dispatched[0][0]
    assert "missing test" in dispatched[1][0]
    assert "Attempt 2" in dispatched[1][0]
    assert gate.checked_worktrees == ["/tmp/worktree", "/tmp/worktree"]


@pytest.mark.asyncio
async def test_rework_loop_returns_accumulated_errors_when_retries_exhausted() -> None:
    lane = TaskDescriptor(
        feature_id="feature-1",
        task_type="rework",
        prompt="Fix the feature.",
        worktree="/tmp/worktree",
    )
    prompts: list[str] = []

    async def dispatch_fn(prompt: str, worktree: str) -> None:
        prompts.append(prompt)

    gate = FakeGate([
        GateResult(passed=False, errors=["tests still fail"]),
        GateResult(passed=False, errors=["mypy still fails"]),
    ])

    result = await ReworkLoop().run(
        lane=lane,
        initial_gate_result=GateResult(passed=False, errors=["initial failure"]),
        dispatch_fn=dispatch_fn,
        gate=gate,
        max_retries=2,
    )

    assert result.status == "failed"
    assert result.attempts == 2
    assert result.final_errors == [
        "initial failure",
        "tests still fail",
        "mypy still fails",
    ]
    assert len(prompts) == 2
    assert "initial failure" in prompts[0]
    assert "tests still fail" in prompts[1]
