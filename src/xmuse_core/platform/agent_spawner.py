from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memoryos_lite.observability import current_observability_context


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
            model = os.environ.get("XMUSE_CODEX_MODEL", "gpt-5.5")
            return [
                "codex",
                "exec",
                "-m",
                model,
                "--dangerously-bypass-approvals-and-sandbox",
                "-c",
                'mcp_servers.xmuse-platform.type="sse"',
                "-c",
                f'mcp_servers.xmuse-platform.url="http://localhost:{self._mcp_port}/sse"',
                "-C",
                str(worktree),
            ]
        model = os.environ.get("XMUSE_CLAUDE_MODEL", "sonnet")
        cmd = [
            "claude",
            "-p",
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--model",
            model,
            "--mcp-config",
            self._write_mcp_config(),
        ]
        if os.environ.get("XMUSE_CLAUDE_BARE", "1") != "0":
            cmd.insert(2, "--bare")
        # Block lane-runaway shell loops at the tool layer.
        # Claude bypasses pattern-based denials by reordering flags
        # (pytest -q tests/) or using alternate invocations
        # (python -m pytest tests/). The robust fix is to disallow Bash
        # entirely for the lane execute-god — Claude can still Edit/Read/
        # Write/Glob/Grep to author code, and the platform's own gate
        # runner is responsible for verification.
        # Operators can override for debugging by setting
        # XMUSE_CLAUDE_DISALLOW_BASH=0.
        if os.environ.get("XMUSE_CLAUDE_DISALLOW_BASH", "1") != "0":
            cmd.extend(["--disallowedTools", "Bash"])
        return cmd

    def _write_mcp_config(self) -> str:
        config = {
            "mcpServers": {
                "xmuse-platform": {
                    "type": "sse",
                    "url": f"http://localhost:{self._mcp_port}/sse",
                }
            }
        }
        path = Path(tempfile.gettempdir()) / "xmuse-mcp-config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return str(path)

    def _build_env(self, god_config: GodConfig, lane_id: str) -> dict[str, str]:
        env = dict(os.environ)
        env["XMUSE_GOD_NAME"] = god_config.name
        env["XMUSE_LANE_ID"] = lane_id
        env["XMUSE_MCP_URL"] = f"http://localhost:{self._mcp_port}"
        context = current_observability_context()
        if trace_id := context.get("trace_id"):
            env["XMUSE_TRACE_ID"] = trace_id
        if request_id := context.get("request_id"):
            env["XMUSE_REQUEST_ID"] = request_id
        if session_id := context.get("session_id"):
            env["MEMORYOS_SESSION_ID"] = session_id
        if graph_id := context.get("graph_id"):
            env["XMUSE_GRAPH_ID"] = graph_id
        return env

    def _spawn_log_dir(self, lane_id: str) -> Path:
        safe_lane_id = "".join(
            char if char.isalnum() or char in {"-", "_", "."} else "-"
            for char in lane_id
        )
        return self._repo_root / "logs" / "agent_spawns" / safe_lane_id

    def _write_spawn_log(
        self,
        *,
        lane_id: str,
        god_config: GodConfig,
        command: list[str],
        prompt: str,
        result: SpawnResult,
    ) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        log_dir = self._spawn_log_dir(lane_id)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{timestamp}.prompt.md").write_text(prompt, encoding="utf-8")
        (log_dir / f"{timestamp}.stdout.log").write_text(result.stdout, encoding="utf-8")
        (log_dir / f"{timestamp}.stderr.log").write_text(result.stderr, encoding="utf-8")
        (log_dir / f"{timestamp}.result.json").write_text(
            json.dumps(
                {
                    "lane_id": lane_id,
                    "god": god_config.name,
                    "runtime": god_config.runtime,
                    "command": command,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

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
            result = SpawnResult(
                exit_code=process.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
            )
            self._write_spawn_log(
                lane_id=lane_id,
                god_config=god_config,
                command=cmd,
                prompt=prompt,
                result=result,
            )
            return result
        except TimeoutError:
            process.kill()
            await process.wait()
            result = SpawnResult(
                exit_code=-1, stdout="", stderr="timeout", timed_out=True
            )
            self._write_spawn_log(
                lane_id=lane_id,
                god_config=god_config,
                command=cmd,
                prompt=prompt,
                result=result,
            )
            return result
