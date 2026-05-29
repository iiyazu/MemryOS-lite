from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from xmuse_core.skills.base import SkillContext, SkillProtocol, SkillResult
from xmuse_core.skills.models import ReviewInput

logger = logging.getLogger(__name__)

_REVIEW_PROMPT_MAP = {
    "spec_review": "spec_review_agent.md",
    "lane_review": "lane_review_agent.md",
    "code_review": "review_agent.md",
}


class ReviewGateSkill(SkillProtocol):
    """Generic review gate — dispatches a review agent and returns pass/fail."""

    async def run(self, input: BaseModel) -> SkillResult:
        assert isinstance(input, ReviewInput)
        feature_dir = self._feature_dir(input.feature_id)
        prompt = self._build_prompt(input)

        worktree = self._resolve_worktree(input.feature_id)
        output = await self._ctx.session_manager.dispatch_one_shot(
            agent=self._ctx.registry.select(["review"]),
            feature_id=input.feature_id,
            prompt=prompt,
            worktree=worktree,
        )

        if output.status not in ("success", "done"):
            return SkillResult(
                status="failed",
                errors=[output.error_message or "review dispatch failed"],
            )

        feedback = self._extract_text(output)
        verdict = self._extract_verdict(feedback)
        passed = verdict == "PASS"

        result_path = feature_dir / f"{input.review_type}.json"
        result_path.write_text(json.dumps({
            "feature_id": input.feature_id,
            "review_type": input.review_type,
            "verdict": verdict,
            "passed": passed,
            "feedback": feedback,
        }, indent=2))

        return SkillResult(
            status="success" if passed else "needs_review",
            artifacts={input.review_type: str(result_path)},
            metadata={"passed": passed, "verdict": verdict},
        )

    def _build_prompt(self, input: ReviewInput) -> str:
        template_name = _REVIEW_PROMPT_MAP.get(input.review_type, "review_agent.md")
        base = self._load_prompt(template_name)
        artifact_content = self._read_artifact(input.artifact_path)
        criteria_block = ""
        if input.criteria:
            criteria_block = "\n## Review Criteria\n" + "\n".join(f"- {c}" for c in input.criteria)
        return (
            f"{base}\n\n"
            f"## Feature: {input.feature_id}\n"
            f"## Review Type: {input.review_type}\n"
            f"{criteria_block}\n\n"
            f"## Artifact Content\n\n```\n{artifact_content}\n```\n\n"
            "Return a JSON verdict: {\"verdict\": \"PASS\" or \"FAIL\", \"findings\": [...], \"blocking_findings\": [...]}\n"
        )

    def _load_prompt(self, name: str) -> str:
        path = self._ctx.prompt_dir / name
        return path.read_text().strip() if path.exists() else ""

    def _read_artifact(self, path_str: str) -> str:
        path = Path(path_str)
        if path.exists():
            content = path.read_text()
            return content[:8000] if len(content) > 8000 else content
        return f"[artifact not found: {path_str}]"

    def _resolve_worktree(self, feature_id: str) -> Path:
        if self._ctx.worktree_resolver:
            return Path(self._ctx.worktree_resolver(feature_id))
        return Path.cwd()

    @staticmethod
    def _extract_text(output: Any) -> str:
        for key in ("review_verdict.json", "verdict", "stdout"):
            value = output.artifacts.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(output.artifacts, indent=2)

    @staticmethod
    def _extract_verdict(text: str) -> str:
        stripped = text.strip()
        if stripped:
            try:
                data = json.loads(stripped)
                if isinstance(data, dict):
                    v = data.get("verdict")
                    if isinstance(v, str):
                        return v.upper()
            except json.JSONDecodeError:
                pass
            # Try fenced JSON block
            m = re.search(r"```json\s*\n(.*?)\n\s*```", stripped, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, dict):
                        v = data.get("verdict")
                        if isinstance(v, str):
                            return v.upper()
                except json.JSONDecodeError:
                    pass
        m = re.search(r"\b(PASS|FAIL)\b", text, re.IGNORECASE)
        return m.group(1).upper() if m else "FAIL"
