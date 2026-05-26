from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)


@dataclass
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return "\n".join(
            part.rstrip() for part in (self.stdout, self.stderr) if part.strip()
        )


class QualityGate:
    _INSERTION_LIMIT = 1000
    _INSERTIONS_RE = re.compile(r"(\d+)\s+insertions?\(\+\)")

    async def check(self, worktree: Path) -> GateResult:
        checks: dict[str, bool] = {}
        errors: list[str] = []

        pytest_result = await self._run(worktree, "uv", "run", "pytest", "tests/", "-x", "-q")
        checks["pytest"] = pytest_result.returncode == 0
        if not checks["pytest"]:
            errors.append(self._format_command_failure("pytest", pytest_result))

        ruff_result = await self._run(worktree, "uv", "run", "ruff", "check", "src/", "xmuse/")
        checks["ruff"] = ruff_result.returncode == 0
        if not checks["ruff"]:
            errors.append(self._format_command_failure("ruff", ruff_result))

        diff_result = await self._run(worktree, "git", "diff", "--stat", "HEAD~1")
        diff_ok, diff_error = self._check_diff_sanity(diff_result)
        checks["diff_sanity"] = diff_ok
        if diff_error is not None:
            errors.append(diff_error)

        return GateResult(passed=all(checks.values()), errors=errors, checks=checks)

    async def _run(self, worktree: Path, *cmd: str) -> _CommandResult:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=worktree,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        returncode = process.returncode
        if returncode is None:
            returncode = await process.wait()
        return _CommandResult(
            returncode=returncode,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

    def _check_diff_sanity(self, result: _CommandResult) -> tuple[bool, str | None]:
        if result.returncode != 0:
            return False, self._format_command_failure("diff_sanity", result)

        insertions = self._count_insertions(result.stdout)
        if insertions > self._INSERTION_LIMIT:
            output = result.output
            message = (
                f"diff_sanity failed: {insertions} insertions exceeds limit of "
                f"{self._INSERTION_LIMIT}"
            )
            return False, f"{message}\n{output}" if output else message

        return True, None

    def _count_insertions(self, stat_output: str) -> int:
        match = self._INSERTIONS_RE.search(stat_output)
        if match is None:
            return 0
        return int(match.group(1))

    def _format_command_failure(self, check_name: str, result: _CommandResult) -> str:
        output = result.output
        message = f"{check_name} failed (exit {result.returncode})"
        return f"{message}\n{output}" if output else message
