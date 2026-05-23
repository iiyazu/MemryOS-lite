from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from memoryos_lite.agent_answer_eval import evaluate_agent_answer
from memoryos_lite.public_case_movement import movement_status


def build_case_diagnostics(
    *,
    benchmark: str,
    baseline: str,
    case_id: str,
    memory_arch: str | None,
    answer: str,
    answer_mode: str,
    verdict: str,
    reasoning: str,
    expected_source_ids: list[str],
    retrieval_candidate_source_ids: list[str],
    episode_candidate_message_ids: list[str],
    planned_evidence_message_ids: list[str],
    source_ids: list[str],
    v3_context: dict[str, object],
    v3_diagnostics: list[dict[str, object]],
    kernel_trace_events: list[dict[str, Any]],
    answer_evidence_ids: list[str] | None = None,
    answer_evidence: list[dict[str, object]] | None = None,
    baseline_verdict: str | None = None,
    movement_baseline_source: str | None = None,
) -> dict[str, object]:
    expected_ids = _dedupe(expected_source_ids)
    retrieved_ids = _dedupe(
        [
            *retrieval_candidate_source_ids,
            *episode_candidate_message_ids,
            *planned_evidence_message_ids,
        ]
    )
    selected_ids = _selected_context_ids(
        memory_arch=memory_arch,
        v3_context=v3_context,
        v3_diagnostics=v3_diagnostics,
        fallback_ids=retrieved_ids,
    )
    final_context_trace_source_ids = _final_context_trace_source_ids(v3_context)
    archival_eligibility = _archival_eligibility(v3_context)
    rendered_ids = _dedupe(source_ids)
    answer_evidence_id_list = _dedupe(
        rendered_ids if answer_evidence_ids is None else answer_evidence_ids
    )
    answer_eval = evaluate_agent_answer(answer, rendered_ids)
    handoff = _evidence_handoff(
        expected_ids=expected_ids,
        retrieved_ids=retrieved_ids,
        selected_ids=selected_ids,
        rendered_ids=rendered_ids,
        answer_evidence_ids=answer_evidence_id_list,
        cited_source_ids=answer_eval.cited_source_ids,
    )
    handoff_stage_status = handoff["stage_status"]

    retrieval_status = _overlap_status(expected_ids, retrieved_ids, "evidence_retrieved")
    selected_context_status = _overlap_status(expected_ids, selected_ids, "evidence_selected")
    rendered_context_status = _overlap_status(expected_ids, rendered_ids, "evidence_rendered")
    answer_support_status = _answer_support_status(
        answer_mode=answer_mode,
        verdict=verdict,
        rendered_has_expected=bool(set(expected_ids) & set(rendered_ids)),
        unsupported=answer_eval.unsupported_answer,
        unsupported_citation_ids=answer_eval.unsupported_citation_ids,
        cited_source_ids=answer_eval.cited_source_ids,
        citation_contract_status=answer_eval.citation_contract_status,
    )
    judge_status = _judge_status(verdict, reasoning)
    failure_class = _failure_class(
        verdict=verdict,
        retrieval_status=retrieval_status,
        selected_context_status=selected_context_status,
        rendered_context_status=rendered_context_status,
        answer_evidence_status=str(handoff_stage_status["answer_evidence"]),
        answer_support_status=answer_support_status,
        judge_status=judge_status,
    )
    movement = movement_status(baseline_verdict, verdict)
    notes: list[str] = []
    if baseline_verdict is None:
        notes.append(f"missing baseline comparison for {benchmark}/{baseline}/{case_id}")

    return {
        "benchmark": benchmark,
        "baseline": baseline,
        "case_id": case_id,
        "memory_arch": memory_arch,
        "answer_mode": answer_mode,
        "verdict": verdict,
        "reasoning": reasoning,
        "expected_source_ids": expected_ids,
        "retrieved_evidence_ids": retrieved_ids,
        "selected_context_ids": selected_ids,
        "selected_context_overlap_ids": sorted(set(expected_ids) & set(selected_ids)),
        "final_context_trace_source_ids": final_context_trace_source_ids,
        "rendered_evidence_ids": rendered_ids,
        "answer_evidence_ids": answer_evidence_id_list,
        "answer_evidence_overlap_ids": handoff["answer_evidence_overlap_ids"],
        "answer_evidence": list(answer_evidence or []),
        "cited_source_ids": answer_eval.cited_source_ids,
        "unsupported_citation_ids": answer_eval.unsupported_citation_ids,
        "missing_citation": answer_eval.missing_citation,
        "explicit_no_evidence_refusal": answer_eval.explicit_no_evidence_refusal,
        "citation_contract_status": answer_eval.citation_contract_status,
        "retrieval_status": retrieval_status,
        "selected_context_status": selected_context_status,
        "rendered_context_status": rendered_context_status,
        "answer_support_status": answer_support_status,
        "judge_status": judge_status,
        "failure_class": failure_class,
        "movement_status": movement,
        "baseline_verdict": baseline_verdict,
        "movement_baseline_source": movement_baseline_source,
        "kernel_trace_present": bool(kernel_trace_events),
        "archival_eligibility": archival_eligibility,
        "component_drop_counts": _v3_metadata_mapping(v3_context, "component_drop_counts"),
        "locomo_neighbor_diagnostics": _v3_metadata_list(
            v3_context,
            "locomo_neighbor_diagnostics",
        ),
        "source_hit_semantics": "final_projection_source_overlap",
        "evidence_handoff": handoff,
        "diagnostic_notes": notes,
    }


def _overlap_status(expected_ids: list[str], candidate_ids: list[str], hit_status: str) -> str:
    if not expected_ids:
        return "no_expected_evidence"
    return hit_status if set(expected_ids) & set(candidate_ids) else "evidence_missing"


def _evidence_handoff(
    *,
    expected_ids: list[str],
    retrieved_ids: list[str],
    selected_ids: list[str],
    rendered_ids: list[str],
    answer_evidence_ids: list[str],
    cited_source_ids: list[str],
) -> dict[str, Any]:
    expected = _dedupe(expected_ids)
    retrieved = _dedupe(retrieved_ids)
    selected = _dedupe(selected_ids)
    rendered = _dedupe(rendered_ids)
    answer_evidence = _dedupe(answer_evidence_ids)
    cited = _dedupe(cited_source_ids)
    retrieved_overlap = _overlap(expected, retrieved)
    selected_overlap = _overlap(expected, selected)
    rendered_overlap = _overlap(expected, rendered)
    answer_evidence_overlap = _overlap(expected, answer_evidence)
    cited_overlap = _overlap(expected, cited)
    stage_status = {
        "retrieval": _stage_status(expected, retrieved_overlap, "evidence_retrieved"),
        "selected": _stage_status(expected, selected_overlap, "evidence_selected"),
        "rendered": _stage_status(expected, rendered_overlap, "evidence_rendered"),
        "answer_evidence": _stage_status(
            expected,
            answer_evidence_overlap,
            "evidence_in_answer_evidence",
        ),
        "citation": _stage_status(expected, cited_overlap, "evidence_cited"),
    }
    return {
        "expected_source_ids": expected,
        "retrieved_evidence_ids": retrieved,
        "retrieved_overlap_ids": retrieved_overlap,
        "selected_context_ids": selected,
        "selected_context_overlap_ids": selected_overlap,
        "rendered_evidence_ids": rendered,
        "rendered_overlap_ids": rendered_overlap,
        "answer_evidence_ids": answer_evidence,
        "answer_evidence_overlap_ids": answer_evidence_overlap,
        "cited_source_ids": cited,
        "cited_overlap_ids": cited_overlap,
        "stage_status": stage_status,
        "failure_boundary": _failure_boundary(stage_status),
    }


def _stage_status(expected_ids: list[str], overlap_ids: list[str], hit_status: str) -> str:
    if not expected_ids:
        return "no_expected_evidence"
    return hit_status if overlap_ids else "evidence_missing"


def _failure_boundary(stage_status: dict[str, str]) -> str:
    if stage_status["retrieval"] == "no_expected_evidence":
        return "none"
    if stage_status["retrieval"] != "evidence_retrieved":
        return "retrieval_miss"
    if stage_status["selected"] != "evidence_selected":
        return "selected_drop"
    if stage_status["rendered"] != "evidence_rendered":
        return "render_drop"
    if stage_status["answer_evidence"] != "evidence_in_answer_evidence":
        return "answer_evidence_drop"
    if stage_status["citation"] != "evidence_cited":
        return "citation_drop"
    return "none"


def _answer_support_status(
    *,
    answer_mode: str,
    verdict: str,
    rendered_has_expected: bool,
    unsupported: bool,
    unsupported_citation_ids: list[str],
    cited_source_ids: list[str],
    citation_contract_status: str,
) -> str:
    if citation_contract_status in {"missing_citation", "unsupported_citation"}:
        return "unsupported_answer"
    if citation_contract_status == "no_evidence_refusal":
        return "no_evidence_refusal"
    if unsupported and (answer_mode == "llm" or unsupported_citation_ids):
        return "unsupported_answer"
    if verdict == "pass" and cited_source_ids and not unsupported:
        return "supported_cited_answer"
    if verdict == "pass" and not unsupported:
        return "supported_answer_missing_citation"
    if answer_mode == "projected" and rendered_has_expected and verdict == "fail":
        return "answer_failed_with_rendered_evidence"
    if unsupported:
        return "unsupported_answer"
    return "answer_not_supported_by_judge"


def _judge_status(verdict: str, reasoning: str) -> str:
    if not reasoning or reasoning == "exact substring match":
        return "not_run"
    normalized = reasoning.lower()
    if verdict == "error" or "judge_error:" in normalized:
        return "judge_questionable"
    return "judge_pass" if verdict == "pass" else "judge_fail"


def _failure_class(
    *,
    verdict: str,
    retrieval_status: str,
    selected_context_status: str,
    rendered_context_status: str,
    answer_evidence_status: str,
    answer_support_status: str,
    judge_status: str,
) -> str:
    if judge_status == "judge_questionable":
        return "judge_questionable"
    if retrieval_status != "evidence_retrieved":
        return "retrieval_miss"
    if (
        rendered_context_status == "evidence_rendered"
        and answer_support_status == "unsupported_answer"
    ):
        return "unsupported_answer"
    if selected_context_status != "evidence_selected":
        return "evidence_retrieved_not_selected"
    if rendered_context_status != "evidence_rendered":
        return "evidence_selected_not_rendered"
    if answer_evidence_status != "evidence_in_answer_evidence":
        return "evidence_rendered_not_answer_evidence"
    if answer_support_status == "unsupported_answer":
        return "unsupported_answer"
    if answer_support_status == "no_evidence_refusal":
        return "unsupported_answer"
    if verdict == "pass":
        return "supported_cited_answer"
    return "evidence_hit_answer_fail"


def _overlap(expected: list[str], candidates: list[str]) -> list[str]:
    candidate_set = set(candidates)
    return [item for item in expected if item in candidate_set]


def _selected_context_ids(
    *,
    memory_arch: str | None,
    v3_context: dict[str, object],
    v3_diagnostics: list[dict[str, object]],
    fallback_ids: list[str],
) -> list[str]:
    ids: list[str] = []
    for item in v3_diagnostics:
        if item.get("included") is not True:
            continue
        ids.extend(_strings_from_mapping(item, ("source_id", "source_message_id", "item_id")))
        for key in ("source_ids", "source_message_ids", "source_message_id_chain"):
            ids.extend(_strings_from_value(item.get(key)))
        ids.extend(_source_ids_from_source_refs(item.get("source_refs")))
    ids.extend(_ids_from_v3_context(v3_context))
    ids.extend(_final_context_trace_source_ids(v3_context))
    if memory_arch != "v3" and not ids:
        return fallback_ids
    return _dedupe(ids)


def _ids_from_v3_context(v3_context: dict[str, object]) -> list[str]:
    items = v3_context.get("items") if isinstance(v3_context, dict) else None
    if not isinstance(items, list):
        return []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ids.extend(_strings_from_mapping(item, ("item_id", "source_id", "source_message_id")))
        for key in ("source_ids", "source_message_ids"):
            ids.extend(_strings_from_value(item.get(key)))
        ids.extend(_source_ids_from_source_refs(item.get("source_refs")))
    return ids


def _final_context_trace_source_ids(v3_context: dict[str, object]) -> list[str]:
    metadata = v3_context.get("metadata") if isinstance(v3_context, dict) else None
    if not isinstance(metadata, dict):
        return []
    trace = metadata.get("final_context_trace")
    if not isinstance(trace, list):
        return []
    ids: list[str] = []
    for row in trace:
        if not isinstance(row, dict) or row.get("dropped") is True:
            continue
        ids.extend(_strings_from_value(row.get("source_ids")))
        ids.extend(_source_ids_from_source_refs(row.get("source_refs")))
    return _dedupe(ids)


def _v3_metadata_mapping(v3_context: dict[str, object], key: str) -> dict[str, object]:
    metadata = v3_context.get("metadata") if isinstance(v3_context, dict) else None
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get(key)
    return value if isinstance(value, dict) else {}


def _v3_metadata_list(v3_context: dict[str, object], key: str) -> list[object]:
    metadata = v3_context.get("metadata") if isinstance(v3_context, dict) else None
    if not isinstance(metadata, dict):
        return []
    value = metadata.get(key)
    return value if isinstance(value, list) else []


def _archival_eligibility(v3_context: dict[str, object]) -> dict[str, object]:
    if not isinstance(v3_context, dict):
        return {}
    metadata = v3_context.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    eligibility = metadata.get("archival_eligibility")
    return eligibility if isinstance(eligibility, dict) else {}


def _strings_from_mapping(item: dict[str, object], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = item.get(key)
        if isinstance(value, str):
            values.append(value)
    return values


def _strings_from_value(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _source_ids_from_source_refs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        if isinstance(source_id, str):
            ids.append(source_id)
    return ids


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
