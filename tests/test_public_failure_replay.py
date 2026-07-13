from __future__ import annotations

import json
from pathlib import Path

from memoryos_lite.public_failure_replay import (
    FAILED_LOCOMO_PHASE8_CASE_IDS,
    JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS,
    REQUIRED_PATH_LEVEL_CLASSES,
    build_case_matrix,
    build_replay_row,
    classify_path_level_failure,
    validate_phase9_case_coverage,
)

REPORT_PATH = Path(__file__).parent / "fixtures/public_failure_replay/phase8_cases.json"
CONTEXT_BUNDLE = "tests/fixtures/public_failure_replay/phase9_context_bundle.md"

REQUIRED_REPLAY_FIELDS = {
    "phase",
    "case_id",
    "benchmark",
    "baseline",
    "question",
    "expected_source_ids",
    "expected_session_ids",
    "indexed_source_status",
    "indexed_source_ids",
    "retrieved_ids",
    "retrieved_overlap_ids",
    "retrieval_candidate_session_ids",
    "selected_ids",
    "selected_overlap_ids",
    "rendered_ids",
    "rendered_overlap_ids",
    "answer_evidence_ids",
    "answer_evidence_overlap_ids",
    "evidence_handoff",
    "failure_boundary",
    "answer_output",
    "cited_source_ids",
    "unsupported_citation_ids",
    "citation_contract_status",
    "answer_support_status",
    "explicit_no_evidence_refusal",
    "judge_verdict",
    "judge_reasoning",
    "movement_status",
    "report_level_failure_class",
    "path_level_failure_class",
    "source_metrics",
    "judge_metrics",
    "source_hit_semantics",
    "diagnostic_notes",
    "context_bundle",
}


def _rows_by_case_id() -> dict[str, dict[str, object]]:
    rows = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    return {str(row["case_id"]): row for row in rows}


def test_real_phase8_failed_row_builds_complete_replay_row() -> None:
    row = _rows_by_case_id()["conv-26_qa_003"]

    replay = build_replay_row(row, context_bundle=CONTEXT_BUNDLE)

    assert REQUIRED_REPLAY_FIELDS <= set(replay)
    assert replay["phase"] == "phase-9"
    assert replay["case_id"] == "conv-26_qa_003"
    assert replay["context_bundle"] == CONTEXT_BUNDLE
    assert replay["report_level_failure_class"] == "retrieval_miss"
    assert replay["path_level_failure_class"] == "session_localization_miss"
    assert replay["indexed_source_status"] == "indexed"
    assert replay["expected_source_ids"]
    assert replay["retrieved_ids"]
    assert replay["diagnostic_notes"]


def test_required_path_classes_are_distinct_from_report_level_classes() -> None:
    assert {
        "retrieval_miss",
        "session_localization_miss",
        "temporal_date_miss",
        "speaker_entity_confusion",
        "evidence_retrieved_not_selected",
        "evidence_selected_not_rendered",
        "evidence_rendered_answer_fails",
        "unsupported_citation",
        "refusal_despite_evidence",
        "judge_questionable",
        "diagnostic_gap",
    } <= REQUIRED_PATH_LEVEL_CLASSES
    assert "session_localization_miss" in REQUIRED_PATH_LEVEL_CLASSES
    assert "session_localization_miss" != "retrieval_miss"


def test_replay_row_separates_source_metrics_from_judge_metrics() -> None:
    row = _rows_by_case_id()["conv-26_qa_006"]

    replay = build_replay_row(row, context_bundle=CONTEXT_BUNDLE)

    assert replay["path_level_failure_class"] == "temporal_date_miss"
    assert set(replay["source_metrics"]) >= {
        "expected_source_count",
        "retrieved_source_hit",
        "selected_source_hit",
        "rendered_source_hit",
        "source_hit_semantics",
    }
    assert set(replay["judge_metrics"]) >= {
        "judge_verdict",
        "judge_status",
        "answer_support_status",
        "citation_contract_status",
    }
    assert "judge_verdict" not in replay["source_metrics"]
    assert "retrieved_source_hit" not in replay["judge_metrics"]


def test_phase9_case_matrix_covers_20_failures_and_tracks_risk_case_separately() -> None:
    rows = list(_rows_by_case_id().values())

    matrix = build_case_matrix(rows, context_bundle=CONTEXT_BUNDLE)
    failures = [row for row in matrix if row["case_id"] in FAILED_LOCOMO_PHASE8_CASE_IDS]
    risks = [row for row in matrix if row["case_id"] in JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS]

    assert validate_phase9_case_coverage(matrix) == []
    assert len(FAILED_LOCOMO_PHASE8_CASE_IDS) == 20
    assert len(failures) == 20
    assert {row["case_id"] for row in failures} == set(FAILED_LOCOMO_PHASE8_CASE_IDS)
    assert {row["phase"] for row in failures} == {"phase-9"}
    assert {row["judge_verdict"] for row in failures} == {"fail"}
    assert [row["case_id"] for row in risks] == ["conv-26_qa_015"]
    assert risks[0]["path_level_failure_class"] == "judge_questionable"
    assert risks[0]["case_id"] not in FAILED_LOCOMO_PHASE8_CASE_IDS


def test_unclassifiable_missing_evidence_is_explicit_diagnostic_gap() -> None:
    row = {
        "case_id": "synthetic_gap",
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "verdict": "fail",
        "case_diagnostics": {},
    }

    replay = build_replay_row(row, context_bundle=CONTEXT_BUNDLE)

    assert classify_path_level_failure(row, {}) == "diagnostic_gap"
    assert replay["path_level_failure_class"] == "diagnostic_gap"
    assert "diagnostic_gap" in replay["diagnostic_notes"]
