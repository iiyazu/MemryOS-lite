#!/usr/bin/env python3
"""Hermes hardening helpers for long eval observation and promotion gates.

This module is intentionally additive. It does not mutate state.json or eval
reports; writes are limited to explicit heartbeat/status artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
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


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    if args.phase != "phase-8":
        raise SystemExit("only phase-8 auto-discovery is currently supported")
    result = _run_phase8(loop_root, Path(args.eval_root), args.write)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
