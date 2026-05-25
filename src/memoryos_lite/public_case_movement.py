from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MOVEMENT_STATUS_KEYS = (
    "fail_to_pass",
    "pass_to_fail",
    "unchanged_pass",
    "unchanged_fail",
    "new_case_no_baseline",
)
FAILURE_CLASS_KEYS = (
    "retrieval_miss",
    "evidence_retrieved_not_selected",
    "evidence_selected_not_rendered",
    "evidence_rendered_not_answer_evidence",
    "unsupported_answer",
    "evidence_hit_answer_fail",
    "supported_cited_answer",
    "judge_questionable",
    "unknown",
)
FAILURE_BOUNDARY_KEYS = (
    "retrieval_miss",
    "selected_drop",
    "render_drop",
    "answer_evidence_drop",
    "citation_drop",
    "none",
    "unknown",
)


@dataclass(frozen=True)
class BaselineCaseVerdict:
    benchmark: str
    baseline: str
    case_id: str
    verdict: str
    source: str


MovementKey = tuple[str, str, str]


def load_public_case_movement(paths: Iterable[Path]) -> dict[MovementKey, BaselineCaseVerdict]:
    comparison: dict[MovementKey, BaselineCaseVerdict] = {}
    for path in paths:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"comparison report must be a JSON list: {path}")
        for row in rows:
            if not isinstance(row, dict):
                continue
            benchmark = str(row.get("benchmark") or "")
            baseline = str(row.get("baseline") or "")
            case_id = str(row.get("case_id") or "")
            if not benchmark or not baseline or not case_id:
                continue
            verdict = _row_verdict(row)
            comparison[(benchmark, baseline, case_id)] = BaselineCaseVerdict(
                benchmark=benchmark,
                baseline=baseline,
                case_id=case_id,
                verdict=verdict,
                source=str(path),
            )
    return comparison


def movement_status(baseline_verdict: str | None, current_verdict: str) -> str:
    current = _normalize_verdict(current_verdict)
    if baseline_verdict is None:
        return "new_case_no_baseline"
    baseline = _normalize_verdict(baseline_verdict)
    if baseline == "pass" and current != "pass":
        return "pass_to_fail"
    if baseline in {"fail", "error"} and current == "pass":
        return "fail_to_pass"
    if baseline == "pass" and current == "pass":
        return "unchanged_pass"
    if baseline in {"fail", "error"} and current != "pass":
        return "unchanged_fail"
    return "unchanged_fail"


def build_public_case_movement_summary(
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    movement: dict[str, list[str]] = {key: [] for key in MOVEMENT_STATUS_KEYS}
    failure_classes: dict[str, list[str]] = {
        key: [] for key in FAILURE_CLASS_KEYS
    }
    failure_boundaries: dict[str, list[str]] = {
        key: [] for key in FAILURE_BOUNDARY_KEYS
    }
    total_cases = 0

    for row in rows:
        case_id = _row_case_id(row)
        if case_id is None:
            continue
        total_cases += 1
        _append_grouped(movement, _row_movement_status(row), case_id)
        _append_grouped(failure_classes, _row_failure_class(row), case_id)
        _append_grouped(failure_boundaries, _row_failure_boundary(row), case_id)

    return {
        "total_cases": total_cases,
        "movement": movement,
        "failure_classes": failure_classes,
        "failure_boundaries": failure_boundaries,
        "counts": {
            "movement": {key: len(value) for key, value in movement.items()},
            "failure_classes": {
                key: len(value) for key, value in failure_classes.items()
            },
            "failure_boundaries": {
                key: len(value) for key, value in failure_boundaries.items()
            },
        },
        "source_hit_semantics": "final_projection_source_overlap",
        "diagnostic_note": (
            "Movement summarizes verdict changes. Failure boundaries come from "
            "case_diagnostics.evidence_handoff and do not infer retrieval "
            "localization from public source_hit."
        ),
    }


def _row_verdict(row: dict[str, object]) -> str:
    raw = row.get("verdict")
    if raw is None and "pass" in row:
        raw = "pass" if row.get("pass") is True else "fail"
    return _normalize_verdict(str(raw))


def _normalize_verdict(value: str) -> str:
    verdict = value.strip().lower()
    if verdict not in {"pass", "fail", "error"}:
        raise ValueError(f"unsupported public benchmark verdict: {value!r}")
    return verdict


def _row_case_id(row: dict[str, Any]) -> str | None:
    case_id = row.get("case_id")
    return case_id if isinstance(case_id, str) and case_id else None


def _row_movement_status(row: dict[str, Any]) -> str:
    movement = row.get("movement_status")
    if isinstance(movement, str) and movement:
        return movement
    diagnostics = row.get("case_diagnostics")
    if isinstance(diagnostics, dict):
        movement = diagnostics.get("movement_status")
        if isinstance(movement, str) and movement:
            return movement
    return "new_case_no_baseline"


def _row_failure_class(row: dict[str, Any]) -> str:
    failure_class = row.get("failure_class")
    if isinstance(failure_class, str) and failure_class:
        return failure_class
    diagnostics = row.get("case_diagnostics")
    if isinstance(diagnostics, dict):
        failure_class = diagnostics.get("failure_class")
        if isinstance(failure_class, str) and failure_class:
            return failure_class
    return "unknown"


def _row_failure_boundary(row: dict[str, Any]) -> str:
    diagnostics = row.get("case_diagnostics")
    if not isinstance(diagnostics, dict):
        return "unknown"
    handoff = diagnostics.get("evidence_handoff")
    if not isinstance(handoff, dict):
        return "unknown"
    boundary = handoff.get("failure_boundary")
    return boundary if isinstance(boundary, str) and boundary else "unknown"


def _append_grouped(groups: dict[str, list[str]], key: str, case_id: str) -> None:
    bucket = key or "unknown"
    groups.setdefault(bucket, [])
    if case_id not in groups[bucket]:
        groups[bucket].append(case_id)
