from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GodConfig:
    name: str
    runtime: str
    timeout_s: int
    skill_prompt_path: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GodConfig:
        return cls(
            name=data["name"],
            runtime=data["runtime"],
            timeout_s=data["timeout_s"],
            skill_prompt_path=data.get("skill_prompt_path", ""),
        )


@dataclass
class SpawnResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class AgentSpawner:
    def __init__(self, *, repo_root: Path, mcp_port: int) -> None:
        self._repo_root = repo_root
        self._mcp_port = mcp_port

    def _build_command(self, god_config: GodConfig, worktree: Path) -> list[str]:
        if god_config.runtime == "codex":
            return [
                "codex", "exec",
                "-m", "o4-mini",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C", str(worktree),
            ]
        return [
            "claude", "--dangerously-skip-permissions",
            "-p", "",
            "--cwd", str(worktree),
        ]

    def _build_env(self, god_config: GodConfig, lane_id: str) -> dict[str, str]:
        env = dict(os.environ)
        env["XMUSE_GOD_NAME"] = god_config.name
        env["XMUSE_LANE_ID"] = lane_id
        env["XMUSE_MCP_URL"] = f"http://localhost:{self._mcp_port}"
        return env

    async def spawn(
        self,
        *,
        god_config: GodConfig,
        lane_id: str,
        prompt: str,
        worktree: Path,
    ) -> SpawnResult:
        cmd = self._build_command(god_config, worktree)
        env = self._build_env(god_config, lane_id)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=worktree,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=prompt.encode()),
                timeout=god_config.timeout_s,
            )
            return SpawnResult(
                exit_code=process.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return SpawnResult(
                exit_code=-1, stdout="", stderr="timeout", timed_out=True
            )
