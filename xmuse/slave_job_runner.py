#!/usr/bin/env python3
"""Run queued xmuse Slave jobs from the deterministic dispatch plan."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _loop_path(loop: Path, ref: str) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    prefix = loop.name + "/"
    if ref.startswith(prefix):
        return loop / ref[len(prefix) :]
    return loop / ref


def _pid_alive(pid: object) -> bool:
    try:
        value = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _job_is_running(job_path: Path) -> bool:
    if not job_path.exists():
        return False
    job = _read_json(job_path)
    runtime = job.get("runtime", {})
    if not isinstance(runtime, dict) or runtime.get("status") != "running":
        return False
    return _pid_alive(runtime.get("pid"))


def _runtime_status(job_path: Path) -> str:
    if not job_path.exists():
        return "missing"
    job = _read_json(job_path)
    runtime = job.get("runtime", {})
    if not isinstance(runtime, dict):
        return "not_started"
    status = str(runtime.get("status") or "not_started")
    if status == "running" and not _pid_alive(runtime.get("pid")):
        return "stale_running"
    return status


def _optional_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _artifact_ref(job: dict[str, Any], feature_id: str, name: str) -> str:
    artifacts = job.get("artifacts", {})
    if isinstance(artifacts, dict) and isinstance(artifacts.get(name), str):
        return artifacts[name]
    return f"xmuse/work/features/{feature_id}/{name}.json"


def _job_artifacts_blocked(loop: Path, feature_id: str, job: dict[str, Any]) -> bool:
    ack = _optional_json(_loop_path(loop, _artifact_ref(job, feature_id, "ack")))
    review = _optional_json(_loop_path(loop, _artifact_ref(job, feature_id, "review_verdict")))
    if ack and str(ack.get("ack_level", "")).lower() != "usable":
        return True
    if review and str(review.get("verdict", "")).lower() != "pass":
        return True
    return False


def _job_log_paths(loop: Path, feature_id: str) -> tuple[Path, Path]:
    logs = loop / "jobs" / "logs"
    safe_id = feature_id.replace("/", "_")
    return logs / f"{safe_id}.out", logs / f"{safe_id}.err"


def _api_transient_error(text: str) -> bool:
    markers = (
        "429 Too Many Requests",
        "You've hit your usage limit",
        "exceeded retry limit, last status: 429",
    )
    return any(marker in text for marker in markers)


def _job_has_api_transient_error(loop: Path, feature_id: str) -> bool:
    _, stderr_path = _job_log_paths(loop, feature_id)
    try:
        return _api_transient_error(stderr_path.read_text(encoding="utf-8", errors="ignore"))
    except FileNotFoundError:
        return False


def _load_dispatch_jobs(loop: Path) -> list[dict[str, Any]]:
    plan = _read_json(loop / "dispatch" / "multi_lane_dispatch.json")
    jobs = plan.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("dispatch jobs must be a list")
    return [job for job in jobs if isinstance(job, dict)]


def _mark_runtime(job_path: Path, runtime: dict[str, Any]) -> None:
    job = _read_json(job_path)
    job["runtime"] = runtime
    _write_json(job_path, job)


def run_one(loop: Path, job_ref: str) -> int:
    job_path = _loop_path(loop, job_ref)
    job = _read_json(job_path)
    feature_id = str(job.get("feature_id") or job_path.stem)
    command = job.get("command")
    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        _mark_runtime(
            job_path,
            {
                "status": "failed",
                "pid": os.getpid(),
                "failed_at": _now(),
                "exit_code": 2,
                "reason": "job command is missing or invalid",
            },
        )
        return 2

    started = _now()
    _mark_runtime(
        job_path,
        {
            "status": "running",
            "pid": os.getpid(),
            "started_at": started,
            "runner": "xmuse/slave_job_runner.py",
        },
    )
    completed = subprocess.run(command, cwd=PROJECT, check=False)
    status = "completed" if completed.returncode == 0 else "failed"
    reason = None
    if completed.returncode != 0 and _job_has_api_transient_error(loop, feature_id):
        status = "api_transient_blocked"
        reason = "codex api transient limit or usage exhaustion"
    elif completed.returncode == 0 and _job_artifacts_blocked(loop, feature_id, job):
        status = "artifact_blocked"
        reason = "feature-local artifacts are not usable"
    runtime = {
        "status": status,
        "pid": os.getpid(),
        "started_at": started,
        "completed_at": _now(),
        "exit_code": completed.returncode,
        "runner": "xmuse/slave_job_runner.py",
    }
    if reason:
        runtime["reason"] = reason
    _mark_runtime(
        job_path,
        runtime,
    )
    return completed.returncode


def start_queued_jobs(loop: Path, *, dry_run: bool = False) -> dict[str, Any]:
    started: list[str] = []
    skipped: list[dict[str, str]] = []

    for job in _load_dispatch_jobs(loop):
        feature_id = str(job.get("feature_id") or "")
        status = str(job.get("status") or "")
        job_ref = str(job.get("job_ref") or "")
        if status != "queued":
            skipped.append({"feature_id": feature_id, "reason": f"job status is {status}"})
            continue
        if not job_ref:
            skipped.append({"feature_id": feature_id, "reason": "job_ref is missing"})
            continue

        job_path = _loop_path(loop, job_ref)
        if _job_is_running(job_path):
            skipped.append({"feature_id": feature_id, "reason": "job already running"})
            continue
        runtime_status = _runtime_status(job_path)
        if runtime_status == "completed" and _job_artifacts_blocked(loop, feature_id, job):
            runtime_status = "artifact_blocked"
        if runtime_status == "failed" and _job_has_api_transient_error(loop, feature_id):
            runtime_status = "api_transient_blocked"
        if runtime_status in {"completed", "failed"}:
            skipped.append({"feature_id": feature_id, "reason": f"job already {runtime_status}"})
            continue
        if dry_run:
            started.append(feature_id)
            continue

        stdout_path, stderr_path = _job_log_paths(loop, feature_id)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "run-one",
                    "--loop",
                    str(loop),
                    "--job-ref",
                    job_ref,
                ],
                cwd=PROJECT,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        started.append(feature_id)

    return {"started": started, "skipped": skipped}


def summarize_jobs(loop: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": 0,
        "queued": 0,
        "runnable": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "api_transient_blocked": 0,
        "artifact_blocked": 0,
        "stale_running": 0,
        "blocked": 0,
        "needs_master_reconcile": False,
    }
    for job in _load_dispatch_jobs(loop):
        status = str(job.get("status") or "")
        job_ref = str(job.get("job_ref") or "")
        summary["total"] += 1
        if status == "blocked":
            summary["blocked"] += 1
            continue
        if status != "queued" or not job_ref:
            continue
        summary["queued"] += 1
        runtime_status = _runtime_status(_loop_path(loop, job_ref))
        if runtime_status == "completed" and _job_artifacts_blocked(
            loop, str(job.get("feature_id") or ""), job
        ):
            runtime_status = "artifact_blocked"
        if runtime_status == "failed" and _job_has_api_transient_error(
            loop, str(job.get("feature_id") or "")
        ):
            runtime_status = "api_transient_blocked"
        if runtime_status in {
            "missing",
            "not_started",
            "stale_running",
            "api_transient_blocked",
            "artifact_blocked",
        }:
            summary["runnable"] += 1
        if runtime_status in {
            "running",
            "completed",
            "failed",
            "api_transient_blocked",
            "artifact_blocked",
            "stale_running",
        }:
            summary[runtime_status] += 1
    summary["needs_master_reconcile"] = bool(
        (summary["completed"] or summary["failed"])
        and not summary["running"]
        and not summary["runnable"]
        and not summary["stale_running"]
    )
    return summary


def has_queued_jobs(loop: Path) -> bool:
    return any(str(job.get("status") or "") == "queued" for job in _load_dispatch_jobs(loop))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start-queued")
    start_parser.add_argument("--loop", default="xmuse")
    start_parser.add_argument("--dry-run", action="store_true")

    run_parser = subparsers.add_parser("run-one")
    run_parser.add_argument("--loop", default="xmuse")
    run_parser.add_argument("--job-ref", required=True)

    has_parser = subparsers.add_parser("has-queued")
    has_parser.add_argument("--loop", default="xmuse")

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--loop", default="xmuse")

    needs_master_parser = subparsers.add_parser("needs-master")
    needs_master_parser.add_argument("--loop", default="xmuse")

    args = parser.parse_args()
    loop = Path(args.loop)
    if args.command == "start-queued":
        print(json.dumps(start_queued_jobs(loop, dry_run=args.dry_run), indent=2))
        return 0
    if args.command == "run-one":
        return run_one(loop, args.job_ref)
    if args.command == "has-queued":
        return 0 if has_queued_jobs(loop) else 1
    if args.command == "summary":
        print(json.dumps(summarize_jobs(loop), indent=2, sort_keys=True))
        return 0
    if args.command == "needs-master":
        return 0 if summarize_jobs(loop)["needs_master_reconcile"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
