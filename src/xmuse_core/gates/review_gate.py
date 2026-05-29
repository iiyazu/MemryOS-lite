"""Codex-based diff review gate - semantic code review before auto-merge."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_MAX_DIFF_CHARS = 6000
_MAX_PROMPT_CHARS = 2000


@dataclass
class ReviewVerdict:
    approved: bool
    concerns: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 1.0
    self_modification: bool = False


@dataclass
class DiffResult:
    text: str
    error: str = ""


class CodexReviewGate:
    """Single-shot Codex process review of a lane's diff before merge."""

    def __init__(
        self,
        *,
        codex_cmd: str = "codex",
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._codex_cmd = codex_cmd
        self._model = model
        self._timeout_s = timeout_s

    async def review(
        self,
        feature_id: str,
        worktree: Path,
        original_prompt: str,
        base_ref: str | None = None,
        gate_context: str | None = None,
    ) -> ReviewVerdict:
        """Review a lane's diff. Returns verdict with concerns."""
        diff_result = self._get_diff(worktree, base_ref)
        if diff_result.error:
            return ReviewVerdict(
                approved=False,
                concerns=[diff_result.error],
                summary="review gate could not collect lane diff",
                confidence=0.0,
            )
        if not diff_result.text.strip():
            return ReviewVerdict(approved=True, summary="no changes")

        self_mod = self._detect_self_modification(diff_result.text)
        prompt = self._build_prompt(
            feature_id,
            original_prompt,
            diff_result.text,
            self_mod,
            gate_context=gate_context,
        )
        result = await asyncio.to_thread(
            subprocess.run,
            self._build_command(worktree),
            input=prompt,
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=self._timeout_s,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()[:500]
            raise RuntimeError(f"codex_review_failed: {stderr}")

        verdict = self._parse_verdict(result.stdout)
        verdict.self_modification = self_mod
        return verdict

    def _build_command(self, worktree: Path) -> list[str]:
        command = [*shlex.split(self._codex_cmd), "exec"]
        if self._model:
            command.extend(["-m", self._model])
        command.extend(
            [
                "--dangerously-bypass-approvals-and-sandbox",
                "-C",
                str(worktree),
            ]
        )
        return command

    def _get_diff(self, worktree: Path, base_ref: str | None) -> DiffResult:
        ref = base_ref or "HEAD~1"
        result = subprocess.run(
            ["git", "diff", "--stat", ref],
            capture_output=True, text=True, cwd=worktree,
        )
        if result.returncode != 0:
            return DiffResult(
                text="",
                error=f"diff_stat_failed: {result.stderr.strip()[:500]}",
            )
        stat = result.stdout[:500]
        result2 = subprocess.run(
            ["git", "diff", ref],
            capture_output=True, text=True, cwd=worktree,
        )
        if result2.returncode != 0:
            return DiffResult(
                text="",
                error=f"diff_failed: {result2.stderr.strip()[:500]}",
            )
        full = result2.stdout[:_MAX_DIFF_CHARS]
        return DiffResult(text=f"{stat}\n\n{full}")

    def _detect_self_modification(self, diff: str) -> bool:
        return "xmuse/" in diff or "src/xmuse_core/" in diff

    def _build_prompt(
        self,
        feature_id: str,
        original_prompt: str,
        diff: str,
        self_mod: bool,
        *,
        gate_context: str | None = None,
    ) -> str:
        extra = ""
        if self_mod:
            extra = """
6. 【自修改审查】此 diff 修改了 xmuse 控制面代码。额外检查：
   - 是否移除了安全机制（超时、认证、校验）？
   - 是否扩大了自动执行权限？
   - 是否引入了无限循环或资源泄漏？"""
        gate_section = gate_context or "No quality gate context was provided."

        return f"""你是代码审查 agent。审查以下 diff 是否正确实现了需求。

## Lane: {feature_id}

## 原始需求
{original_prompt[:_MAX_PROMPT_CHARS]}

## Quality Gate Context
{gate_section}

## Diff
{diff}

## 审查标准
1. 改动是否真正解决了需求描述的问题？
2. 是否引入了安全风险（注入、硬编码密钥、不安全的 eval）？
3. 是否有明显的逻辑错误或边界条件遗漏？
4. 是否有不必要的大范围改动（scope creep）？
5. 代码是否可以正常工作（语法正确、import 存在）？{extra}

返回 JSON（无 markdown fencing）:
{{"approved": true/false, "concerns": ["具体问题1"], "summary": "一句话总结"}}

如果没有问题: {{"approved": true, "concerns": [], "summary": "改动合理", "confidence": 0.9}}"""

    def _parse_verdict(self, raw: str) -> ReviewVerdict:
        match = _FENCED_JSON_RE.search(raw)
        text = match.group(1) if match else raw.strip()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("review_gate: failed to parse LLM response")
            return self._invalid_verdict("review_parse_failed")
        if not isinstance(data, Mapping):
            return self._invalid_verdict("review_schema_invalid")

        approved = data.get("approved")
        if not isinstance(approved, bool):
            return self._invalid_verdict("review_schema_invalid")
        concerns = data.get("concerns", [])
        if not isinstance(concerns, list) or not all(
            isinstance(item, str) for item in concerns
        ):
            return self._invalid_verdict("review_schema_invalid")
        confidence = data.get("confidence", 0.5)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            return self._invalid_verdict("review_schema_invalid")
        confidence_value = max(0.0, min(1.0, confidence_value))
        summary = data.get("summary", "")
        if not isinstance(summary, str):
            summary = str(summary)
        return ReviewVerdict(
            approved=approved,
            concerns=concerns,
            summary=summary,
            confidence=confidence_value,
        )

    def _invalid_verdict(self, concern: str) -> ReviewVerdict:
        return ReviewVerdict(
            approved=False,
            concerns=[concern],
            summary="Codex response unparseable",
            confidence=0.0,
        )


LLMReviewGate = CodexReviewGate
