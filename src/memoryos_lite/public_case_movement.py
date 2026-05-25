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
SOURCE_METRIC_KEYS = (
    "source_hit",
    "planned_evidence_source_hit_at_5",
    "episode_source_hit_at_10",
)
SOURCE_METRIC_MOVEMENT_KEYS = (
    "improved",
    "regressed",
    "unchanged_hit",
    "unchanged_miss",
)


@dataclass(frozen=True)
class BaselineCaseVerdict:
    benchmark: str
    baseline: str
    case_id: str
    verdict: str
    source: str
    source_hit: bool | None = None
    planned_evidence_source_hit_at_5: bool | None = None
    episode_source_hit_at_10: bool | None = None

    def source_metrics(self) -> dict[str, bool | None]:
        return {
            "source_hit": self.source_hit,
            "planned_evidence_source_hit_at_5": self.planned_evidence_source_hit_at_5,
            "episode_source_hit_at_10": self.episode_source_hit_at_10,
        }


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
                source_hit=_bool_or_none(row.get("source_hit")),
                planned_evidence_source_hit_at_5=_bool_or_none(
                    row.get("planned_evidence_source_hit_at_5")
                ),
                episode_source_hit_at_10=_bool_or_none(
                    row.get("episode_source_hit_at_10")
                ),
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
    source_metric_movement: dict[str, dict[str, list[str]]] = {
        metric: {key: [] for key in SOURCE_METRIC_MOVEMENT_KEYS}
        for metric in SOURCE_METRIC_KEYS
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
        baseline_metrics = _row_baseline_source_metrics(row)
        for metric in SOURCE_METRIC_KEYS:
            _append_source_metric_movement(
                source_metric_movement,
                metric,
                baseline_metrics.get(metric),
                _bool_or_none(row.get(metric)),
                case_id,
            )

    return {
        "total_cases": total_cases,
        "movement": movement,
        "failure_classes": failure_classes,
        "failure_boundaries": failure_boundaries,
        "source_metric_movement": source_metric_movement,
        "counts": {
            "movement": {key: len(value) for key, value in movement.items()},
            "failure_classes": {
                key: len(value) for key, value in failure_classes.items()
            },
            "failure_boundaries": {
                key: len(value) for key, value in failure_boundaries.items()
            },
            "source_metric_movement": {
                metric: {
                    key: len(value)
                    for key, value in metric_movement.items()
                }
                for metric, metric_movement in source_metric_movement.items()
            },
        },
        "source_hit_semantics": "final_projection_source_overlap",
        "diagnostic_note": (
            "Movement summarizes verdict changes. Failure boundaries come from "
            "case_diagnostics.evidence_handoff and do not infer retrieval "
            "localization from public source_hit. Source-metric movement uses "
            "comparison-report metrics; cases with missing baseline or current "
            "metric values are omitted from source-metric movement buckets."
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


def _row_baseline_source_metrics(row: dict[str, Any]) -> dict[str, bool | None]:
    diagnostics = row.get("case_diagnostics")
    metrics: object = None
    if isinstance(diagnostics, dict):
        metrics = diagnostics.get("baseline_source_metrics")
    if not isinstance(metrics, dict):
        metrics = row.get("baseline_source_metrics")
    if not isinstance(metrics, dict):
        return {}
    return {
        metric: _bool_or_none(metrics.get(metric))
        for metric in SOURCE_METRIC_KEYS
    }


def _append_source_metric_movement(
    groups: dict[str, dict[str, list[str]]],
    metric: str,
    baseline_value: bool | None,
    current_value: bool | None,
    case_id: str,
) -> None:
    if baseline_value is None or current_value is None:
        return
    if baseline_value is False and current_value is True:
        bucket = "improved"
    elif baseline_value is True and current_value is False:
        bucket = "regressed"
    elif baseline_value is True and current_value is True:
        bucket = "unchanged_hit"
    else:
        bucket = "unchanged_miss"
    _append_grouped(groups[metric], bucket, case_id)


def _append_grouped(groups: dict[str, list[str]], key: str, case_id: str) -> None:
    bucket = key or "unknown"
    groups.setdefault(bucket, [])
    if case_id not in groups[bucket]:
        groups[bucket].append(case_id)


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
