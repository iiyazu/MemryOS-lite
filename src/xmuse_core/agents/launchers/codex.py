from __future__ import annotations

import os
from pathlib import Path

from xmuse_core.agents.protocol import AgentOutput, StdoutMessage


class CodexLauncher:
    def build_command(self, feature_id: str, worktree: Path) -> list[str]:
        return [
            "codex", "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "-C", str(worktree),
        ]

    def format_prompt(self, task: str, context: str) -> str:
        if context:
            return f"{context}\n\n---\n\n{task}"
        return task

    def build_env(self, feature_id: str) -> dict[str, str]:
        env = dict(os.environ)
        env["XMUSE_FEATURE_ID"] = feature_id
        return env

    def parse_output(self, msg: StdoutMessage) -> AgentOutput | None:
        if msg.type == "result":
            return AgentOutput.from_result(msg)
        if msg.type == "error":
            return AgentOutput.from_error(msg)
        return None
