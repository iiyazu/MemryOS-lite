"""Tests for diagnostic_report.py — failure mode classification and report generation."""
from __future__ import annotations

import pytest

from memoryos_lite.diagnostic_report import classify_failure, generate_report
from memoryos_lite.public_benchmarks import PublicBenchmarkResult


def _make_result(**overrides) -> PublicBenchmarkResult:
    defaults = {
        "benchmark": "longmemeval",
        "baseline": "memoryos_lite",
        "case_id": "test_001",
        "question": "test?",
        "expected_answer": "answer",
        "answer": "answer",
        "answer_mode": "projected",
        "verdict": "pass",
        "reasoning": "",
        "expected_present": [],
        "expected_missing": [],
        "source_ids": [],
        "expected_source_ids": [],
        "source_overlap_ids": [],
        "missing_source_ids": [],
        "retrieval_candidate_top_k": None,
        "retrieval_candidate_unit": None,
        "retrieval_candidate_page_ids": [],
        "retrieval_candidate_source_ids": [],
        "retrieval_candidate_session_ids": [],
        "page_candidate_top_k": None,
        "page_candidate_page_ids": [],
        "page_candidate_source_ids": [],
        "page_candidate_session_ids": [],
        "source_recall": None,
        "source_hit": None,
        "source_hit_at_k": None,
        "page_source_overlap_at_k": None,
        "expected_session_ids": [],
        "source_session_ids": [],
        "session_overlap_ids": [],
        "missing_session_ids": [],
        "session_recall": None,
        "session_hit": None,
        "session_hit_at_k": None,
        "page_session_overlap_at_k": None,
        "context_tokens": 0,
        "page_count": 0,
        "loaded_pages": 0,
        "dropped_pages": 0,
        "page_type_counts": {},
        "page_source_counts": [],
        "page_summary_token_counts": [],
        "retrieved_page_ids": [],
        "dropped_page_reasons": {},
        "dropped_relevant_page_ids": [],
        "dropped_relevant_page_count": 0,
        "superseded_source_recovered": 0,
        "candidate_budget_dropped": 0,
        "active_overlap_not_top5": 0,
        "item_source_overlap_at_k": None,
        "item_promoted_evidence_count": 0,
        "item_evidence_budget_dropped": 0,
        "source_not_indexed": False,
        "item_hit_item_ids": [],
        "item_hit_source_ids": [],
        "latency_ms": 0,
        "question_type": None,
    }
    defaults.update(overrides)
    return PublicBenchmarkResult(**defaults)


# --- classify_failure tests ---


def test_classify_failure_pass():
    result = _make_result(source_hit=True)
    assert classify_failure(result) == "pass"


def test_classify_failure_source_not_indexed():
    result = _make_result(source_hit=False, source_not_indexed=True)
    assert classify_failure(result) == "source_not_indexed"


def test_classify_failure_budget_dropped_candidate():
    result = _make_result(source_hit=False, candidate_budget_dropped=2)
    assert classify_failure(result) == "promoted_but_budget_dropped"


def test_classify_failure_budget_dropped_item():
    result = _make_result(source_hit=False, item_evidence_budget_dropped=1)
    assert classify_failure(result) == "promoted_but_budget_dropped"


def test_classify_failure_item_hit_not_promoted():
    result = _make_result(source_hit=False, item_source_overlap_at_k=True)
    assert classify_failure(result) == "item_hit_but_not_promoted"


def test_classify_failure_neither_found():
    result = _make_result(
        source_hit=False,
        page_source_overlap_at_k=False,
        item_source_overlap_at_k=False,
    )
    assert classify_failure(result) == "item_source_overlap_at_k_zero"


def test_classify_failure_page_found_item_not():
    result = _make_result(
        source_hit=False,
        page_source_overlap_at_k=True,
        item_source_overlap_at_k=False,
    )
    assert classify_failure(result) == "page_source_overlap_at_k_zero"


def test_classify_failure_evidence_filtered():
    # Both overlaps are None (unknown) and no other condition matches — catch-all
    result = _make_result(
        source_hit=False,
        source_not_indexed=False,
        candidate_budget_dropped=0,
        item_evidence_budget_dropped=0,
        item_source_overlap_at_k=None,
        page_source_overlap_at_k=None,
    )
    assert classify_failure(result) == "evidence_filtered_out"


# --- generate_report tests ---


def test_generate_report_empty():
    report = generate_report([])
    assert report["total_cases"] == 0
    assert report["source_hit_rate"] == 0.0
    assert report["failure_breakdown"] == {}
    assert report["typical_failures"] == {}
    assert report["item_contribution"] == {}


def test_generate_report_structure():
    results = [
        _make_result(case_id="c1", source_hit=True),
        _make_result(case_id="c2", source_hit=False, source_not_indexed=True),
        _make_result(case_id="c3", source_hit=False, candidate_budget_dropped=1),
    ]
    report = generate_report(results)
    assert report["total_cases"] == 3
    assert "source_hit_rate" in report
    assert "failure_breakdown" in report
    assert "typical_failures" in report
    assert "item_contribution" in report


def test_generate_report_hit_rate():
    results = [
        _make_result(case_id="c1", source_hit=True),
        _make_result(case_id="c2", source_hit=True),
        _make_result(case_id="c3", source_hit=False, source_not_indexed=True),
        _make_result(case_id="c4", source_hit=False, source_not_indexed=True),
    ]
    report = generate_report(results)
    assert report["source_hit_rate"] == pytest.approx(0.5)
    assert report["failure_breakdown"].get("pass") == 2
    assert report["failure_breakdown"].get("source_not_indexed") == 2


def test_generate_report_typical_failures_max_two():
    results = [
        _make_result(case_id=f"c{i}", source_hit=False, source_not_indexed=True)
        for i in range(5)
    ]
    report = generate_report(results)
    assert len(report["typical_failures"]["source_not_indexed"]) == 2


def test_generate_report_pass_not_in_typical_failures():
    results = [_make_result(case_id="c1", source_hit=True)]
    report = generate_report(results)
    assert "pass" not in report["typical_failures"]


def test_generate_report_item_contribution():
    results = [
        # item helped (item overlap + source hit)
        _make_result(case_id="c1", source_hit=True, item_source_overlap_at_k=True),
        # page only (page overlap + source hit, no item)
        _make_result(
            case_id="c2",
            source_hit=True,
            page_source_overlap_at_k=True,
            item_source_overlap_at_k=False,
        ),
        # failure
        _make_result(case_id="c3", source_hit=False, source_not_indexed=True),
    ]
    report = generate_report(results)
    contrib = report["item_contribution"]
    assert contrib["item_helped"] == 1
    assert contrib["page_only"] == 1
