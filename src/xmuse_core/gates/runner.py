from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from xmuse_core.gates.models import CommandPlan, GateCommandResult, GatePlan, GateReport


class GateRunner:
    def __init__(self, *, repo_root: Path, logs_root: Path | None = None) -> None:
        self.repo_root = repo_root
        self.logs_root = logs_root or repo_root / "xmuse" / "logs" / "gates"

    async def run(self, plan: GatePlan) -> GateReport:
        artifact_dir = self.logs_root / plan.feature_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        results: list[GateCommandResult] = []
        for command in plan.commands:
            name = f"{command.profile_id}__{command.command_id}"
            result = await self._run_command(plan.worktree, command)
            stdout_path = artifact_dir / f"{name}.stdout"
            stderr_path = artifact_dir / f"{name}.stderr"
            stdout_path.write_text(result[1], encoding="utf-8")
            stderr_path.write_text(result[2], encoding="utf-8")
            results.append(
                GateCommandResult(
                    command_id=command.command_id,
                    profile_id=command.profile_id,
                    blocking=command.blocking,
                    argv=command.argv,
                    cwd=command.cwd,
                    timeout_s=command.timeout_s,
                    env=command.env,
                    returncode=result[0],
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )
            )

        blocking_passed = all(
            result.returncode == 0 for result in results if result.blocking
        )
        nonblocking_failures = sorted(
            {
                result.profile_id
                for result in results
                if not result.blocking and result.returncode != 0
            }
        )
        report = GateReport(
            feature_id=plan.feature_id,
            passed=blocking_passed if plan.blocking else True,
            blocking_passed=blocking_passed,
            nonblocking_failures=nonblocking_failures,
            profile_ids=plan.profiles,
            resolution_reasons=plan.resolution_reasons,
            command_results=results,
            artifact_dir=artifact_dir,
            warnings=[
                *plan.warnings,
                *[
                    f"nonblocking profile failed: {profile_id}"
                    for profile_id in nonblocking_failures
                ],
            ],
        )
        (artifact_dir / "report.json").write_text(
            json.dumps(_report_to_json(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return report

    async def _run_command(
        self,
        worktree: Path,
        command: CommandPlan,
    ) -> tuple[int, str, str]:
        env = dict(os.environ)
        env.update(command.env)
        cwd = (worktree / command.cwd).resolve()
        process = await asyncio.create_subprocess_exec(
            *command.argv,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            if command.timeout_s > 0:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=command.timeout_s,
                )
            else:
                stdout_bytes, stderr_bytes = await process.communicate()
        except TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            return (
                124,
                stdout_bytes.decode(errors="replace"),
                (
                    stderr_bytes.decode(errors="replace")
                    + f"\ncommand timed out after {command.timeout_s}s"
                ).lstrip(),
            )
        returncode = process.returncode
        if returncode is None:
            returncode = await process.wait()
        return (
            returncode,
            stdout_bytes.decode(errors="replace"),
            stderr_bytes.decode(errors="replace"),
        )


def _report_to_json(report: GateReport) -> dict[str, object]:
    return {
        "feature_id": report.feature_id,
        "passed": report.passed,
        "blocking_passed": report.blocking_passed,
        "nonblocking_failures": report.nonblocking_failures,
        "profile_ids": report.profile_ids,
        "resolution_reasons": report.resolution_reasons,
        "warnings": report.warnings,
        "artifact_dir": str(report.artifact_dir),
        "command_results": [
            {
                "command_id": result.command_id,
                "profile_id": result.profile_id,
                "blocking": result.blocking,
                "argv": result.argv,
                "cwd": result.cwd.as_posix(),
                "timeout_s": result.timeout_s,
                "env": result.env,
                "returncode": result.returncode,
                "stdout_path": str(result.stdout_path),
                "stderr_path": str(result.stderr_path),
            }
            for result in report.command_results
        ],
    }
