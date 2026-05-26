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
    commands: dict[str, list[str]] = field(default_factory=dict)


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
    _DEFAULT_BASE_REF = "HEAD~1"
    _SMOKE_TESTS = ("tests/test_config.py",)

    async def check(self, worktree: Path) -> GateResult:
        checks: dict[str, bool] = {}
        errors: list[str] = []
        commands: dict[str, list[str]] = {}

        ruff_cmd = ["uv", "run", "ruff", "check", "src/", "xmuse/"]
        commands["ruff"] = ruff_cmd
        ruff_result = await self._run(worktree, *ruff_cmd)
        checks["ruff"] = ruff_result.returncode == 0
        if not checks["ruff"]:
            errors.append(self._format_command_failure("ruff", ruff_result))

        diff_cmd = ["git", "diff", "--stat", self._DEFAULT_BASE_REF]
        commands["diff_sanity"] = diff_cmd
        diff_result = await self._run(worktree, *diff_cmd)
        diff_ok, diff_error = self._check_diff_sanity(diff_result)
        checks["diff_sanity"] = diff_ok
        if diff_error is not None:
            errors.append(diff_error)

        changed_files_result = await self._run(
            worktree,
            "git",
            "diff",
            "--name-only",
            self._DEFAULT_BASE_REF,
        )
        target_paths = self._targeted_pytest_paths(worktree, changed_files_result)
        pytest_cmd = ["uv", "run", "pytest", *target_paths, "-x", "-q"]
        commands["targeted_pytest"] = pytest_cmd
        pytest_result = await self._run(worktree, *pytest_cmd)
        checks["targeted_pytest"] = pytest_result.returncode == 0
        if not checks["targeted_pytest"]:
            errors.append(self._format_command_failure("targeted_pytest", pytest_result))

        return GateResult(
            passed=all(checks.values()),
            errors=errors,
            checks=checks,
            commands=commands,
        )

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

    def _targeted_pytest_paths(
        self,
        worktree: Path,
        changed_files_result: _CommandResult,
    ) -> list[str]:
        if changed_files_result.returncode != 0:
            return list(self._SMOKE_TESTS)

        changed_files = [
            line.strip()
            for line in changed_files_result.stdout.splitlines()
            if line.strip()
        ]
        targets: list[str] = []
        for changed_file in changed_files:
            if changed_file.startswith("tests/") and changed_file.endswith(".py"):
                targets.append(changed_file)
            elif changed_file.startswith(("xmuse/", "src/xmuse_core/")):
                targets.extend(
                    [
                        "tests/test_xmuse_quality_gate.py",
                        "tests/test_xmuse_master_loop.py",
                        "tests/test_xmuse_auto_discovery.py",
                    ]
                )
            elif changed_file.startswith("src/memoryos_lite/"):
                targets.extend(
                    [
                        "tests/test_config.py",
                        "tests/test_memory_lifecycle.py",
                        "tests/test_core_memory_service.py",
                    ]
                )

        deduped = self._dedupe_existing_paths(worktree, targets)
        if deduped:
            return deduped
        return self._dedupe_existing_paths(worktree, self._SMOKE_TESTS) or list(
            self._SMOKE_TESTS
        )

    def _dedupe_existing_paths(
        self,
        worktree: Path,
        paths: list[str] | tuple[str, ...],
    ) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for path in paths:
            if path in seen:
                continue
            if (worktree / path).exists():
                deduped.append(path)
                seen.add(path)
        return deduped

    def _format_command_failure(self, check_name: str, result: _CommandResult) -> str:
        output = result.output
        message = f"{check_name} failed (exit {result.returncode})"
        return f"{message}\n{output}" if output else message
