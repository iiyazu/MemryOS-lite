#!/usr/bin/env python3
"""Hermes hardening helpers for launcher state, active jobs, and promotion gates.

Writes are limited to explicit controller artifacts such as state, active job,
heartbeat, status, and stale-index files. It does not mutate source code or
benchmark reports.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROMOTION_PASS_VERDICTS = {"pass", "passed", "usable", "usable_ack", "ack", "approved"}
STALE_CANDIDATE_FILES = (
    "ack.json",
    "review_verdict.json",
    "execute_review.md",
    "result.md",
    "reflect_phase-8.md",
    "plan_review.md",
    "plan_final.md",
)
FEATURE_LANES_FILE = "feature_lanes.json"
MASTER_REVIEW_STATES = {"ready_for_master_review"}
MERGE_REQUEST_STATES = {"ready_for_merge", "merge_requested"}
TARGET_BRANCH_STATES = MASTER_REVIEW_STATES | MERGE_REQUEST_STATES
FEATURE_PASS_STATES = {"acked", "ready_for_master_review", "ready_for_merge", "merged"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _counter_dict(values: list[str]) -> dict[str, int]:
    return dict(Counter(value for value in values if value))


def _context_bundle_path(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str):
            return path
    return None


def _resolve_controller_path(loop: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if value.startswith(".hermes-loop/"):
        return loop.parent / value
    return loop / value


def _controller_display_path(loop: Path, path: Path) -> str:
    """Return stable project-relative controller paths for reports."""
    try:
        return path.resolve().relative_to(loop.parent.resolve()).as_posix()
    except ValueError:
        return str(path)


def _git_status_short(path: Path) -> str | None:
    if not path.exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _pid_alive_default(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False
    return True


def write_active_job(
    loop_root: str | Path,
    *,
    pid: int,
    phase_id: str | None,
    prompt_file: str,
    attempt: int,
    output_path: str,
    idle_timeout_seconds: int,
    started_at: str | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    timestamp = started_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "pid": int(pid),
        "phase_id": phase_id,
        "prompt_file": prompt_file,
        "attempt": int(attempt),
        "output_path": output_path,
        "idle_timeout_seconds": int(idle_timeout_seconds),
        "started_at": timestamp,
        "status": "running",
    }
    path = loop / "active_job.json"
    _atomic_write_json(path, payload)
    return {"ok": True, "path": str(path), **payload}


def classify_active_job(
    loop_root: str | Path,
    *,
    now: float | None = None,
    pid_alive: Any | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    job_path = loop / "active_job.json"
    if not job_path.exists():
        return {"ok": True, "state": "missing", "reason": "missing active_job.json"}

    try:
        job = _read_json(job_path)
    except Exception as exc:
        return {"ok": False, "state": "invalid", "reason": f"invalid active_job.json: {exc}"}

    if not isinstance(job, dict):
        return {"ok": False, "state": "invalid", "reason": "active_job root is not an object"}
    if job.get("status") and job.get("status") != "running":
        return {
            "ok": True,
            "state": str(job.get("status")),
            "reason": "job is not running",
            **job,
        }

    pid = int(job.get("pid", 0) or 0)
    alive_checker = _pid_alive_default if pid_alive is None else pid_alive
    alive = alive_checker(pid) if pid else False
    if not alive:
        return {
            "ok": True,
            "state": "exited_or_missing",
            "reason": "pid is not alive",
            **job,
        }

    output_path = loop / str(job.get("output_path", "codex_output.log"))
    current_time = time.time() if now is None else now
    if not output_path.exists():
        return {
            "ok": True,
            "state": "running",
            "reason": "output file missing but pid alive",
            "output_age_seconds": None,
            **job,
        }

    output_age = int(max(0, current_time - output_path.stat().st_mtime))
    timeout = int(job.get("idle_timeout_seconds", 0) or 0)
    if timeout > 0 and output_age > timeout:
        return {
            "ok": False,
            "state": "stalled",
            "reason": "output stale beyond idle timeout",
            "output_age_seconds": output_age,
            **job,
        }
    return {
        "ok": True,
        "state": "running",
        "reason": "pid alive and output fresh",
        "output_age_seconds": output_age,
        **job,
    }


def complete_active_job(
    loop_root: str | Path,
    *,
    exit_code: int,
    status: str,
    completed_at: str | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    job_path = loop / "active_job.json"
    job: dict[str, Any] = {}
    if job_path.exists():
        loaded = _read_json(job_path)
        if isinstance(loaded, dict):
            job = loaded
    timestamp = completed_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job.update(
        {
            "status": status,
            "exit_code": int(exit_code),
            "completed_at": timestamp,
        }
    )
    _atomic_write_json(job_path, job)
    return {"ok": True, "path": str(job_path), **job}


def load_feature_lanes(loop_root: str | Path) -> dict[str, Any]:
    """Load optional master/slave feature-lane registry.

    The registry is deliberately separate from ``state.json``. ``state.json``
    remains the authoritative single-phase Hermes controller state, while
    ``feature_lanes.json`` records parallel feature worktrees/branches that a
    master God may later integrate.
    """
    loop = Path(loop_root)
    registry_path = loop / FEATURE_LANES_FILE
    if not registry_path.exists():
        return {
            "ok": True,
            "state": "missing",
            "path": str(registry_path),
            "master_god": {},
            "features": [],
        }
    try:
        registry = _read_json(registry_path)
    except Exception as exc:
        return {
            "ok": False,
            "state": "invalid",
            "path": str(registry_path),
            "error": f"invalid {FEATURE_LANES_FILE}: {exc}",
            "master_god": {},
            "features": [],
        }
    if not isinstance(registry, dict):
        return {
            "ok": False,
            "state": "invalid",
            "path": str(registry_path),
            "error": f"{FEATURE_LANES_FILE} root is not an object",
            "master_god": {},
            "features": [],
        }
    features = registry.get("features", [])
    if not isinstance(features, list):
        return {
            "ok": False,
            "state": "invalid",
            "path": str(registry_path),
            "error": "features must be a list",
            "master_god": registry.get("master_god", {}),
            "features": [],
        }
    return {
        "ok": True,
        "state": "loaded",
        "path": _controller_display_path(loop, registry_path),
        "master_god": registry.get("master_god", {}),
        "features": features,
    }


def _artifact_gate(loop: Path, artifacts: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    paths: dict[str, str] = {}

    ack_path = _resolve_controller_path(loop, artifacts.get("ack"))
    review_path = _resolve_controller_path(loop, artifacts.get("review_verdict"))
    result_path = _resolve_controller_path(loop, artifacts.get("result"))

    if ack_path is None:
        blockers.append("missing ack artifact path")
    else:
        paths["ack"] = _controller_display_path(loop, ack_path)
        if not ack_path.exists():
            blockers.append("ack artifact does not exist")
        else:
            try:
                ack = _read_json(ack_path)
            except Exception as exc:
                blockers.append(f"invalid ack artifact: {exc}")
            else:
                if not isinstance(ack, dict):
                    blockers.append("ack artifact root is not an object")
                elif str(ack.get("ack_level", "")).lower() != "usable":
                    blockers.append("ack artifact is not usable")

    if review_path is None:
        blockers.append("missing review_verdict artifact path")
    else:
        paths["review_verdict"] = _controller_display_path(loop, review_path)
        if not review_path.exists():
            blockers.append("review_verdict artifact does not exist")
        else:
            try:
                review = _read_json(review_path)
            except Exception as exc:
                blockers.append(f"invalid review_verdict artifact: {exc}")
            else:
                verdict = str(review.get("verdict", "")).lower() if isinstance(review, dict) else ""
                if verdict not in PROMOTION_PASS_VERDICTS:
                    blockers.append("review_verdict artifact is not passing")

    if result_path is None:
        blockers.append("missing result artifact path")
    else:
        paths["result"] = _controller_display_path(loop, result_path)
        if not result_path.exists():
            blockers.append("result artifact does not exist")

    return {"ok": not blockers, "blockers": blockers, "paths": paths}


def _integrated_tests_gate(loop: Path, artifacts: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    paths: dict[str, str] = {}

    tests_path = _resolve_controller_path(loop, artifacts.get("integrated_tests"))
    if tests_path is None:
        return {
            "ok": False,
            "blockers": ["missing integrated_tests artifact path"],
            "paths": paths,
        }
    paths["integrated_tests"] = _controller_display_path(loop, tests_path)
    if not tests_path.exists():
        blockers.append("integrated_tests artifact does not exist")
    else:
        try:
            integrated = _read_json(tests_path)
        except Exception as exc:
            blockers.append(f"invalid integrated_tests artifact: {exc}")
        else:
            if not isinstance(integrated, dict):
                blockers.append("integrated_tests artifact root is not an object")
            elif str(integrated.get("status", "")).lower() not in PROMOTION_PASS_VERDICTS:
                blockers.append("integrated_tests artifact is not passing")
    return {"ok": not blockers, "blockers": blockers, "paths": paths}


def classify_feature_lane(
    loop_root: str | Path,
    feature: dict[str, Any],
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    blockers: list[str] = []
    warnings: list[str] = []
    feature_id = str(feature.get("id") or "").strip()
    if not feature_id:
        blockers.append("feature id is required")
        feature_id = "<missing>"

    state = str(feature.get("state") or "planned").lower()
    if state not in {
        "planned",
        "planning",
        "executing",
        "review",
        "acked",
        "ready_for_master_review",
        "ready_for_merge",
        "merge_requested",
        "merged",
        "blocked",
        "held",
    }:
        blockers.append(f"unsupported feature state: {state}")

    slave_god = feature.get("slave_god", {})
    if not isinstance(slave_god, dict):
        blockers.append("slave_god must be an object")
        slave_god = {}

    merge = feature.get("merge", {})
    if not isinstance(merge, dict):
        merge = {}
        blockers.append("merge must be an object")
    merge_status = str(merge.get("status") or state).lower()
    gate_requested = (
        state in FEATURE_PASS_STATES | {"merge_requested"}
        or merge_status in TARGET_BRANCH_STATES
    )
    if merge_status in MERGE_REQUEST_STATES and state not in MERGE_REQUEST_STATES:
        blockers.append("merge status is ahead of feature state")
    if merge_status in MASTER_REVIEW_STATES and state not in MASTER_REVIEW_STATES:
        blockers.append("master review status is ahead of feature state")

    branch = feature.get("branch")
    worktree = feature.get("worktree")
    if gate_requested and not isinstance(branch, str):
        blockers.append("merge-ready feature requires branch")
    worktree_path = Path(worktree) if isinstance(worktree, str) and worktree else None
    if gate_requested:
        if worktree_path is None:
            blockers.append("merge-ready feature requires worktree")
        elif not worktree_path.exists():
            blockers.append("feature worktree does not exist")

    artifacts = feature.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
        blockers.append("artifacts must be an object")
    if gate_requested:
        artifact_gate = _artifact_gate(loop, artifacts)
    else:
        artifact_gate = {
            "ok": True,
            "blockers": [],
            "paths": {},
        }
    blockers.extend(artifact_gate["blockers"])

    target_branch = str(merge.get("target_branch") or "").strip()
    if merge_status in MERGE_REQUEST_STATES and not target_branch:
        blockers.append("merge target_branch is required")
    if merge_status in MASTER_REVIEW_STATES and not target_branch:
        blockers.append("master review target_branch is required")

    requires_integrated_tests = merge_status in MERGE_REQUEST_STATES or bool(
        merge.get("requires_integrated_tests")
    )
    if merge_status in MERGE_REQUEST_STATES:
        integrated_tests_gate = _integrated_tests_gate(loop, artifacts)
        blockers.extend(integrated_tests_gate["blockers"])
        artifact_gate["paths"].update(integrated_tests_gate["paths"])
    else:
        integrated_tests_gate = {"ok": True, "blockers": [], "paths": {}}

    git_status = None
    if worktree_path is not None and worktree_path.exists():
        git_status = _git_status_short(worktree_path)
        if git_status and merge_status in TARGET_BRANCH_STATES:
            blockers.append("feature worktree has uncommitted changes")
        elif git_status:
            warnings.append("feature worktree has uncommitted changes")

    reviewable = (
        not blockers
        and merge_status in MASTER_REVIEW_STATES
        and artifact_gate.get("ok") is True
    )
    mergeable = (
        not blockers
        and merge_status in MERGE_REQUEST_STATES
        and artifact_gate.get("ok") is True
        and (not requires_integrated_tests or integrated_tests_gate.get("ok") is True)
    )
    return {
        "id": feature_id,
        "name": feature.get("name"),
        "state": state,
        "slave_god": slave_god,
        "branch": branch,
        "worktree": str(worktree_path) if worktree_path is not None else None,
        "merge": merge,
        "merge_status": merge_status,
        "reviewable": reviewable,
        "mergeable": mergeable,
        "blockers": blockers,
        "warnings": warnings,
        "artifact_gate": artifact_gate,
        "integrated_tests_gate": integrated_tests_gate,
        "git_status_short": git_status,
        "project_root": str(project_root) if project_root is not None else str(loop.parent),
    }


def summarize_master_slave_control(
    loop_root: str | Path,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    registry = load_feature_lanes(loop)
    if not registry.get("ok"):
        return {
            "ok": False,
            "state": registry.get("state"),
            "path": registry.get("path"),
            "error": registry.get("error"),
            "master_god": registry.get("master_god", {}),
            "features": [],
            "master_review_queue": [],
            "merge_queue": [],
            "blockers": [registry.get("error", "invalid feature registry")],
        }

    features = [
        classify_feature_lane(loop, feature, project_root=project_root)
        for feature in registry.get("features", [])
        if isinstance(feature, dict)
    ]
    malformed_count = sum(
        1 for feature in registry.get("features", []) if not isinstance(feature, dict)
    )
    blockers: list[str] = []
    if malformed_count:
        blockers.append(f"{malformed_count} feature entries are not objects")
    for feature in features:
        for blocker in feature["blockers"]:
            blockers.append(f"{feature['id']}: {blocker}")

    def _queue_item(feature: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": feature["id"],
            "branch": feature["branch"],
            "worktree": feature["worktree"],
            "target_branch": feature["merge"].get("target_branch"),
            "strategy": feature["merge"].get("strategy", "git_worktree"),
        }

    master_review_queue = [
        _queue_item(feature)
        for feature in features
        if feature["reviewable"]
    ]
    merge_queue = [
        _queue_item(feature)
        for feature in features
        if feature["mergeable"]
    ]
    return {
        "ok": not blockers,
        "state": registry.get("state"),
        "path": registry.get("path"),
        "master_god": registry.get("master_god", {}),
        "features": features,
        "master_review_queue": master_review_queue,
        "merge_queue": merge_queue,
        "blockers": blockers,
        "counts": {
            "features": len(features),
            "reviewable": len(master_review_queue),
            "mergeable": len(merge_queue),
            "blocked": sum(1 for feature in features if feature["blockers"]),
        },
    }


def write_master_slave_status(
    loop_root: str | Path,
    summary: dict[str, Any] | None = None,
) -> dict[str, str]:
    loop = Path(loop_root)
    payload = summary or summarize_master_slave_control(loop)
    json_path = loop / "master_slave_status.json"
    md_path = loop / "master_slave_status.md"
    _atomic_write_json(json_path, payload)

    lines = ["# Hermes Master/Slave Feature Status", ""]
    lines.append(f"- registry: `{payload.get('path')}`")
    lines.append(f"- ok: `{payload.get('ok')}`")
    lines.append(f"- features: `{payload.get('counts', {}).get('features', 0)}`")
    lines.append(f"- reviewable: `{payload.get('counts', {}).get('reviewable', 0)}`")
    lines.append(f"- mergeable: `{payload.get('counts', {}).get('mergeable', 0)}`")
    lines.append("")
    for feature in payload.get("features", []):
        lines.append(
            f"- `{feature.get('id')}` state={feature.get('state')} "
            f"reviewable={feature.get('reviewable')} "
            f"mergeable={feature.get('mergeable')} branch={feature.get('branch')}"
        )
        for blocker in feature.get("blockers", []):
            lines.append(f"  - blocker: {blocker}")
        for warning in feature.get("warnings", []):
            lines.append(f"  - warning: {warning}")
    if payload.get("master_review_queue"):
        lines.append("")
        lines.append("## Master Review Queue")
        for item in payload["master_review_queue"]:
            lines.append(
                f"- `{item.get('id')}` {item.get('branch')} -> {item.get('target_branch')} "
                f"via {item.get('strategy')}"
            )
    if payload.get("merge_queue"):
        lines.append("")
        lines.append("## Merge Queue")
        for item in payload["merge_queue"]:
            lines.append(
                f"- `{item.get('id')}` {item.get('branch')} -> {item.get('target_branch')} "
                f"via {item.get('strategy')}"
            )
    _atomic_write_text(md_path, "\n".join(lines) + "\n")
    return {"json": str(json_path), "markdown": str(md_path)}


def summarize_eval_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        return {
            "valid": False,
            "error": "missing report",
            "path": str(report_path),
            "rows_done": 0,
        }
    try:
        rows = _read_json(report_path)
    except Exception as exc:
        return {
            "valid": False,
            "error": f"invalid json: {exc}",
            "path": str(report_path),
            "rows_done": 0,
        }
    if not isinstance(rows, list):
        return {
            "valid": False,
            "error": "report root is not a list",
            "path": str(report_path),
            "rows_done": 0,
        }

    verdicts = [str(row.get("verdict", "")).lower() for row in rows if isinstance(row, dict)]
    answer_modes = [
        str(row.get("answer_mode", "missing")).lower() for row in rows if isinstance(row, dict)
    ]
    judge_statuses = [
        str(row.get("judge_status") or row.get("verdict") or "missing").lower()
        for row in rows
        if isinstance(row, dict)
    ]
    movements = [
        str(row.get("movement_status") or row.get("movement", "")).lower()
        for row in rows
        if isinstance(row, dict)
    ]
    last_case_id = None
    if rows and isinstance(rows[-1], dict):
        last_case_id = rows[-1].get("case_id")

    stat = report_path.stat()
    return {
        "valid": True,
        "path": str(report_path),
        "rows_done": len(rows),
        "last_case_id": last_case_id,
        "pass_count": verdicts.count("pass"),
        "fail_count": verdicts.count("fail"),
        "answer_mode_counts": _counter_dict(answer_modes),
        "judge_status_counts": _counter_dict(judge_statuses),
        "movement_counts": _counter_dict(movements),
        "file_size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def _llm_promotion_problem(summary: dict[str, Any]) -> str | None:
    rows_done = summary.get("rows_done", 0)
    if rows_done == 0:
        return "requires llm answer and judge but report has no rows"
    answer_mode_counts = summary.get("answer_mode_counts", {})
    if answer_mode_counts.get("llm", 0) != rows_done:
        return "requires llm answer and judge but some rows are not llm answer mode"
    judge_status_counts = summary.get("judge_status_counts", {})
    non_judged = {
        key: value
        for key, value in judge_status_counts.items()
        if key not in {"pass", "fail", "passed", "failed", "judge_pass", "judge_fail"}
    }
    if non_judged:
        return f"requires llm answer and judge but non-judged rows exist: {non_judged}"
    return None


def classify_eval_run(
    *,
    run_id: str,
    benchmark: str,
    partial_path: str | Path,
    final_path: str | Path,
    previous_snapshot: dict[str, Any] | None = None,
    now: float | None = None,
    stale_after_seconds: int = 900,
    require_llm: bool = True,
) -> dict[str, Any]:
    partial = Path(partial_path)
    final = Path(final_path)
    current_time = time.time() if now is None else now

    if final.exists():
        summary = summarize_eval_report(final)
        state = "completed" if summary.get("valid") else "invalid_final"
        reason = (
            "final report exists"
            if state == "completed"
            else summary.get("error", "invalid final")
        )
        if require_llm and summary.get("valid"):
            problem = _llm_promotion_problem(summary)
            if problem:
                state = "invalid_for_promotion"
                reason = problem
        return {
            "run_id": run_id,
            "benchmark": benchmark,
            "state": state,
            "reason": reason,
            **summary,
        }

    if not partial.exists():
        return {
            "run_id": run_id,
            "benchmark": benchmark,
            "state": "missing",
            "reason": "no partial or final report",
            "rows_done": 0,
        }

    summary = summarize_eval_report(partial)
    if not summary.get("valid"):
        return {
            "run_id": run_id,
            "benchmark": benchmark,
            "state": "invalid_partial",
            "reason": summary.get("error", "invalid partial"),
            **summary,
        }

    if require_llm:
        problem = _llm_promotion_problem(summary)
        if problem:
            return {
                "run_id": run_id,
                "benchmark": benchmark,
                "state": "invalid_for_promotion",
                "reason": problem,
                **summary,
            }

    if previous_snapshot:
        grew = (
            summary.get("file_size", 0) > previous_snapshot.get("file_size", 0)
            or summary.get("rows_done", 0) > previous_snapshot.get("rows_done", 0)
            or summary.get("mtime", 0) > previous_snapshot.get("mtime", 0)
        )
        if grew:
            return {
                "run_id": run_id,
                "benchmark": benchmark,
                "state": "running_or_progressing",
                "reason": "partial grew since previous snapshot",
                **summary,
            }

    age = current_time - float(summary.get("mtime", current_time))
    if age > stale_after_seconds:
        return {
            "run_id": run_id,
            "benchmark": benchmark,
            "state": "stalled",
            "reason": f"no final report and partial stale for {age:.0f}s",
            **summary,
        }
    return {
        "run_id": run_id,
        "benchmark": benchmark,
        "state": "running_or_progressing",
        "reason": "partial mtime is fresh",
        **summary,
    }


def check_state_ack_consistency(loop_root: str | Path, phase_id: str) -> dict[str, Any]:
    loop = Path(loop_root)
    phase_dir = loop / "work" / phase_id
    blockers: list[str] = []

    ack_path = phase_dir / "ack.json"
    review_path = phase_dir / "review_verdict.json"
    result_path = phase_dir / "result.md"

    ack: dict[str, Any] = {}
    review: dict[str, Any] = {}

    if not ack_path.exists():
        blockers.append("missing ack.json")
    else:
        try:
            ack = _read_json(ack_path)
        except Exception as exc:
            blockers.append(f"invalid ack.json: {exc}")
        if ack and str(ack.get("ack_level", "")).lower() != "usable":
            blockers.append("ack_level is not usable")

    if not review_path.exists():
        blockers.append("missing review_verdict.json")
    else:
        try:
            review = _read_json(review_path)
        except Exception as exc:
            blockers.append(f"invalid review_verdict.json: {exc}")
        verdict = str(review.get("verdict", "")).lower() if review else ""
        if review and verdict not in PROMOTION_PASS_VERDICTS:
            blockers.append("review verdict is not passing")

    if not result_path.exists():
        blockers.append("missing result.md")

    ack_bundle = _context_bundle_path(ack.get("context_bundle")) if ack else None
    review_bundle = _context_bundle_path(review.get("context_bundle")) if review else None
    if ack_bundle and review_bundle and ack_bundle != review_bundle:
        blockers.append("ack/review context_bundle mismatch")
    if ack_bundle and result_path.exists():
        result_text = result_path.read_text(encoding="utf-8", errors="replace")
        if ack_bundle not in result_text:
            blockers.append("result.md does not reference ack context_bundle")

    return {
        "phase_id": phase_id,
        "ok": not blockers,
        "blockers": blockers,
        "ack_path": str(ack_path),
        "review_path": str(review_path),
        "result_path": str(result_path),
    }


def _benchmark_eval_decision_runs(decision: Any) -> bool:
    return isinstance(decision, dict) and bool(decision.get("run"))


def check_review_eval_decision(loop_root: str | Path, phase_id: str) -> dict[str, Any]:
    loop = Path(loop_root)
    review_path = loop / "work" / phase_id / "review_verdict.json"
    blockers: list[str] = []

    if not review_path.exists():
        return {
            "phase_id": phase_id,
            "ok": False,
            "blockers": ["missing review_verdict.json"],
            "review_path": str(review_path),
        }

    try:
        review = _read_json(review_path)
    except Exception as exc:
        return {
            "phase_id": phase_id,
            "ok": False,
            "blockers": [f"invalid review_verdict.json: {exc}"],
            "review_path": str(review_path),
        }

    if not isinstance(review, dict):
        return {
            "phase_id": phase_id,
            "ok": False,
            "blockers": ["review_verdict root is not an object"],
            "review_path": str(review_path),
        }

    eval_decision = review.get("review_eval_decision")
    if not isinstance(eval_decision, dict):
        return {
            "phase_id": phase_id,
            "ok": False,
            "blockers": ["missing review_eval_decision"],
            "review_path": str(review_path),
        }

    scope = str(eval_decision.get("scope", "")).lower()
    reason = str(eval_decision.get("reason", "")).strip()
    promotion_gate = str(eval_decision.get("promotion_gate", "")).lower()
    decision = str(review.get("decision", "")).lower()
    verdict = str(review.get("verdict", "")).lower()
    longmemeval = eval_decision.get("longmemeval")
    locomo = eval_decision.get("locomo")
    lme_runs = _benchmark_eval_decision_runs(longmemeval)
    locomo_runs = _benchmark_eval_decision_runs(locomo)

    if scope not in {"not_applicable", "smoke", "milestone"}:
        blockers.append("review_eval_decision.scope is invalid")
    if not reason:
        blockers.append("review_eval_decision.reason is required")
    if promotion_gate not in {"satisfied", "not_applicable", "not_satisfied"}:
        blockers.append("review_eval_decision.promotion_gate is invalid")
    if not isinstance(longmemeval, dict):
        blockers.append("review_eval_decision.longmemeval is required")
    if not isinstance(locomo, dict):
        blockers.append("review_eval_decision.locomo is required")

    if decision == "advance" and promotion_gate not in {"satisfied", "not_applicable"}:
        blockers.append("advance requires promotion_gate satisfied or not_applicable")

    if scope == "milestone":
        if not (lme_runs and locomo_runs):
            blockers.append("milestone scope requires both LongMemEval and LoCoMo")
        if promotion_gate == "satisfied" and not (
            bool(eval_decision.get("llm_answer")) and bool(eval_decision.get("llm_judge"))
        ):
            blockers.append("satisfied milestone promotion requires llm_answer and llm_judge")

    if (
        verdict in PROMOTION_PASS_VERDICTS
        and promotion_gate == "satisfied"
        and scope != "not_applicable"
        and lme_runs != locomo_runs
    ):
        blockers.append("promotion evidence cannot be LongMemEval-only or LoCoMo-only")

    return {
        "phase_id": phase_id,
        "ok": not blockers,
        "blockers": blockers,
        "review_path": str(review_path),
        "review_eval_decision": eval_decision,
    }


def check_execute_goal_contract(loop_root: str | Path, phase_id: str) -> dict[str, Any]:
    loop = Path(loop_root)
    goal_path = loop / "work" / phase_id / "execute_goal.md"
    blockers: list[str] = []

    if not goal_path.exists():
        return {
            "phase_id": phase_id,
            "ok": False,
            "blockers": ["missing execute_goal.md"],
            "goal_path": str(goal_path),
        }

    text = goal_path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""

    if first_line != f"# phase: {phase_id}":
        blockers.append("execute_goal.md phase binding mismatch")
    if "/goal" not in text:
        blockers.append("execute_goal.md missing /goal command")
    if "real memoryos" not in lowered and "real v3" not in lowered:
        blockers.append("execute_goal.md must require real MemoryOS path wiring")
    if "result.md" not in lowered:
        blockers.append("execute_goal.md must require result.md")
    if "test" not in lowered:
        blockers.append("execute_goal.md must require tests")
    if "demo-only" not in lowered and "demo only" not in lowered:
        blockers.append("execute_goal.md must forbid demo-only implementation")
    if not re.search(r"max repair cycles:\s*[1-3]\b", text, flags=re.IGNORECASE):
        blockers.append("execute_goal.md must cap max repair cycles at 1-3")

    forbidden_score_patterns = (
        r"target\s+score",
        r"score\s*(?:>=|>|=)",
        r"pass\s+rate\s*(?:>=|>|=)",
        r"accuracy\s*(?:>=|>|=)",
        r"must\s+pass\s+\d+\s*/\s*\d+",
    )
    if any(re.search(pattern, lowered) for pattern in forbidden_score_patterns):
        blockers.append("execute_goal.md contains forbidden benchmark score target")

    return {
        "phase_id": phase_id,
        "ok": not blockers,
        "blockers": blockers,
        "goal_path": str(goal_path),
    }


def check_config_blueprint_consistency(loop_root: str | Path) -> dict[str, Any]:
    loop = Path(loop_root)
    config_path = loop / "config.json"
    blueprint_path = loop / "blueprint.md"
    blockers: list[str] = []
    missing_headings: list[dict[str, str]] = []

    if not config_path.exists():
        blockers.append("missing config.json")
    if not blueprint_path.exists():
        blockers.append("missing blueprint.md")
    if blockers:
        return {"ok": False, "blockers": blockers, "missing_headings": missing_headings}

    try:
        config = _read_json(config_path)
    except Exception as exc:
        return {
            "ok": False,
            "blockers": [f"invalid config.json: {exc}"],
            "missing_headings": missing_headings,
        }

    blueprint = blueprint_path.read_text(encoding="utf-8", errors="replace")
    headings = set(re.findall(r"^(?:##|###)\s+(.+)$", blueprint, flags=re.MULTILINE))
    phases = config.get("phases", []) if isinstance(config, dict) else []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        heading = phase.get("blueprint_heading")
        phase_id = phase.get("id")
        if isinstance(heading, str) and heading not in headings:
            missing_headings.append({"phase": str(phase_id), "heading": heading})

    if missing_headings:
        blockers.append("config phase blueprint_heading missing from blueprint.md")
    return {
        "ok": not blockers,
        "blockers": blockers,
        "missing_headings": missing_headings,
    }


def _phase_index(phase_id: str) -> int | None:
    match = re.fullmatch(r"phase-(\d+)", phase_id)
    if not match:
        return None
    return int(match.group(1))


def _has_superseded_adjustment(loop_root: Path, phase_id: str) -> bool:
    adjustment_path = loop_root / "work" / phase_id / "adjustment.md"
    if not adjustment_path.exists():
        return False
    text = adjustment_path.read_text(encoding="utf-8", errors="replace").lower()
    return "superseded" in text or "repeat_phase" in text or "god_adjust" in text


def check_state_phase_order(loop_root: str | Path) -> dict[str, Any]:
    loop = Path(loop_root)
    state_path = loop / "state.json"
    if not state_path.exists():
        return {"ok": False, "blockers": ["missing state.json"], "problems": []}

    try:
        state = _read_json(state_path)
    except Exception as exc:
        return {"ok": False, "blockers": [f"invalid state.json: {exc}"], "problems": []}

    current_phase_idx = state.get("current_phase_idx") if isinstance(state, dict) else None
    phases = state.get("phases", []) if isinstance(state, dict) else []
    if not isinstance(current_phase_idx, int):
        return {
            "ok": False,
            "blockers": ["current_phase_idx is missing or not an integer"],
            "problems": [],
        }

    problems: list[dict[str, str]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_id = str(phase.get("id", ""))
        phase_idx = _phase_index(phase_id)
        if phase_idx is None:
            continue
        status = str(phase.get("status", ""))
        if phase_idx < current_phase_idx:
            if status == "completed":
                continue
            if status == "superseded" and _has_superseded_adjustment(loop, phase_id):
                continue
            problems.append(
                {
                    "phase": phase_id,
                    "status": status,
                    "reason": (
                        "phase before current_phase_idx is not completed "
                        "or documented superseded"
                    ),
                }
            )
        if phase_idx > current_phase_idx and status == "completed":
            problems.append(
                {
                    "phase": phase_id,
                    "status": status,
                    "reason": "phase after current_phase_idx is completed",
                }
            )

    return {"ok": not problems, "blockers": [], "problems": problems}


def check_execute_bootstrap_gate(loop_root: str | Path) -> dict[str, Any]:
    loop = Path(loop_root)
    state_path = loop / "state.json"
    if not state_path.exists():
        return {
            "ok": False,
            "phase_id": None,
            "action": "missing_state",
            "blockers": ["missing state.json"],
        }

    try:
        state = _read_json(state_path)
    except Exception as exc:
        return {
            "ok": False,
            "phase_id": None,
            "action": "invalid_state",
            "blockers": [f"invalid state.json: {exc}"],
        }

    execute_lane = state.get("execute_lane") if isinstance(state, dict) else {}
    phase_id = (
        str(execute_lane.get("phase"))
        if isinstance(execute_lane, dict) and execute_lane.get("phase")
        else None
    )
    current_state = str(state.get("current_state", "")).upper() if isinstance(state, dict) else ""
    if not phase_id:
        return {
            "ok": True,
            "phase_id": phase_id,
            "action": "not_in_execute",
            "blockers": [],
        }

    phase_dir = loop / "work" / phase_id
    required_files = ("context_bundle.md", "god_dispatch.json", "plan_final.md")
    present = []
    missing = []
    for name in required_files:
        path = phase_dir / name
        if path.exists():
            present.append(name)
        else:
            missing.append(f"missing {name}")

    if current_state == "GOD_DISPATCH":
        missing_names = [item.removeprefix("missing ") for item in missing]
        return {
            "phase_id": phase_id,
            "ok": True,
            "action": "promote_execute" if not missing else "dispatch_incomplete",
            "blockers": [],
            "present_files": present,
            "missing_files": missing_names,
            "phase_dir": str(phase_dir),
        }

    if current_state != "EXECUTE":
        return {
            "ok": True,
            "phase_id": phase_id,
            "action": "not_in_execute",
            "blockers": [],
        }

    blockers: list[str] = []
    if missing:
        blockers.extend(missing)
        action = "bootstrap_dispatch"
    else:
        action = "allow_execute"

    return {
        "phase_id": phase_id,
        "ok": not blockers,
        "action": action,
        "blockers": blockers,
        "present_files": present,
        "phase_dir": str(phase_dir),
    }


def promote_dispatch_to_execute(
    loop_root: str | Path,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    status = check_execute_bootstrap_gate(loop)
    if status.get("action") != "promote_execute":
        return {
            **status,
            "promoted": False,
        }

    state_path = loop / "state.json"
    state = _read_json(state_path)
    phase_id = str(status.get("phase_id"))
    timestamp = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["current_state"] = "EXECUTE"
    state.setdefault("execute_lane", {})["state"] = "EXECUTE"
    state["last_updated"] = timestamp
    _atomic_write_json(state_path, state)

    phase_dir = loop / "work" / phase_id
    phase_status_path = phase_dir / "phase_status.md"
    if phase_status_path.exists():
        previous = phase_status_path.read_text(encoding="utf-8", errors="replace").rstrip()
    else:
        previous = f"# phase: {phase_id}"

    note = (
        "\n\n## GOD_DISPATCH Auto-Promote To EXECUTE\n\n"
        f"Time: {timestamp}\n\n"
        "Reason: `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` "
        "already exist for the active execute phase. Launcher preflight promoted "
        "the controller to `EXECUTE` without waiting for prompt-level action.\n"
    )
    if "## GOD_DISPATCH Auto-Promote To EXECUTE" not in previous:
        _atomic_write_text(phase_status_path, previous + note)

    return {
        **status,
        "ok": True,
        "action": "promoted_execute",
        "promoted": True,
        "state_path": str(state_path),
        "phase_status_path": str(phase_status_path),
    }


def _markdown_phase_bound(path: Path, phase_id: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    first_line = lines[0].strip() if lines else ""
    return first_line == f"# phase: {phase_id}"


def check_execute_completion_gate(loop_root: str | Path) -> dict[str, Any]:
    loop = Path(loop_root)
    state_path = loop / "state.json"
    if not state_path.exists():
        return {
            "ok": False,
            "phase_id": None,
            "action": "missing_state",
            "blockers": ["missing state.json"],
        }

    try:
        state = _read_json(state_path)
    except Exception as exc:
        return {
            "ok": False,
            "phase_id": None,
            "action": "invalid_state",
            "blockers": [f"invalid state.json: {exc}"],
        }

    execute_lane = state.get("execute_lane") if isinstance(state, dict) else {}
    phase_id = (
        str(execute_lane.get("phase"))
        if isinstance(execute_lane, dict) and execute_lane.get("phase")
        else None
    )
    current_state = str(state.get("current_state", "")).upper() if isinstance(state, dict) else ""
    if not phase_id or current_state != "EXECUTE":
        return {
            "ok": True,
            "phase_id": phase_id,
            "action": "not_in_execute",
            "blockers": [],
        }

    phase_dir = loop / "work" / phase_id
    result_path = phase_dir / "result.md"
    if not result_path.exists():
        return {
            "ok": True,
            "phase_id": phase_id,
            "action": "wait_execute",
            "blockers": [],
            "missing_files": ["result.md"],
            "phase_dir": str(phase_dir),
        }

    if not _markdown_phase_bound(result_path, phase_id):
        return {
            "ok": False,
            "phase_id": phase_id,
            "action": "blocked_stale_result",
            "blockers": ["result.md phase binding mismatch"],
            "result_path": str(result_path),
            "phase_dir": str(phase_dir),
        }

    return {
        "ok": True,
        "phase_id": phase_id,
        "action": "promote_execute_self_review",
        "blockers": [],
        "present_files": ["result.md"],
        "result_path": str(result_path),
        "phase_dir": str(phase_dir),
    }


def promote_execute_to_self_review(
    loop_root: str | Path,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    loop = Path(loop_root)
    status = check_execute_completion_gate(loop)
    if status.get("action") != "promote_execute_self_review":
        return {
            **status,
            "promoted": False,
        }

    state_path = loop / "state.json"
    state = _read_json(state_path)
    phase_id = str(status.get("phase_id"))
    timestamp = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["current_state"] = "EXECUTE_SELF_REVIEW"
    state.setdefault("execute_lane", {})["state"] = "EXECUTE_SELF_REVIEW"
    state["last_updated"] = timestamp
    _atomic_write_json(state_path, state)

    phase_dir = loop / "work" / phase_id
    phase_status_path = phase_dir / "phase_status.md"
    if phase_status_path.exists():
        previous = phase_status_path.read_text(encoding="utf-8", errors="replace").rstrip()
    else:
        previous = f"# phase: {phase_id}"

    note = (
        "\n\n## EXECUTE Auto-Promote To EXECUTE_SELF_REVIEW\n\n"
        f"Time: {timestamp}\n\n"
        "Reason: phase-bound `result.md` exists for the active execute phase. "
        "Controller hardening promoted the state to `EXECUTE_SELF_REVIEW` "
        "without waiting for prompt-level action.\n"
    )
    if "## EXECUTE Auto-Promote To EXECUTE_SELF_REVIEW" not in previous:
        _atomic_write_text(phase_status_path, previous + note)

    return {
        **status,
        "ok": True,
        "action": "promoted_execute_self_review",
        "promoted": True,
        "state_path": str(state_path),
        "phase_status_path": str(phase_status_path),
    }


def scan_stale_artifacts(
    phase_dir: str | Path,
    *,
    current_context_bundle: str,
    candidate_files: tuple[str, ...] = STALE_CANDIDATE_FILES,
) -> dict[str, Any]:
    phase = Path(phase_dir)
    stale_files: list[str] = []
    active_files: list[str] = []
    missing_files: list[str] = []

    for name in candidate_files:
        path = phase / name
        if not path.exists():
            missing_files.append(name)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if current_context_bundle in text:
            active_files.append(name)
        else:
            stale_files.append(name)

    return {
        "phase_dir": str(phase),
        "current_context_bundle": current_context_bundle,
        "stale_files": stale_files,
        "active_files": active_files,
        "missing_files": missing_files,
    }


def generate_shard_resume_plan(
    *,
    benchmark: str,
    data_path: str,
    baseline: str,
    run_id_prefix: str,
    limit: int,
    shard_size: int,
    comparison_report: str | None = None,
) -> str:
    lines = [
        "# Shard Resume Plan",
        "",
        "Run shards only after the monolithic 50-case run is confirmed stalled or invalid.",
        "",
    ]
    shard_count = math.ceil(limit / shard_size)
    for shard_idx in range(shard_count):
        start = shard_idx * shard_size + 1
        end = min(limit, (shard_idx + 1) * shard_size)
        run_id = f"{run_id_prefix}_s{shard_idx + 1:02d}_{start:03d}_{end:03d}"
        comparison = f" --comparison-report {comparison_report}" if comparison_report else ""
        lines.append(
            "MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public "
            f"--benchmark {benchmark} "
            f"--data-path {data_path} "
            f"--baseline {baseline} "
            f"--limit {end - start + 1} "
            "--llm-answer --llm-judge"
            f"{comparison} "
            f"--run-id {run_id}"
        )
    return "\n".join(lines) + "\n"


def write_phase_status(
    loop_root: str | Path,
    phase_id: str,
    statuses: list[dict[str, Any]],
    *,
    ack_gate: dict[str, Any] | None = None,
    stale_index: dict[str, Any] | None = None,
) -> dict[str, Path]:
    loop = Path(loop_root)
    phase_dir = loop / "work" / phase_id
    phase_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase_id": phase_id,
        "eval_runs": statuses,
        "ack_gate": ack_gate,
        "stale_index": stale_index,
    }
    json_path = phase_dir / "eval_heartbeat.json"
    md_path = phase_dir / "eval_heartbeat.md"
    status_path = phase_dir / f"{phase_id}_status.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [f"# {phase_id} Eval Heartbeat", ""]
    for status in statuses:
        lines.append(
            f"- {status.get('benchmark')} `{status.get('run_id')}`: "
            f"{status.get('state')} rows={status.get('rows_done', 0)} "
            f"pass={status.get('pass_count', 0)} fail={status.get('fail_count', 0)} "
            f"reason={status.get('reason')}"
        )
    if ack_gate is not None:
        lines.append("")
        lines.append(f"- ack_gate: {'ok' if ack_gate.get('ok') else 'blocked'}")
        for blocker in ack_gate.get("blockers", []):
            lines.append(f"  - {blocker}")
    md = "\n".join(lines) + "\n"
    md_path.write_text(md, encoding="utf-8")
    status_path.write_text(md, encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "status": status_path}


def run_phase_hardening(
    loop_root: str | Path,
    eval_root: str | Path,
    phase_id: str,
    *,
    write: bool = False,
) -> dict[str, Any]:
    loop = Path(loop_root)
    _ = Path(eval_root)
    context_bundle = f"work/{phase_id}/context_bundle.md"
    statuses: list[dict[str, Any]] = []
    ack_gate = check_state_ack_consistency(loop, phase_id)
    review_eval_gate = check_review_eval_decision(loop, phase_id)
    execute_goal_gate = check_execute_goal_contract(loop, phase_id)
    if write:
        execute_completion_gate = promote_execute_to_self_review(loop)
    else:
        execute_completion_gate = check_execute_completion_gate(loop)
    stale_index = scan_stale_artifacts(
        loop / "work" / phase_id,
        current_context_bundle=context_bundle,
    )
    config_gate = check_config_blueprint_consistency(loop)
    state_order_gate = check_state_phase_order(loop)
    master_slave = summarize_master_slave_control(loop, project_root=loop.parent)
    if write:
        write_phase_status(
            loop,
            phase_id,
            statuses,
            ack_gate=ack_gate,
            stale_index=stale_index,
        )
        write_master_slave_status(loop, master_slave)
    return {
        "phase_id": phase_id,
        "eval_runs": statuses,
        "ack_gate": ack_gate,
        "review_eval_gate": review_eval_gate,
        "execute_goal_gate": execute_goal_gate,
        "execute_completion_gate": execute_completion_gate,
        "stale_index": stale_index,
        "config_gate": config_gate,
        "state_order_gate": state_order_gate,
        "master_slave": master_slave,
    }


def _run_phase8(loop_root: Path, eval_root: Path, write: bool) -> dict[str, Any]:
    reports = loop_root / "work" / "phase-8" / "reports" / "run_ids.txt"
    run_ids: dict[str, str] = {}
    if reports.exists():
        for line in reports.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                run_ids[key.strip()] = value.strip()

    specs = [
        ("longmemeval", run_ids.get("LME_RUN_ID", "")),
        ("locomo", run_ids.get("LOCOMO_RUN_ID", "")),
    ]
    statuses = []
    for benchmark, run_id in specs:
        if not run_id:
            continue
        suffix = "longmemeval" if benchmark == "longmemeval" else "locomo"
        statuses.append(
            classify_eval_run(
                run_id=run_id,
                benchmark=benchmark,
                partial_path=eval_root / f"{run_id}_{suffix}.partial.json",
                final_path=eval_root / f"{run_id}_{suffix}.json",
            )
        )

    ack_gate = check_state_ack_consistency(loop_root, "phase-8")
    stale_index = scan_stale_artifacts(
        loop_root / "work" / "phase-8", current_context_bundle="work/phase-8/context_bundle.md"
    )
    if write:
        write_phase_status(
            loop_root,
            "phase-8",
            statuses,
            ack_gate=ack_gate,
            stale_index=stale_index,
        )
    return {"eval_runs": statuses, "ack_gate": ack_gate, "stale_index": stale_index}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop-root", default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--eval-root",
        default=Path(__file__).resolve().parent.parent / ".memoryos" / "evals",
    )
    parser.add_argument("--phase", default="phase-8")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    loop_root = Path(args.loop_root)
    if args.phase == "phase-8":
        result = _run_phase8(loop_root, Path(args.eval_root), args.write)
    else:
        result = run_phase_hardening(
            loop_root,
            Path(args.eval_root),
            args.phase,
            write=args.write,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
