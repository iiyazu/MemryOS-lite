from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from memoryos_lite.v3_contracts import SourceRef, SourceType


class ModelVisiblePlannerInput(BaseModel):
    question: str
    rendered_answer: str
    selected_context_ids: list[str] = Field(default_factory=list)
    final_context_trace_source_ids: list[str] = Field(default_factory=list)
    rendered_evidence_ids: list[str] = Field(default_factory=list)
    answer_evidence: list[dict[str, Any]] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    unsupported_citation_ids: list[str] = Field(default_factory=list)
    citation_contract_status: str = "unknown"
    archival_eligibility: dict[str, Any] = Field(default_factory=dict)
    component_drop_counts: dict[str, int] = Field(default_factory=dict)
    kernel_trace_events: list[dict[str, Any]] = Field(default_factory=list)


class EvalGoldSidecar(BaseModel):
    case_id: str
    expected_answer: str
    expected_source_ids: list[str] = Field(default_factory=list)
    verdict: str
    judge_status: str
    failure_class: str
    movement_status: str


class MaintenanceProposal(BaseModel):
    proposal_type: Literal[
        "archive_write",
        "diagnostic_only_denial",
        "grounding_risk",
    ]
    execution_mode: Literal["proposal_only"] = "proposal_only"
    tool_name: Literal["archive_write"] | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    gold_fields_used: Literal[False] = False
    denial_reason: str | None = None


class MaintenanceArtifact(BaseModel):
    model_visible: ModelVisiblePlannerInput
    eval_sidecar: EvalGoldSidecar
    proposal: MaintenanceProposal


def build_maintenance_artifact(
    model_visible: ModelVisiblePlannerInput,
    eval_sidecar: EvalGoldSidecar,
) -> MaintenanceArtifact:
    source_ids = _model_visible_source_ids(model_visible)
    if not source_ids:
        proposal = MaintenanceProposal(
            proposal_type="diagnostic_only_denial",
            denial_reason="no model-visible evidence available for a maintenance proposal",
        )
    elif _has_grounding_risk(model_visible):
        proposal = MaintenanceProposal(
            proposal_type="grounding_risk",
            denial_reason="grounding risk requires non-executable diagnostic review",
        )
    else:
        proposal = MaintenanceProposal(
            proposal_type="archive_write",
            tool_name="archive_write",
            arguments={
                "content": model_visible.rendered_answer,
                "question": model_visible.question,
                "evidence_source_ids": source_ids,
                "citation_contract_status": model_visible.citation_contract_status,
            },
            source_refs=[
                SourceRef(source_type=SourceType.MESSAGE, source_id=source_id)
                for source_id in source_ids
            ],
        )
    return MaintenanceArtifact(
        model_visible=model_visible,
        eval_sidecar=eval_sidecar,
        proposal=proposal,
    )


def _has_grounding_risk(
    model_visible: ModelVisiblePlannerInput,
) -> bool:
    if model_visible.unsupported_citation_ids:
        return True
    if model_visible.citation_contract_status in {
        "missing_citation",
        "unsupported_citation",
    }:
        return True
    return False


def _model_visible_source_ids(model_visible: ModelVisiblePlannerInput) -> list[str]:
    if model_visible.citation_contract_status == "no_cited_evidence":
        return []
    ids: list[str] = []
    ids.extend(model_visible.cited_source_ids)
    ids.extend(model_visible.rendered_evidence_ids)
    ids.extend(model_visible.final_context_trace_source_ids)
    ids.extend(model_visible.selected_context_ids)
    for item in model_visible.answer_evidence:
        evidence_id = item.get("evidence_id") or item.get("id")
        if isinstance(evidence_id, str):
            ids.append(evidence_id)
        source_ids = item.get("source_ids")
        if isinstance(source_ids, str):
            ids.append(source_ids)
        elif isinstance(source_ids, list):
            ids.extend(source_id for source_id in source_ids if isinstance(source_id, str))
    return _dedupe(ids)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
