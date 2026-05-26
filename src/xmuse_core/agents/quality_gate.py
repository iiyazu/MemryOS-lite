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
    gate_report: dict[str, object] | None = None
    gate_warnings: list[str] = field(default_factory=list)


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

    def __init__(
        self,
        *,
        profile_config_path: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.profile_config_path = profile_config_path
        self.repo_root = repo_root or Path.cwd()
        self._profile_config = None
        self._runner = None

    async def check(
        self,
        worktree: Path,
        *,
        feature_id: str = "lane-local",
        gate_profile: str | None = None,
        gate_profiles: list[str] | None = None,
        changed_paths: list[str] | None = None,
        base_head_sha: str | None = None,
    ) -> GateResult:
        if self.profile_config_path is not None:
            return await self._check_with_profiles(
                worktree,
                feature_id=feature_id,
                gate_profile=gate_profile,
                gate_profiles=gate_profiles or [],
                changed_paths=changed_paths,
                base_head_sha=base_head_sha,
            )
        return await self._check_legacy(worktree)

    async def _check_legacy(self, worktree: Path) -> GateResult:
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

    async def _check_with_profiles(
        self,
        worktree: Path,
        *,
        feature_id: str,
        gate_profile: str | None,
        gate_profiles: list[str],
        changed_paths: list[str] | None,
        base_head_sha: str | None,
    ) -> GateResult:
        from xmuse_core.gates.loader import load_gate_config
        from xmuse_core.gates.resolver import GateProfileResolver, ProfileMismatchError
        from xmuse_core.gates.runner import GateRunner

        config = self._profile_config
        if config is None:
            config = load_gate_config(self.profile_config_path, repo_root=self.repo_root)
            self._profile_config = config
        runner = self._runner
        if runner is None:
            runner = GateRunner(repo_root=self.repo_root)
            self._runner = runner

        explicit = list(gate_profiles)
        if not explicit and gate_profile:
            explicit = [gate_profile]
        warnings: list[str] = []
        if changed_paths is None:
            changed, warnings = await self._changed_paths(
                worktree,
                base_head_sha=base_head_sha,
            )
        else:
            changed = changed_paths
        diff_failures = [
            warning for warning in warnings if warning.startswith("diff_collection_failed")
        ]
        if diff_failures:
            return GateResult(
                passed=False,
                errors=diff_failures,
                checks={"gate_profiles": False},
                commands={},
                gate_warnings=warnings,
            )
        try:
            plan = GateProfileResolver(config).resolve(
                feature_id=feature_id,
                worktree=worktree,
                explicit_profiles=explicit,
                changed_paths=changed,
                warnings=warnings,
            )
        except ProfileMismatchError as exc:
            return GateResult(
                passed=False,
                errors=[f"profile_mismatch failed: {exc}"],
                checks={"gate_profiles": False},
                commands={},
            )
        report = await runner.run(plan)
        return GateResult(
            passed=report.passed,
            errors=report.errors,
            checks={"gate_profiles": report.passed},
            commands={"gate_profiles": ["profiles", *report.profile_ids]},
            gate_report={
                "feature_id": report.feature_id,
                "passed": report.passed,
                "blocking_passed": report.blocking_passed,
                "nonblocking_failures": report.nonblocking_failures,
                "profile_ids": report.profile_ids,
                "artifact_dir": str(report.artifact_dir),
            },
            gate_warnings=report.warnings,
        )

    async def _changed_paths(
        self,
        worktree: Path,
        *,
        base_head_sha: str | None,
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        base_ref = f"{base_head_sha}...HEAD" if base_head_sha else self._DEFAULT_BASE_REF
        if base_head_sha is None:
            merge_base = await self._run(worktree, "git", "merge-base", "HEAD", "main")
            if merge_base.returncode == 0 and merge_base.stdout.strip():
                base_ref = f"{merge_base.stdout.strip()}...HEAD"
                warnings.append("legacy_diff_base_inferred")
        result = await self._run(worktree, "git", "diff", "--name-only", base_ref)
        if result.returncode != 0:
            message = "diff_collection_failed"
            if result.output:
                message = f"{message}: {result.output}"
            warnings.append(message)
            return [], warnings
        return [line.strip() for line in result.stdout.splitlines() if line.strip()], warnings

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
