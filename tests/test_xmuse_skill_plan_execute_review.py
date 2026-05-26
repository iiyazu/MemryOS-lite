from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xmuse"))
from skills.plan_execute_review import PlanExecuteReviewSkill
from xmuse_core.agents.protocol import AgentOutput
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime


class FakeRegistry:
    def __init__(self) -> None:
        self.selected: list[list[str]] = []

    def select(self, required: list[str]) -> AgentDescriptor:
        self.selected.append(required)
        return AgentDescriptor(
            runtime=AgentRuntime.CODEX,
            name=f"agent-{len(self.selected)}",
            capabilities=required,
        )


class FakeSessionManager:
    def __init__(self, outputs: list[AgentOutput]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    async def dispatch_one_shot(
        self,
        *,
        agent: AgentDescriptor,
        feature_id: str,
        prompt: str,
        worktree: Path,
        context: str = "",
    ) -> AgentOutput:
        self.calls.append(
            {
                "agent": agent,
                "feature_id": feature_id,
                "prompt": prompt,
                "worktree": worktree,
                "context": context,
            }
        )
        return self.outputs.pop(0)


def _skill(
    tmp_path: Path,
    manager: FakeSessionManager,
    *,
    max_rework_attempts: int = 1,
    skip_plan: bool = False,
) -> PlanExecuteReviewSkill:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    return PlanExecuteReviewSkill(
        registry=FakeRegistry(),
        session_manager=manager,
        feature_root=tmp_path / "features",
        worktree_resolver=lambda _feature_id: worktree,
        max_rework_attempts=max_rework_attempts,
        skip_plan=skip_plan,
    )


@pytest.mark.asyncio
async def test_plan_dispatches_planner_and_returns_plan_md(tmp_path: Path) -> None:
    manager = FakeSessionManager(
        [AgentOutput(status="success", artifacts={"stdout": "# Plan\n\nDo the work.\n"})]
    )
    skill = _skill(tmp_path, manager)

    plan_path = await skill.plan("feature-a", "Add reusable orchestration.")

    assert plan_path == tmp_path / "features" / "feature-a" / "plan.md"
    assert plan_path.read_text() == "# Plan\n\nDo the work.\n"
    call = manager.calls[0]
    assert "Add reusable orchestration." in str(call["prompt"])
    assert "plan.md" in str(call["prompt"])
    assert call["context"] == ""


@pytest.mark.asyncio
async def test_run_orchestrates_plan_execute_and_passing_review(tmp_path: Path) -> None:
    manager = FakeSessionManager(
        [
            AgentOutput(status="success", artifacts={"stdout": "# Plan\n\nImplement tests first."}),
            AgentOutput(status="success", artifacts={"stdout": "implemented"}),
            AgentOutput(status="success", artifacts={"stdout": '{"verdict": "PASS"}'}),
        ]
    )
    skill = _skill(tmp_path, manager)

    result = await skill.run("feature-a", "Ship a tested feature.")

    assert result.status == "done"
    assert result.rework_attempts == 0
    assert result.review.passed is True
    assert len(manager.calls) == 3
    assert "planning node" in str(manager.calls[0]["prompt"])
    assert "execute node" in str(manager.calls[1]["prompt"])
    assert "# Plan\n\nImplement tests first." in str(manager.calls[1]["context"])
    assert "review node" in str(manager.calls[2]["prompt"])


@pytest.mark.asyncio
async def test_run_reworks_failed_review_until_pass(tmp_path: Path) -> None:
    manager = FakeSessionManager(
        [
            AgentOutput(status="success", artifacts={"stdout": "# Plan\n"}),
            AgentOutput(status="success", artifacts={"stdout": "implemented"}),
            AgentOutput(
                status="success",
                artifacts={
                    "stdout": '{"verdict": "FAIL", "blocking_findings": ["missing tests"]}'
                },
            ),
            AgentOutput(status="success", artifacts={"stdout": "reworked"}),
            AgentOutput(status="success", artifacts={"stdout": '{"verdict": "PASS"}'}),
        ]
    )
    skill = _skill(tmp_path, manager, max_rework_attempts=2)

    result = await skill.run("feature-a", "Ship a tested feature.")

    assert result.status == "done"
    assert result.rework_attempts == 1
    assert len(manager.calls) == 5
    assert "rework node" in str(manager.calls[3]["prompt"])
    assert "missing tests" in str(manager.calls[3]["context"])


@pytest.mark.asyncio
async def test_run_fails_after_max_rework_attempts(tmp_path: Path) -> None:
    manager = FakeSessionManager(
        [
            AgentOutput(status="success", artifacts={"stdout": "# Plan\n"}),
            AgentOutput(status="success", artifacts={"stdout": "implemented"}),
            AgentOutput(status="success", artifacts={"stdout": '{"verdict": "FAIL"}'}),
            AgentOutput(status="success", artifacts={"stdout": "reworked"}),
            AgentOutput(status="success", artifacts={"stdout": '{"verdict": "FAIL"}'}),
        ]
    )
    skill = _skill(tmp_path, manager, max_rework_attempts=1)

    result = await skill.run("feature-a", "Ship a tested feature.")

    assert result.status == "failed"
    assert result.rework_attempts == 1
    assert result.review.passed is False


@pytest.mark.asyncio
async def test_skip_plan_uses_goal_as_plan_without_planner_dispatch(tmp_path: Path) -> None:
    manager = FakeSessionManager(
        [
            AgentOutput(status="success", artifacts={"stdout": "implemented"}),
            AgentOutput(status="success", artifacts={"stdout": '{"verdict": "PASS"}'}),
        ]
    )
    skill = _skill(tmp_path, manager, skip_plan=True)

    result = await skill.run("feature-a", "Small targeted cleanup.")

    assert result.status == "done"
    assert result.plan_path.read_text() == "# Goal\n\nSmall targeted cleanup.\n"
    assert len(manager.calls) == 2
    assert "execute node" in str(manager.calls[0]["prompt"])
    assert "Small targeted cleanup." in str(manager.calls[0]["context"])
