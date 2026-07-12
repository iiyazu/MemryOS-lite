from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from memoryos_lite.v3_contracts import (
    AgentStepResult,
    KernelTraceEvent,
    SourceRef,
    ToolExecutionRequest,
)

MaintenanceDecisionAction = Literal[
    "noop",
    "propose",
    "defer",
    "reject",
    "require_approval",
    "execute_after_approval",
]
MaintenanceSignalType = Literal[
    "recall_to_archive_candidate",
    "core_promotion_candidate",
    "dropped_high_value_evidence",
    "unsupported_memory_candidate",
]
MaintenanceProposalType = Literal[
    "archive_write",
    "archive_attach",
    "core_promotion_request",
]
ContextFeedbackType = Literal[
    "dropped_high_value_evidence",
    "layer_budget_pressure",
    "recall_archive_quality_issue",
    "recall_budget_pressure",
]


class MaintenanceSignal(BaseModel):
    signal_id: str
    signal_type: MaintenanceSignalType
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class MaintenanceDecision(BaseModel):
    action: MaintenanceDecisionAction
    reason: str
    signal_id: str | None = None


class MaintenanceMemoryProposal(BaseModel):
    proposal_type: MaintenanceProposalType
    tool_request: ToolExecutionRequest
    signal_id: str

    @model_validator(mode="after")
    def require_source_refs_or_approval(self) -> MaintenanceMemoryProposal:
        if not self.tool_request.source_refs and not self.tool_request.approval_id:
            raise ValueError("maintenance memory proposals require source_refs or approval_id")
        return self


class MaintenanceContextFeedback(BaseModel):
    feedback_type: ContextFeedbackType
    suggested_action: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class KernelMaintenanceAnalysisResult(BaseModel):
    signals: list[MaintenanceSignal] = Field(default_factory=list)
    decisions: list[MaintenanceDecision] = Field(default_factory=list)
    memory_proposals: list[MaintenanceMemoryProposal] = Field(default_factory=list)
    context_feedback: list[MaintenanceContextFeedback] = Field(default_factory=list)
    trace: list[KernelTraceEvent] = Field(default_factory=list)


class KernelMaintenanceExecutionResult(BaseModel):
    analysis: KernelMaintenanceAnalysisResult
    agent_step: AgentStepResult | None = None
    persisted_feedback_trace_count: int = 0
    skipped_duplicate_proposal_count: int = 0
    skipped_duplicate_policy_candidate_count: int = 0
    trace: list[KernelTraceEvent] = Field(default_factory=list)


__all__ = [
    "ContextFeedbackType",
    "KernelMaintenanceAnalysisResult",
    "KernelMaintenanceExecutionResult",
    "MaintenanceContextFeedback",
    "MaintenanceDecision",
    "MaintenanceDecisionAction",
    "MaintenanceMemoryProposal",
    "MaintenanceProposalType",
    "MaintenanceSignal",
    "MaintenanceSignalType",
]
