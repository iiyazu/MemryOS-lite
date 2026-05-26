from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xmuse_core.agents.protocol import AgentOutput
from xmuse_core.agents.registry import AgentDescriptor, AgentRegistry


WorktreeResolver = Callable[[str], Path]


@dataclass(frozen=True)
class ReviewVerdict:
    """Parsed review result returned by the review agent."""

    passed: bool
    verdict: str
    feedback: str
    output: AgentOutput


@dataclass(frozen=True)
class PlanExecuteReviewResult:
    """Summary of a full plan -> execute -> review -> optional rework cycle."""

    status: str
    plan_path: Path
    execute_output: AgentOutput
    review: ReviewVerdict
    rework_attempts: int
    rework_outputs: tuple[AgentOutput, ...]


class PlanExecuteReviewSkill:
    """Reusable one-shot-agent orchestration for feature implementation work."""

    def __init__(
        self,
        registry: AgentRegistry,
        session_manager: Any,
        *,
        feature_root: Path | str = Path("xmuse/work/features"),
        worktree_resolver: WorktreeResolver | None = None,
        prompt_dir: Path | str = Path("xmuse/prompts"),
        max_rework_attempts: int = 1,
        skip_plan: bool = False,
        planner_capabilities: Sequence[str] = ("code",),
        implementer_capabilities: Sequence[str] = ("code",),
        reviewer_capabilities: Sequence[str] = ("review",),
        rework_capabilities: Sequence[str] = ("code",),
    ) -> None:
        if max_rework_attempts < 0:
            raise ValueError("max_rework_attempts must be >= 0")
        self._registry = registry
        self._session_manager = session_manager
        self._feature_root = Path(feature_root)
        self._worktree_resolver = worktree_resolver or (lambda _feature_id: Path.cwd())
        self._prompt_dir = Path(prompt_dir)
        self.max_rework_attempts = max_rework_attempts
        self.skip_plan = skip_plan
        self._capabilities = {
            "plan": list(planner_capabilities),
            "execute": list(implementer_capabilities),
            "review": list(reviewer_capabilities),
            "rework": list(rework_capabilities),
        }

    async def plan(self, feature_id: str, goal: str) -> Path:
        """Dispatch the planner agent and persist its output as plan.md."""

        if self.skip_plan:
            return self._write_plan(feature_id, f"# Goal\n\n{goal.strip()}\n")

        prompt = self._build_plan_prompt(feature_id, goal)
        output = await self._dispatch(
            step="plan",
            feature_id=feature_id,
            prompt=prompt,
            worktree=self._worktree(feature_id),
        )
        self._raise_on_failure("plan", output)
        return self._write_plan(feature_id, self._artifact_text(output, preferred=("plan.md", "plan")))

    async def execute(self, feature_id: str, plan: Path | str) -> AgentOutput:
        """Dispatch the implementer agent with the accepted plan as context."""

        plan_text = self._plan_text(plan)
        output = await self._dispatch(
            step="execute",
            feature_id=feature_id,
            prompt=self._build_execute_prompt(feature_id),
            worktree=self._worktree(feature_id),
            context=plan_text,
        )
        self._raise_on_failure("execute", output)
        return output

    async def review(self, feature_id: str, worktree: Path) -> ReviewVerdict:
        """Dispatch the reviewer agent and parse a PASS/FAIL verdict."""

        output = await self._dispatch(
            step="review",
            feature_id=feature_id,
            prompt=self._build_review_prompt(feature_id, worktree),
            worktree=worktree,
        )
        self._raise_on_failure("review", output)
        return self._parse_verdict(output)

    async def rework(self, feature_id: str, verdict: ReviewVerdict) -> AgentOutput:
        """Dispatch the rework agent with the review feedback as context."""

        output = await self._dispatch(
            step="rework",
            feature_id=feature_id,
            prompt=self._build_rework_prompt(feature_id),
            worktree=self._worktree(feature_id),
            context=verdict.feedback,
        )
        self._raise_on_failure("rework", output)
        return output

    async def run(self, feature_id: str, goal: str) -> PlanExecuteReviewResult:
        """Run the full plan, execute, review, and bounded rework cycle."""

        plan_path = await self.plan(feature_id, goal)
        execute_output = await self.execute(feature_id, plan_path)
        worktree = self._worktree(feature_id)
        review = await self.review(feature_id, worktree)

        rework_outputs: list[AgentOutput] = []
        while not review.passed and len(rework_outputs) < self.max_rework_attempts:
            rework_outputs.append(await self.rework(feature_id, review))
            review = await self.review(feature_id, worktree)

        return PlanExecuteReviewResult(
            status="done" if review.passed else "failed",
            plan_path=plan_path,
            execute_output=execute_output,
            review=review,
            rework_attempts=len(rework_outputs),
            rework_outputs=tuple(rework_outputs),
        )

    async def _dispatch(
        self,
        *,
        step: str,
        feature_id: str,
        prompt: str,
        worktree: Path,
        context: str = "",
    ) -> AgentOutput:
        agent = self._select_agent(step)
        return await self._session_manager.dispatch_one_shot(
            agent=agent,
            feature_id=feature_id,
            prompt=prompt,
            worktree=worktree,
            context=context,
        )

    def _select_agent(self, step: str) -> AgentDescriptor:
        return self._registry.select(self._capabilities[step])

    def _worktree(self, feature_id: str) -> Path:
        return Path(self._worktree_resolver(feature_id))

    def _feature_dir(self, feature_id: str) -> Path:
        return self._feature_root / feature_id

    def _write_plan(self, feature_id: str, text: str) -> Path:
        plan_path = self._feature_dir(feature_id) / "plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(text)
        return plan_path

    def _build_plan_prompt(self, feature_id: str, goal: str) -> str:
        base = self._prompt_template("plan_agent.md")
        return (
            f"{base}\n\n"
            "## Skill Step\n"
            f"You are the planning node for feature `{feature_id}`.\n"
            "Generate the reusable implementation plan and write/return it as `plan.md`.\n\n"
            "## Goal\n"
            f"{goal.strip()}\n"
        )

    def _build_execute_prompt(self, feature_id: str) -> str:
        base = self._prompt_template("execute_agent.md")
        return (
            f"{base}\n\n"
            "## Skill Step\n"
            f"You are the execute node for feature `{feature_id}`.\n"
            "Use the provided plan context as the accepted plan. Implement it with focused "
            "tests and record verification evidence.\n"
        )

    def _build_review_prompt(self, feature_id: str, worktree: Path) -> str:
        base = self._prompt_template("review_agent.md")
        return (
            f"{base}\n\n"
            "## Skill Step\n"
            f"You are the review node for feature `{feature_id}`.\n"
            f"Review the worktree `{worktree}` and return a verdict as JSON with "
            "`verdict` equal to `PASS` or `FAIL`, plus blocking findings when relevant.\n"
        )

    def _build_rework_prompt(self, feature_id: str) -> str:
        return (
            "# Hermes Feature-Local Rework Agent Prompt\n\n"
            "You are the feature-local rework node. Address only the blocking review "
            "findings supplied in context, keep the implementation feature-scoped, and "
            "rerun focused verification.\n\n"
            "## Skill Step\n"
            f"You are the rework node for feature `{feature_id}`.\n"
            "Use the review feedback context as the repair contract. Do not broaden scope.\n"
        )

    def _prompt_template(self, name: str) -> str:
        path = self._prompt_dir / name
        if path.exists():
            return path.read_text().strip()
        return ""

    @staticmethod
    def _plan_text(plan: Path | str) -> str:
        if isinstance(plan, Path):
            return plan.read_text()
        return plan

    @staticmethod
    def _artifact_text(output: AgentOutput, preferred: Sequence[str]) -> str:
        for key in preferred:
            value = output.artifacts.get(key)
            if isinstance(value, str) and value.strip():
                return value
        stdout = output.artifacts.get("stdout")
        if isinstance(stdout, str) and stdout.strip():
            return stdout
        return json.dumps(output.artifacts, indent=2, sort_keys=True) + "\n"

    @classmethod
    def _parse_verdict(cls, output: AgentOutput) -> ReviewVerdict:
        feedback = cls._artifact_text(output, preferred=("review_verdict.json", "verdict"))
        verdict = cls._extract_verdict(feedback)
        return ReviewVerdict(
            passed=verdict == "PASS",
            verdict=verdict,
            feedback=feedback,
            output=output,
        )

    @staticmethod
    def _extract_verdict(text: str) -> str:
        stripped = text.strip()
        if stripped:
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                value = data.get("verdict")
                if isinstance(value, str):
                    return value.upper()

        match = re.search(r"\bverdict\b\s*[:=]\s*['\"]?(PASS|FAIL)\b", text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        match = re.search(r"\b(PASS|FAIL)\b", text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return "FAIL"

    @staticmethod
    def _raise_on_failure(step: str, output: AgentOutput) -> None:
        if output.status in {"success", "done"}:
            return
        message = output.error_message or output.error_code or output.status
        raise RuntimeError(f"{step} dispatch failed: {message}")
