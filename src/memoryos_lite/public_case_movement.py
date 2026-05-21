from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


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
    if baseline == "pass" and current == "fail":
        return "pass_to_fail"
    if baseline in {"fail", "error"} and current == "pass":
        return "fail_to_pass"
    if baseline == "pass" and current == "pass":
        return "unchanged_pass"
    if baseline in {"fail", "error"} and current != "pass":
        return "unchanged_fail"
    return "unchanged_fail"


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
