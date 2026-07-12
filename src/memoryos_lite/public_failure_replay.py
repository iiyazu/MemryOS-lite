"""Phase 9 public benchmark failure replay diagnostics.

This module is intentionally pure and report-derived. It does not run
retrieval, construct services, call an LLM, mutate settings, or write files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PHASE_ID = "phase-9"

FAILED_LOCOMO_PHASE8_CASE_IDS: tuple[str, ...] = (
    "conv-26_qa_003",
    "conv-26_qa_004",
    "conv-26_qa_006",
    "conv-26_qa_008",
    "conv-26_qa_011",
    "conv-26_qa_012",
    "conv-26_qa_016",
    "conv-26_qa_019",
    "conv-26_qa_020",
    "conv-26_qa_024",
    "conv-26_qa_025",
    "conv-26_qa_027",
    "conv-26_qa_033",
    "conv-26_qa_035",
    "conv-26_qa_036",
    "conv-26_qa_039",
    "conv-26_qa_041",
    "conv-26_qa_044",
    "conv-26_qa_048",
    "conv-26_qa_050",
)

JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS: tuple[str, ...] = ("conv-26_qa_015",)

REQUIRED_PATH_LEVEL_CLASSES: set[str] = {
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
}

_SOURCE_HIT_SEMANTICS = "final_projection_source_overlap_not_retrieval_localization"
_CONTEXT_BUNDLE_NOTE_PREFIX = "context bundle: "


def build_replay_row(row: Mapping[str, Any], *, context_bundle: str) -> dict[str, Any]:
    """Build one deterministic phase-9 replay row from a public report row."""

    diagnostics = _mapping(row.get("case_diagnostics"))
    expected_source_ids = _strings(row.get("expected_source_ids"))
    expected_session_ids = _strings(row.get("expected_session_ids"))
    indexed_source_ids = _strings(row.get("indexed_source_ids"))
    retrieved_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="retrieved_evidence_ids",
        row_keys=(
            "retrieval_candidate_source_ids",
            "episode_candidate_message_ids",
            "planned_evidence_message_ids",
        ),
    )
    selected_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="selected_context_ids",
        row_keys=("item_hit_source_ids",),
    )
    rendered_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="rendered_evidence_ids",
        row_keys=("source_ids",),
    )
    answer_evidence_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="answer_evidence_ids",
        row_keys=(),
    )
    cited_source_ids = _strings(diagnostics.get("cited_source_ids"))
    unsupported_citation_ids = _strings(diagnostics.get("unsupported_citation_ids"))
    retrieved_overlap_ids = _overlap(expected_source_ids, retrieved_ids)
    selected_overlap_ids = _overlap(expected_source_ids, selected_ids)
    rendered_overlap_ids = _overlap(expected_source_ids, rendered_ids)
    answer_evidence_overlap_ids = _overlap(expected_source_ids, answer_evidence_ids)
    evidence_handoff = _mapping(diagnostics.get("evidence_handoff"))
    failure_boundary = _first_string(evidence_handoff.get("failure_boundary"), default="unknown")
    path_class = classify_path_level_failure(row, diagnostics)
    report_class = _first_string(
        diagnostics.get("failure_class"),
        row.get("failure_class"),
        default="unknown",
    )
    judge_verdict = _first_string(row.get("verdict"), diagnostics.get("verdict"), default="unknown")
    judge_reasoning = _first_string(
        row.get("reasoning"),
        diagnostics.get("reasoning"),
        default="",
    )
    source_metrics = {
        "expected_source_count": len(expected_source_ids),
        "indexed_source_count": len(indexed_source_ids),
        "retrieved_source_count": len(retrieved_ids),
        "selected_source_count": len(selected_ids),
        "rendered_source_count": len(rendered_ids),
        "retrieved_overlap_count": len(retrieved_overlap_ids),
        "selected_overlap_count": len(selected_overlap_ids),
        "rendered_overlap_count": len(rendered_overlap_ids),
        "retrieved_source_hit": bool(retrieved_overlap_ids),
        "selected_source_hit": bool(selected_overlap_ids),
        "rendered_source_hit": bool(rendered_overlap_ids),
        "retrieval_session_hit": bool(
            _overlap(expected_session_ids, _strings(row.get("retrieval_candidate_session_ids")))
        ),
        "final_source_hit": row.get("source_hit"),
        "source_hit_at_k": row.get("source_hit_at_k"),
        "source_hit_semantics": _SOURCE_HIT_SEMANTICS,
    }
    judge_metrics = {
        "judge_verdict": judge_verdict,
        "judge_status": _first_string(
            diagnostics.get("judge_status"),
            row.get("judge_status"),
            default="unknown",
        ),
        "answer_support_status": _first_string(
            diagnostics.get("answer_support_status"),
            row.get("answer_support_status"),
            default="unknown",
        ),
        "citation_contract_status": _first_string(
            diagnostics.get("citation_contract_status"),
            default="unknown",
        ),
        "unsupported_citation_count": len(unsupported_citation_ids),
        "explicit_no_evidence_refusal": bool(diagnostics.get("explicit_no_evidence_refusal")),
    }

    notes = _diagnostic_notes(
        row=row,
        diagnostics=diagnostics,
        path_class=path_class,
        expected_source_ids=expected_source_ids,
        expected_session_ids=expected_session_ids,
        retrieved_overlap_ids=retrieved_overlap_ids,
        selected_overlap_ids=selected_overlap_ids,
        rendered_overlap_ids=rendered_overlap_ids,
        context_bundle=context_bundle,
    )

    return {
        "phase": PHASE_ID,
        "case_id": _first_string(row.get("case_id"), default=""),
        "benchmark": _first_string(row.get("benchmark"), default="unknown"),
        "baseline": _first_string(row.get("baseline"), default="unknown"),
        "question": _first_string(row.get("question"), default=""),
        "expected_source_ids": expected_source_ids,
        "expected_session_ids": expected_session_ids,
        "indexed_source_status": _indexed_source_status(
            row,
            expected_source_ids,
            indexed_source_ids,
        ),
        "indexed_source_ids": indexed_source_ids,
        "retrieved_ids": retrieved_ids,
        "retrieved_overlap_ids": retrieved_overlap_ids,
        "retrieval_candidate_session_ids": _strings(row.get("retrieval_candidate_session_ids")),
        "selected_ids": selected_ids,
        "selected_overlap_ids": selected_overlap_ids,
        "rendered_ids": rendered_ids,
        "rendered_overlap_ids": rendered_overlap_ids,
        "answer_evidence_ids": answer_evidence_ids,
        "answer_evidence_overlap_ids": answer_evidence_overlap_ids,
        "evidence_handoff": dict(evidence_handoff),
        "failure_boundary": failure_boundary,
        "answer_output": _first_string(row.get("answer"), default=""),
        "cited_source_ids": cited_source_ids,
        "unsupported_citation_ids": unsupported_citation_ids,
        "citation_contract_status": judge_metrics["citation_contract_status"],
        "answer_support_status": judge_metrics["answer_support_status"],
        "explicit_no_evidence_refusal": judge_metrics["explicit_no_evidence_refusal"],
        "judge_verdict": judge_verdict,
        "judge_reasoning": judge_reasoning,
        "movement_status": _first_string(
            diagnostics.get("movement_status"),
            row.get("movement_status"),
            default="unknown",
        ),
        "report_level_failure_class": report_class,
        "path_level_failure_class": path_class,
        "source_metrics": source_metrics,
        "judge_metrics": judge_metrics,
        "source_hit_semantics": _SOURCE_HIT_SEMANTICS,
        "diagnostic_notes": notes,
        "context_bundle": context_bundle,
    }


def classify_path_level_failure(row: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> str:
    """Classify one row by evidence path stage, conservatively."""

    case_id = _first_string(row.get("case_id"), default="")
    if case_id in JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS:
        return "judge_questionable"

    expected_source_ids = _strings(row.get("expected_source_ids"))
    expected_session_ids = _strings(row.get("expected_session_ids"))
    retrieved_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="retrieved_evidence_ids",
        row_keys=(
            "retrieval_candidate_source_ids",
            "episode_candidate_message_ids",
            "planned_evidence_message_ids",
        ),
    )
    selected_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="selected_context_ids",
        row_keys=("item_hit_source_ids",),
    )
    rendered_ids = _candidate_ids(
        diagnostics,
        row,
        diagnostic_key="rendered_evidence_ids",
        row_keys=("source_ids",),
    )
    retrieval_sessions = _strings(row.get("retrieval_candidate_session_ids"))

    if not expected_source_ids:
        return "diagnostic_gap"
    if _first_string(diagnostics.get("judge_status"), row.get("judge_status")) == (
        "judge_questionable"
    ):
        return "judge_questionable"

    retrieved_overlap = _overlap(expected_source_ids, retrieved_ids)
    selected_overlap = _overlap(expected_source_ids, selected_ids)
    rendered_overlap = _overlap(expected_source_ids, rendered_ids)
    if not retrieved_overlap:
        if expected_session_ids and retrieval_sessions:
            if not _overlap(expected_session_ids, retrieval_sessions):
                return "session_localization_miss"
        return "retrieval_miss"
    if not selected_overlap:
        return "evidence_retrieved_not_selected"
    if not rendered_overlap:
        return "evidence_selected_not_rendered"

    citation_status = _first_string(diagnostics.get("citation_contract_status"), default="")
    answer = _first_string(row.get("answer"), default="")
    reasoning = _first_string(row.get("reasoning"), diagnostics.get("reasoning"), default="")
    if citation_status == "unsupported_citation":
        return "unsupported_citation"
    if _is_refusal(answer) and rendered_overlap:
        return "refusal_despite_evidence"
    question = _first_string(row.get("question"), default="")
    if _looks_temporal(reasoning) or _looks_temporal(question):
        return "temporal_date_miss"
    if _looks_speaker_entity(reasoning):
        return "speaker_entity_confusion"
    if _first_string(row.get("verdict"), diagnostics.get("verdict")) == "fail":
        return "evidence_rendered_answer_fails"
    return "diagnostic_gap"


def build_case_matrix(
    rows: Iterable[Mapping[str, Any]],
    *,
    context_bundle: str,
) -> list[dict[str, Any]]:
    """Build replay rows for the 20 phase-8 failures plus tracked risk rows."""

    wanted = set(FAILED_LOCOMO_PHASE8_CASE_IDS) | set(JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS)
    matrix = [
        build_replay_row(row, context_bundle=context_bundle)
        for row in rows
        if _first_string(row.get("case_id"), default="") in wanted
    ]
    order = {
        case_id: index
        for index, case_id in enumerate(
            (*FAILED_LOCOMO_PHASE8_CASE_IDS, *JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS)
        )
    }
    return sorted(matrix, key=lambda replay: order.get(str(replay["case_id"]), 999))


def validate_phase9_case_coverage(matrix: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return fail-closed validation errors for the phase-9 replay matrix."""

    errors: list[str] = []
    by_case_id = {_first_string(row.get("case_id"), default=""): row for row in matrix}
    failed_ids = set(FAILED_LOCOMO_PHASE8_CASE_IDS)
    risk_ids = set(JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS)
    missing = sorted(failed_ids - set(by_case_id))
    if missing:
        errors.append(f"missing failed cases: {', '.join(missing)}")
    extra_failed = sorted(risk_ids & failed_ids)
    if extra_failed:
        errors.append(f"risk cases included in failure constants: {', '.join(extra_failed)}")
    for case_id in FAILED_LOCOMO_PHASE8_CASE_IDS:
        row = by_case_id.get(case_id)
        if row is None:
            continue
        if row.get("judge_verdict") != "fail":
            errors.append(f"{case_id} is not a failed judge case")
        if row.get("path_level_failure_class") not in REQUIRED_PATH_LEVEL_CLASSES:
            errors.append(f"{case_id} has unsupported path class")
        if row.get("phase") != PHASE_ID:
            errors.append(f"{case_id} is missing phase binding")
        if not row.get("context_bundle"):
            errors.append(f"{case_id} is missing context bundle citation")
        if "source_metrics" not in row or "judge_metrics" not in row:
            errors.append(f"{case_id} does not separate source and judge metrics")
    for case_id in JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS:
        row = by_case_id.get(case_id)
        if row is None:
            errors.append(f"missing judge/source-support risk case: {case_id}")
            continue
        if row.get("judge_verdict") == "fail":
            errors.append(f"{case_id} risk case is incorrectly counted as failed")
        if row.get("path_level_failure_class") != "judge_questionable":
            errors.append(f"{case_id} risk case is not marked judge_questionable")
        if row.get("phase") != PHASE_ID:
            errors.append(f"{case_id} risk case is missing phase binding")
    return errors


def _diagnostic_notes(
    *,
    row: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    path_class: str,
    expected_source_ids: list[str],
    expected_session_ids: list[str],
    retrieved_overlap_ids: list[str],
    selected_overlap_ids: list[str],
    rendered_overlap_ids: list[str],
    context_bundle: str,
) -> list[str]:
    notes = [_CONTEXT_BUNDLE_NOTE_PREFIX + context_bundle]
    report_notes = diagnostics.get("diagnostic_notes")
    if isinstance(report_notes, list):
        notes.extend(str(note) for note in report_notes if str(note).strip())
    if not expected_source_ids:
        notes.append("diagnostic_gap: missing expected source ids in report row")
    if not expected_session_ids:
        notes.append("diagnostic_gap: missing expected session ids in report row")
    if path_class == "diagnostic_gap":
        notes.append("diagnostic_gap")
        notes.append("diagnostic_gap: row lacks enough evidence path fields for narrower class")
    if path_class == "session_localization_miss":
        notes.append("expected sessions absent from retrieval candidate sessions")
    elif path_class == "retrieval_miss":
        notes.append("expected sources absent from retrieved evidence ids")
    elif path_class == "evidence_retrieved_not_selected":
        notes.append("expected sources retrieved but absent from selected ids")
    elif path_class == "evidence_selected_not_rendered":
        notes.append("expected sources selected but absent from rendered ids")
    elif path_class == "judge_questionable":
        notes.append("tracked separately as judge/source-support risk, not a failed case")
    if retrieved_overlap_ids and selected_overlap_ids and rendered_overlap_ids:
        notes.append("expected evidence reached rendered context; answer/judge failure is separate")
    if _first_string(row.get("case_id"), default="") in JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS:
        notes.append("risk case is excluded from phase-9 failed-case count")
    return _dedupe(notes)


def _indexed_source_status(
    row: Mapping[str, Any],
    expected_source_ids: list[str],
    indexed_source_ids: list[str],
) -> str:
    if not expected_source_ids:
        return "diagnostic_gap"
    if row.get("source_not_indexed") is False:
        return "indexed"
    overlap = set(expected_source_ids) & set(indexed_source_ids)
    if overlap == set(expected_source_ids):
        return "indexed"
    if overlap:
        return "partially_indexed"
    if indexed_source_ids:
        return "not_indexed"
    return "diagnostic_gap"


def _candidate_ids(
    diagnostics: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    diagnostic_key: str,
    row_keys: Sequence[str],
) -> list[str]:
    ids = _strings(diagnostics.get(diagnostic_key))
    for key in row_keys:
        ids.extend(_strings(row.get(key)))
    return _dedupe(ids)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
        return _dedupe(result)
    return []


def _first_string(*values: Any, default: str = "") -> str:
    for value in values:
        if isinstance(value, str):
            return value
    return default


def _overlap(expected: Sequence[str], candidates: Sequence[str]) -> list[str]:
    candidate_set = set(candidates)
    return [item for item in expected if item in candidate_set]


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _looks_temporal(text: str) -> bool:
    normalized = text.lower()
    markers = (
        "date",
        "day",
        "sunday",
        "saturday",
        "year",
        "month",
        "before",
        "after",
        "when",
        "time",
    )
    return any(marker in normalized for marker in markers)


def _looks_speaker_entity(text: str) -> bool:
    normalized = text.lower()
    markers = (
        "wrong person",
        "different person",
        "speaker",
        "caroline",
        "melanie",
        "entity",
    )
    return any(marker in normalized for marker in markers)


def _is_refusal(answer: str) -> bool:
    normalized = answer.lower()
    markers = (
        "insufficient evidence",
        "insufficient retrieved evidence",
        "not enough evidence",
        "no evidence",
        "cannot answer",
        "can't answer",
        "unable to answer",
    )
    return any(marker in normalized for marker in markers)
