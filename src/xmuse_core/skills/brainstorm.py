from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from xmuse_core.skills.base import SkillProtocol, SkillResult
from xmuse_core.skills.models import BrainstormInput, DesignSpec

logger = logging.getLogger(__name__)


class BrainstormSkill(SkillProtocol):
    """Explore a goal, propose approaches, produce a design spec."""

    async def run(self, input: BaseModel) -> SkillResult:
        assert isinstance(input, BrainstormInput)
        feature_dir = self._feature_dir(input.feature_id)

        bridge = self._try_superpowers()
        if bridge:
            return await bridge.delegate_brainstorm(input, feature_dir)

        context = self._gather_context(input.context_files)
        prompt = self._build_prompt(input, context)
        worktree = self._resolve_worktree(input.feature_id)

        output = await self._ctx.session_manager.dispatch_one_shot(
            agent=self._ctx.registry.select(["code"]),
            feature_id=input.feature_id,
            prompt=prompt,
            worktree=worktree,
        )

        if output.status not in ("success", "done"):
            return SkillResult(
                status="failed",
                errors=[output.error_message or "brainstorm dispatch failed"],
            )

        raw_text = self._extract_text(output)
        spec = self._parse_spec(input.feature_id, raw_text)

        spec_path = feature_dir / "spec.json"
        spec_path.write_text(spec.model_dump_json(indent=2))
        brainstorm_path = feature_dir / "brainstorm.md"
        brainstorm_path.write_text(raw_text)

        return SkillResult(
            status="success",
            artifacts={"spec": str(spec_path), "brainstorm": str(brainstorm_path)},
            metadata={"approaches_count": len(spec.approaches)},
        )

    def _build_prompt(self, input: BrainstormInput, context: str) -> str:
        base = self._load_prompt("brainstorm_agent.md")
        constraints_block = ""
        if input.constraints:
            constraints_block = "\n## Constraints\n" + "\n".join(f"- {c}" for c in input.constraints)
        return (
            f"{base}\n\n"
            f"## Feature: {input.feature_id}\n"
            f"## Goal\n{input.goal}\n"
            f"{constraints_block}\n\n"
            f"## Project Context\n{context}\n\n"
            "## Output Format\n"
            "Return a JSON design spec in a fenced block:\n"
            "```json\n"
            '{"title": "...", "summary": "...", "approaches": [...], '
            '"chosen_approach": "...", "architecture_decisions": [...], '
            '"non_goals": [...], "acceptance_criteria": [...]}\n'
            "```\n"
        )

    def _gather_context(self, paths: list[str]) -> str:
        parts: list[str] = []
        for p in paths[:10]:
            path = Path(p)
            if path.exists():
                content = path.read_text()
                parts.append(f"### {p}\n{content[:4000]}")
        return "\n\n".join(parts) if parts else "(no context files provided)"

    def _load_prompt(self, name: str) -> str:
        path = self._ctx.prompt_dir / name
        return path.read_text().strip() if path.exists() else ""

    def _resolve_worktree(self, feature_id: str) -> Path:
        if self._ctx.worktree_resolver:
            return Path(self._ctx.worktree_resolver(feature_id))
        return Path.cwd()

    def _try_superpowers(self) -> Any:
        try:
            from xmuse_core.skills.superpowers_bridge import SuperpowersBridge
            bridge = SuperpowersBridge()
            return bridge if bridge.available else None
        except ImportError:
            return None

    @staticmethod
    def _extract_text(output: Any) -> str:
        for key in ("spec.json", "spec", "stdout"):
            value = output.artifacts.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(output.artifacts, indent=2)

    def _parse_spec(self, feature_id: str, text: str) -> DesignSpec:
        data = _extract_fenced_json(text)
        if data and isinstance(data, dict):
            data.setdefault("feature_id", feature_id)
            try:
                return DesignSpec.model_validate(data)
            except Exception:
                pass
        return DesignSpec(
            feature_id=feature_id,
            title=feature_id.replace("-", " ").title(),
            summary=text[:500],
        )


def _extract_fenced_json(text: str) -> dict | None:
    m = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None
