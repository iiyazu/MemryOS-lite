from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RunTerminalStatus(StrEnum):
    RUNNING = "running"
    MERGED = "merged"
    TERMINATED = "terminated"
    BLOCKED_FOR_INPUT = "blocked_for_input"


class EvolutionProposalStatus(StrEnum):
    DRAFTING = "drafting"
    AWAITING_REVIEW = "awaiting_review"
    NARROWED_FOR_REDRAFT = "narrowed_for_redraft"
    APPROVED = "approved"
    REJECTED = "rejected"
    GUARDRAIL_BLOCKED = "guardrail_blocked"
    LANDED = "landed"


class EvolutionReviewKind(StrEnum):
    APPROVE = "approve"
    NARROW = "narrow"
    REJECT = "reject"


class EvolutionGuardrailAction(StrEnum):
    CONTINUE = "continue"
    HOLD = "hold"
    STOP = "stop"


class EvolutionBudgetStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"


class EvolutionDedupStatus(StrEnum):
    CONTINUED = "continued"
    DUPLICATE = "duplicate"


class ClarificationStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class EvolutionBudgetWindow(BaseModel):
    window_id: str
    origin_run_id: str
    started_at: str
    expires_at: str
    status: EvolutionBudgetStatus
    consumed_run_ids: list[str] = Field(default_factory=list)


class EvolutionDedupRecord(BaseModel):
    dedup_key: str
    signal_fingerprint: str
    source_lineage_key: str
    target_track_ids: list[str] = Field(default_factory=list)
    first_seen_at: str
    last_seen_at: str
    last_proposal_id: str
    status: EvolutionDedupStatus


class RunTerminalAggregation(BaseModel):
    aggregation_id: str
    run_id: str
    resolution_id: str
    graph_id: str
    status: RunTerminalStatus
    terminal: bool
    reason: str
    lane_counts: dict[str, int] = Field(default_factory=dict)
    lane_statuses: list[dict[str, Any]] = Field(default_factory=list)
    open_lineages: list[dict[str, Any]] = Field(default_factory=list)
    blocked_objects: list[dict[str, Any]] = Field(default_factory=list)
    final_action_holds: list[dict[str, Any]] = Field(default_factory=list)
    # verdict_lineage: per-lane list of {lane_id, verdict_id, decision, summary}
    # populated when a VerdictStore is wired into the aggregation.
    verdict_lineage: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class StructuredEvidenceBundle(BaseModel):
    bundle_id: str
    source_run_id: str
    source_resolution_id: str
    selection_policy_id: str
    selection_policy_version: str
    summary: str
    run_terminal_status: RunTerminalStatus
    verdict_refs: list[str] = Field(default_factory=list)
    gate_report_refs: list[str] = Field(default_factory=list)
    lineage_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    signal_refs: list[str] = Field(default_factory=list)
    primary_refs: list[str] = Field(default_factory=list)
    created_at: str


class NarrowingDecision(BaseModel):
    decision_id: str
    proposal_id: str
    source_review_session_id: str
    source_draft_version: int
    target_draft_version: int
    scope_constraints: list[str] = Field(default_factory=list)
    required_graph_changes: list[str] = Field(default_factory=list)
    required_evidence_focus: list[str] = Field(default_factory=list)
    rationale: str
    created_at: str


class EvolutionProposal(BaseModel):
    proposal_id: str
    source_run_id: str
    blueprint_set_id: str
    target_track_ids: list[str]
    status: EvolutionProposalStatus
    draft_version: int
    author_session_id: str
    scope_summary: str
    why_now: str
    evidence_bundle_id: str
    candidate_graph: dict[str, Any]
    review_status: str = "unreviewed"
    spawned_conversation_id: str | None = None
    spawned_resolution_id: str | None = None
    created_at: str


class EvolutionReviewDecision(BaseModel):
    decision_id: str
    proposal_id: str
    review_session_id: str
    decision: EvolutionReviewKind
    rationale: str
    narrowing_decision: NarrowingDecision | None = None
    created_at: str


class EvolutionGuardrailDecision(BaseModel):
    decision_id: str
    proposal_id: str
    action: EvolutionGuardrailAction
    rationale: str
    source_run_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    budget_window_id: str | None = None
    dedup_key: str | None = None
    terminal_aggregation_ref: str | None = None
    checks: dict[str, bool] = Field(default_factory=dict)
    created_at: str


class EvolutionConversation(BaseModel):
    conversation_id: str
    proposal_id: str
    source_run_id: str
    created_by: str
    created_at: str


class EvolutionLineageRecord(BaseModel):
    lineage_id: str
    source_run_id: str
    source_resolution_id: str | None = None
    evidence_bundle_id: str
    evolution_proposal_id: str
    review_decision_id: str
    guardrail_decision_id: str
    spawned_conversation_id: str
    spawned_proposal_id: str
    spawned_resolution_id: str
    spawned_graph_id: str
    blueprint_set_id: str
    target_track_ids: list[str] = Field(default_factory=list)
    terminal_aggregation_ref: str | None = None
    created_at: str


class ClarificationRequest(BaseModel):
    """Formal record of a blocked run that requires external information.

    Created when a run reaches ``blocked_for_input`` terminal status.
    The request captures exactly what is missing, who owns the answer, and
    how the system should resume once the information is provided.
    """

    request_id: str
    source_run_id: str
    aggregation_id: str
    # Structured list of blocked objects from the aggregation
    blocked_objects: list[dict[str, Any]] = Field(default_factory=list)
    # Human-readable summary of what is missing
    missing_input_summary: str
    # Who is expected to provide the information
    owner: str = "human"
    # How the system should resume once information is provided
    resume_path: str
    status: ClarificationStatus = ClarificationStatus.OPEN
    created_at: str
    resolved_at: str | None = None


class ClarificationResolution(BaseModel):
    """Provided information that resolves an open ClarificationRequest.

    When an operator or automated process supplies the missing information,
    a ClarificationResolution is created.  The controller uses it to spawn
    a follow-up resolution that re-enters the standard mainline.
    """

    resolution_id: str
    request_id: str
    source_run_id: str
    # The information provided to unblock the run
    provided_information: str
    # Optional structured key-value pairs for machine-readable context
    provided_context: dict[str, Any] = Field(default_factory=dict)
    # Who provided the information
    provided_by: str = "human"
    # Spawned conversation / resolution / graph after landing
    spawned_conversation_id: str | None = None
    spawned_resolution_id: str | None = None
    spawned_graph_id: str | None = None
    created_at: str
