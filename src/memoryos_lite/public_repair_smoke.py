from __future__ import annotations

import json
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from memoryos_lite.agent_tool_registry import executable_kernel_tool_names
from memoryos_lite.public_maintenance_planner import ModelVisiblePlannerInput
from memoryos_lite.v3_contracts import SourceRef, ToolExecutionRequest

FAILURE_CLASS_KEYS = (
    "retrieval_miss",
    "evidence_hit_answer_fail",
    "context_missing_evidence",
    "unsupported_answer",
    "judge_questionable",
    "source_miss_judge_pass",
)
CONTEXT_FAILURE_CLASS_ALIASES = (
    "evidence_retrieved_not_selected",
    "evidence_selected_not_rendered",
    "evidence_rendered_not_answer_evidence",
)
SOURCE_METRIC_KEYS = (
    "source_hit",
    "planned_evidence_source_hit_at_5",
    "episode_source_hit_at_10",
)
MOVEMENT_KEYS = (
    "fail_to_pass",
    "pass_to_fail",
    "unchanged_fail",
    "unchanged_pass",
)


class BaselineCoverage(TypedDict):
    valid: bool
    matched_case_ids: list[str]
    missing_baseline_case_ids: list[str]
    extra_baseline_case_ids: list[str]
    duplicate_baseline_case_ids: list[str]
    duplicate_repair_case_ids: list[str]


class ExecutableRepairProposal(BaseModel):
    executable: bool
    denial_reason: str | None = None
    tool_request: ToolExecutionRequest | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


def build_executable_repair_proposal(
    row: dict[str, Any],
    source_id_aliases: dict[str, str],
) -> ExecutableRepairProposal:
    proposal = row.get("maintenance_proposal")
    if not isinstance(proposal, dict):
        return _denied("missing maintenance proposal")

    tool_name = proposal.get("tool_name")
    if not isinstance(tool_name, str) or tool_name not in executable_kernel_tool_names():
        return _denied("unknown or unopened kernel tool")
    if proposal.get("execution_mode") != "proposal_only":
        return _denied("maintenance proposal is not proposal_only")
    if proposal.get("gold_fields_used") is not False:
        return _denied("gold fields were marked as used")

    arguments = proposal.get("arguments", {})
    if not isinstance(arguments, dict):
        return _denied("tool arguments must be an object")

    immediate_unsafe_reason = _contains_forbidden_payload(
        arguments,
        _immediate_forbidden_values(row),
    )
    if immediate_unsafe_reason:
        return _denied(immediate_unsafe_reason)

    forbidden_values = _forbidden_values(row)
    model_visible = _parse_model_visible(row.get("model_visible_planner_input"))
    if model_visible is None:
        return _denied("missing model-visible planner input")
    allowed_source_ids = _model_visible_source_ids(model_visible)

    source_refs_input = proposal.get("source_refs", [])
    if not isinstance(source_refs_input, list):
        return _denied("source_refs must be a list")

    rewritten_refs: list[SourceRef] = []
    for source_ref in source_refs_input:
        if not isinstance(source_ref, dict):
            return _denied("source_refs must contain objects")
        raw_source_id = source_ref.get("source_id")
        if not isinstance(raw_source_id, str) or not raw_source_id:
            return _denied("source_refs require source_id")
        if raw_source_id not in allowed_source_ids:
            return _denied("source ref is not model-visible")
        alias = source_id_aliases.get(raw_source_id)
        if not alias:
            return _denied("source ref must be rewritten through repair-store alias")
        ref_payload = dict(source_ref)
        ref_payload["source_id"] = alias
        rewritten_refs.append(SourceRef.model_validate(ref_payload))

    rewritten_arguments = _rewrite_aliases(arguments, source_id_aliases)
    request = ToolExecutionRequest(
        session_id="repair-smoke",
        tool_name=tool_name,
        arguments=rewritten_arguments,
        source_refs=rewritten_refs,
        candidate_reason="repair-smoke",
    )
    serialized_request = request.model_dump_json()
    request_unsafe_reason = _contains_forbidden_payload(
        serialized_request,
        forbidden_values,
    )
    if request_unsafe_reason:
        return _denied(request_unsafe_reason)

    return ExecutableRepairProposal(
        executable=True,
        tool_request=request,
        provenance={
            "source_ref_count": len(rewritten_refs),
            "tool_name": tool_name,
        },
    )


def _denied(reason: str) -> ExecutableRepairProposal:
    return ExecutableRepairProposal(
        executable=False,
        denial_reason=reason,
        tool_request=None,
    )


def _parse_model_visible(value: Any) -> ModelVisiblePlannerInput | None:
    if isinstance(value, ModelVisiblePlannerInput):
        return value
    if isinstance(value, dict):
        return ModelVisiblePlannerInput.model_validate(value)
    return None


def _model_visible_source_ids(model_visible: ModelVisiblePlannerInput) -> set[str]:
    ids: list[str] = []
    ids.extend(model_visible.selected_context_ids)
    ids.extend(model_visible.final_context_trace_source_ids)
    ids.extend(model_visible.rendered_evidence_ids)
    ids.extend(model_visible.cited_source_ids)
    ids.extend(model_visible.unsupported_citation_ids)
    for item in model_visible.answer_evidence:
        evidence_id = item.get("evidence_id") or item.get("id")
        if isinstance(evidence_id, str):
            ids.append(evidence_id)
        source_ids = item.get("source_ids")
        if isinstance(source_ids, str):
            ids.append(source_ids)
        elif isinstance(source_ids, list):
            ids.extend(source_id for source_id in source_ids if isinstance(source_id, str))
    return {source_id for source_id in ids if source_id}


def _forbidden_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    sidecar = row.get("eval_gold_sidecar")
    if isinstance(sidecar, dict):
        for key in (
            "case_id",
            "expected_answer",
            "verdict",
            "judge_status",
            "failure_class",
            "movement_status",
        ):
            value = sidecar.get(key)
            if isinstance(value, str):
                values.add(value)
        expected_source_ids = sidecar.get("expected_source_ids")
        if isinstance(expected_source_ids, list):
            values.update(value for value in expected_source_ids if isinstance(value, str))
    case_id = row.get("case_id")
    if isinstance(case_id, str):
        values.add(case_id)
    return {value for value in values if value}


def _immediate_forbidden_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    sidecar = row.get("eval_gold_sidecar")
    if isinstance(sidecar, dict):
        for key in (
            "expected_answer",
            "verdict",
            "judge_status",
            "failure_class",
            "movement_status",
        ):
            value = sidecar.get(key)
            if isinstance(value, str):
                values.add(value)
    return {value for value in values if value}


def _contains_forbidden_payload(payload: Any, forbidden_values: set[str]) -> str | None:
    serialized = (
        payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, default=str)
    )
    for value in sorted(forbidden_values, key=len, reverse=True):
        if value and value in serialized:
            return "forbidden gold or benchmark value in executable payload"
    return None


def _rewrite_aliases(value: Any, source_id_aliases: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_aliases(item, source_id_aliases) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_aliases(item, source_id_aliases) for item in value]
    if isinstance(value, str):
        return _rewrite_source_id_mentions(value, source_id_aliases)
    return value


def _rewrite_source_id_mentions(value: str, source_id_aliases: dict[str, str]) -> str:
    rewritten = value
    for source_id, alias in sorted(
        source_id_aliases.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        rewritten = rewritten.replace(source_id, alias)
    return rewritten


def archive_artifacts_from_kernel_trace(
    trace_events: list[dict[str, Any]],
) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for event in trace_events:
        if event.get("event_type") != "tool_verified":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("tool_name") != "archive_write":
            continue
        verification = payload.get("verification")
        if not isinstance(verification, dict):
            continue
        archive_id = verification.get("archive_id")
        passage_id = verification.get("passage_id")
        if not isinstance(archive_id, str) or not isinstance(passage_id, str):
            continue
        key = (archive_id, passage_id)
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(
            {
                "archive_id": archive_id,
                "passage_id": passage_id,
                "verification_status": str(verification.get("status") or "unknown"),
                "session_attachment_found": bool(verification.get("session_attachment_found")),
                "eligible_for_session": bool(verification.get("eligible_for_session")),
            }
        )
    return artifacts


def build_repair_smoke_comparison_summary(
    baseline_rows: list[dict[str, Any]],
    repair_rows: list[dict[str, Any]],
    *,
    llm_answer: bool,
    llm_judge: bool,
    provider_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    gate_errors = _provider_errors(provider_errors, repair_rows)
    gate_status, gate_reason = _full_chain_gate_status(
        llm_answer=llm_answer,
        llm_judge=llm_judge,
        provider_errors=gate_errors,
    )
    baseline_coverage = _baseline_coverage(baseline_rows, repair_rows)
    if not baseline_coverage["valid"]:
        gate_status = "blocked_baseline_mismatch"
        gate_reason = _baseline_mismatch_reason(baseline_coverage)
    duplicate_baseline_case_ids = set(baseline_coverage["duplicate_baseline_case_ids"])
    duplicate_repair_case_ids = set(baseline_coverage["duplicate_repair_case_ids"])
    baseline_by_case = {
        case_id: row
        for row in baseline_rows
        if isinstance((case_id := row.get("case_id")), str)
        and case_id not in duplicate_baseline_case_ids
    }
    summary: dict[str, Any] = {
        "same_slice_repair_smoke_only": True,
        "answer_mode": "llm" if llm_answer and not gate_errors else "projected",
        "judge_mode": "llm" if llm_judge and not gate_errors else "heuristic",
        "llm_answer_requested": llm_answer,
        "llm_judge_requested": llm_judge,
        "full_chain_gate_status": gate_status,
        "full_chain_gate_reason": gate_reason,
        "promotion_gate_satisfied": False,
        "quality_gate_satisfied": False,
        "provider_errors": gate_errors,
        "baseline_coverage": baseline_coverage,
        "failure_classes": {key: [] for key in FAILURE_CLASS_KEYS},
        "source_metric_movement": {
            key: {"improved": [], "regressed": []} for key in SOURCE_METRIC_KEYS
        },
        "counts": {},
    }
    for key in MOVEMENT_KEYS:
        summary[key] = []

    for row in repair_rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str):
            continue
        normalized_failure_class = _normalized_failure_class(row)
        if normalized_failure_class is not None:
            _append_unique(
                summary["failure_classes"][normalized_failure_class],
                case_id,
            )
        if case_id in duplicate_repair_case_ids:
            continue
        baseline = baseline_by_case.get(case_id)
        if baseline is None:
            continue
        movement = _case_movement(_row_passed(baseline), _row_passed(row))
        if movement in MOVEMENT_KEYS:
            summary[movement].append(case_id)
        for metric in SOURCE_METRIC_KEYS:
            baseline_metric = _bool_or_none(baseline.get(metric))
            repair_metric = _bool_or_none(row.get(metric))
            if baseline_metric is False and repair_metric is True:
                summary["source_metric_movement"][metric]["improved"].append(case_id)
            elif baseline_metric is True and repair_metric is False:
                summary["source_metric_movement"][metric]["regressed"].append(case_id)

    summary["counts"] = {key: len(summary[key]) for key in MOVEMENT_KEYS} | {
        "failure_classes": {key: len(value) for key, value in summary["failure_classes"].items()},
        "source_metric_movement": {
            metric: {direction: len(cases) for direction, cases in movement.items()}
            for metric, movement in summary["source_metric_movement"].items()
        },
        "baseline_coverage": {
            "valid": baseline_coverage["valid"],
            "matched_case_ids": len(baseline_coverage["matched_case_ids"]),
            "missing_baseline_case_ids": len(baseline_coverage["missing_baseline_case_ids"]),
            "extra_baseline_case_ids": len(baseline_coverage["extra_baseline_case_ids"]),
            "duplicate_baseline_case_ids": len(baseline_coverage["duplicate_baseline_case_ids"]),
            "duplicate_repair_case_ids": len(baseline_coverage["duplicate_repair_case_ids"]),
        },
    }
    return summary


def _baseline_coverage(
    baseline_rows: list[dict[str, Any]],
    repair_rows: list[dict[str, Any]],
) -> BaselineCoverage:
    baseline_case_ids = _row_case_ids(baseline_rows)
    repair_case_ids = _row_case_ids(repair_rows)
    duplicate_baseline_case_ids = _duplicate_case_ids(baseline_case_ids)
    duplicate_repair_case_ids = _duplicate_case_ids(repair_case_ids)
    baseline_case_id_set = set(baseline_case_ids)
    repair_case_id_set = set(repair_case_ids)
    matched_case_ids = sorted(
        case_id
        for case_id in baseline_case_id_set & repair_case_id_set
        if case_id not in duplicate_baseline_case_ids and case_id not in duplicate_repair_case_ids
    )
    missing_baseline_case_ids = sorted(repair_case_id_set - baseline_case_id_set)
    extra_baseline_case_ids = sorted(baseline_case_id_set - repair_case_id_set)
    valid = not (
        missing_baseline_case_ids
        or extra_baseline_case_ids
        or duplicate_baseline_case_ids
        or duplicate_repair_case_ids
    )
    return {
        "valid": valid,
        "matched_case_ids": matched_case_ids,
        "missing_baseline_case_ids": missing_baseline_case_ids,
        "extra_baseline_case_ids": extra_baseline_case_ids,
        "duplicate_baseline_case_ids": sorted(duplicate_baseline_case_ids),
        "duplicate_repair_case_ids": sorted(duplicate_repair_case_ids),
    }


def _row_case_ids(rows: list[dict[str, Any]]) -> list[str]:
    return [case_id for row in rows if isinstance((case_id := row.get("case_id")), str)]


def _duplicate_case_ids(case_ids: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for case_id in case_ids:
        if case_id in seen:
            duplicates.add(case_id)
        seen.add(case_id)
    return duplicates


def _baseline_mismatch_reason(baseline_coverage: BaselineCoverage) -> str:
    parts: list[str] = []
    for key in (
        "missing_baseline_case_ids",
        "extra_baseline_case_ids",
        "duplicate_baseline_case_ids",
        "duplicate_repair_case_ids",
    ):
        value = baseline_coverage.get(key)
        if isinstance(value, list) and value:
            parts.append(f"{key}={value}")
    detail = "; ".join(parts) if parts else "case coverage mismatch"
    return (
        "Repair smoke baseline report must contain exactly one row for every "
        f"current fixed-slice case; {detail}."
    )


def _normalized_failure_class(row: dict[str, Any]) -> str | None:
    raw_failure_class = row.get("failure_class")
    failure_class = raw_failure_class if isinstance(raw_failure_class, str) else ""
    if failure_class == "judge_questionable":
        return "judge_questionable"
    if _source_miss_judge_pass(row, failure_class):
        return "source_miss_judge_pass"
    if failure_class in CONTEXT_FAILURE_CLASS_ALIASES:
        return "context_missing_evidence"
    if failure_class in FAILURE_CLASS_KEYS:
        return failure_class
    return None


def _source_miss_judge_pass(row: dict[str, Any], failure_class: str) -> bool:
    if not _row_passed(row):
        return False
    if failure_class == "retrieval_miss":
        return True
    return any(_bool_or_none(row.get(metric)) is False for metric in SOURCE_METRIC_KEYS)


def _append_unique(values: list[str], case_id: str) -> None:
    if case_id not in values:
        values.append(case_id)


def _full_chain_gate_status(
    *,
    llm_answer: bool,
    llm_judge: bool,
    provider_errors: list[dict[str, str]],
) -> tuple[str, str]:
    if provider_errors:
        return (
            "blocked_provider_unavailable",
            "Full-chain repair smoke was requested, but the configured LLM "
            "provider unavailable state blocked answer or judge execution.",
        )
    if not (llm_answer and llm_judge):
        return (
            "not_satisfied",
            "No-LLM or partial-LLM repair smoke is diagnostic only; it is not "
            "full-chain benchmark quality or promotion evidence.",
        )
    return (
        "not_satisfied",
        "Full-chain answer and judge were requested, but same-slice repair "
        "smoke remains diagnostic only and cannot satisfy a promotion gate.",
    )


def _provider_errors(
    explicit_errors: list[dict[str, str]] | None,
    repair_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for error in explicit_errors or []:
        explicit_stage = error.get("stage")
        message = error.get("error")
        if isinstance(explicit_stage, str) and isinstance(message, str):
            errors.append({"stage": explicit_stage, "error": message})

    for row in repair_rows:
        reasoning = row.get("reasoning")
        if not isinstance(reasoning, str):
            continue
        diagnostic_stage: str | None = None
        if reasoning.startswith("answer_error:"):
            diagnostic_stage = "answer"
        elif reasoning.startswith("judge_error:"):
            diagnostic_stage = "judge"
        if diagnostic_stage is None:
            continue
        error_payload = {"stage": diagnostic_stage, "error": reasoning}
        case_id = row.get("case_id")
        if isinstance(case_id, str):
            error_payload["case_id"] = case_id
        errors.append(error_payload)
    return errors


def _row_passed(row: dict[str, Any]) -> bool:
    pass_value = row.get("pass")
    if isinstance(pass_value, bool):
        return pass_value
    verdict = row.get("verdict")
    return verdict == "pass"


def _case_movement(baseline_passed: bool, repair_passed: bool) -> str:
    if not baseline_passed and repair_passed:
        return "fail_to_pass"
    if baseline_passed and not repair_passed:
        return "pass_to_fail"
    if baseline_passed and repair_passed:
        return "unchanged_pass"
    return "unchanged_fail"


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


__all__ = [
    "ExecutableRepairProposal",
    "archive_artifacts_from_kernel_trace",
    "build_repair_smoke_comparison_summary",
    "build_executable_repair_proposal",
]
