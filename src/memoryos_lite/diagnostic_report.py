"""Failure mode classification and diagnostic report generation for Phase 2.5."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from memoryos_lite.public_benchmarks import PublicBenchmarkResult

FAILURE_MODES = [
    "pass",
    "source_not_indexed",
    "promoted_but_budget_dropped",
    "item_hit_but_not_promoted",
    "page_source_overlap_at_k_zero",
    "item_source_overlap_at_k_zero",
    "evidence_filtered_out",
]


def classify_failure(result: PublicBenchmarkResult) -> str:
    """Classify a single benchmark result into its primary failure mode.

    Priority order (most specific first):
    1. pass — source was found
    2. source_not_indexed — target not in any page/item source refs
    3. promoted_but_budget_dropped — evidence found but dropped due to budget
    4. item_hit_but_not_promoted — item found target but didn't promote to evidence
    5. page_source_overlap_at_k_zero — page didn't find target (but item might have)
    6. item_source_overlap_at_k_zero — neither page nor item found target
    7. evidence_filtered_out — catch-all (found somewhere but filtered)
    """
    if result.source_hit:
        return "pass"
    if result.source_not_indexed:
        return "source_not_indexed"
    if result.candidate_budget_dropped > 0 or result.item_evidence_budget_dropped > 0:
        return "promoted_but_budget_dropped"
    if result.item_source_overlap_at_k and not result.source_hit:
        return "item_hit_but_not_promoted"
    if result.page_source_overlap_at_k is False and result.item_source_overlap_at_k is False:
        return "item_source_overlap_at_k_zero"
    if result.page_source_overlap_at_k is True and result.item_source_overlap_at_k is False:
        return "page_source_overlap_at_k_zero"
    return "evidence_filtered_out"


def generate_report(results: list[PublicBenchmarkResult]) -> dict[str, Any]:
    """Generate diagnostic report from benchmark results."""
    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "source_hit_rate": 0.0,
            "failure_breakdown": {},
            "typical_failures": {},
            "item_contribution": {},
        }

    classifications: dict[str, list[str]] = defaultdict(list)
    for result in results:
        mode = classify_failure(result)
        classifications[mode].append(result.case_id)

    pass_count = len(classifications.get("pass", []))
    source_hit_rate = pass_count / total

    failure_breakdown = {mode: len(case_ids) for mode, case_ids in classifications.items()}

    # Typical failures: up to 2 example case_ids per mode
    typical_failures = {
        mode: case_ids[:2]
        for mode, case_ids in classifications.items()
        if mode != "pass"
    }

    # Item contribution: how many cases item retrieval helped
    item_helped = sum(1 for r in results if r.item_source_overlap_at_k and r.source_hit)
    page_only = sum(
        1 for r in results
        if r.page_source_overlap_at_k and r.source_hit and not r.item_source_overlap_at_k
    )

    return {
        "total_cases": total,
        "source_hit_rate": source_hit_rate,
        "failure_breakdown": failure_breakdown,
        "typical_failures": typical_failures,
        "item_contribution": {
            "item_helped": item_helped,
            "page_only": page_only,
            "neither": total - item_helped - page_only - (total - pass_count),
        },
    }


def load_results(report_path: Path) -> list[PublicBenchmarkResult]:
    """Load PublicBenchmarkResult list from a JSON report file."""
    data = json.loads(report_path.read_text(encoding="utf-8"))
    results = []
    fields = set(PublicBenchmarkResult.__dataclass_fields__)
    for item in data:
        kwargs = {k: v for k, v in item.items() if k in fields}
        results.append(PublicBenchmarkResult(**kwargs))
    return results
