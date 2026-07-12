from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from memoryos_lite.schemas import Episode, MemoryItem, MemoryPage, Message, Role, new_id, utc_now


class SourceType(StrEnum):
    MESSAGE = "message"
    EPISODE = "episode"
    DOCUMENT = "document"
    PASSAGE = "passage"
    MEMORY = "memory"
    CORE_BLOCK = "core_block"
    TOOL_CALL = "tool_call"
    APPROVAL = "approval"
    MANUAL = "manual"


class SourceSpan(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> SourceSpan:
        if self.start > self.end:
            raise ValueError("SourceSpan.start must be less than or equal to end")
        return self


class IdentityScope(BaseModel):
    user_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    archive_id: str | None = None
    tags: list[str] = Field(default_factory=list)


def ensure_persisted_identity_scope(scope: IdentityScope | None) -> IdentityScope | None:
    if scope is None:
        return None
    if not any(
        [
            scope.user_id,
            scope.agent_id,
            scope.run_id,
            scope.session_id,
            scope.project_id,
            scope.archive_id,
        ]
    ):
        raise ValueError("persisted identity scopes require at least one identity boundary")
    return scope


class SourceRef(BaseModel):
    source_type: SourceType
    source_id: str = Field(min_length=1)
    session_id: str | None = None
    identity_scope: IdentityScope | None = None
    span: SourceSpan | None = None
    quote: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    approval_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_manual_approval(self) -> SourceRef:
        if self.source_type == SourceType.MANUAL and not self.approval_id:
            raise ValueError("manual source refs require approval_id")
        return self


MemoryType = Literal[
    "recall",
    "archival_document",
    "archival_passage",
    "archival_memory",
    "core_block",
]
HistoryOperation = Literal[
    "add",
    "update",
    "replace",
    "delete",
    "promote",
    "demote",
    "attach",
    "detach",
]


class MemoryHistoryEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("hist"))
    memory_id: str = Field(min_length=1)
    memory_type: MemoryType
    operation: HistoryOperation
    source_refs: list[SourceRef] = Field(default_factory=list)
    actor: Literal["system", "user", "agent", "tool"]
    reason: str = Field(min_length=1)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_replace_before_state(self) -> MemoryHistoryEvent:
        if self.operation != "delete" and self.after is None:
            raise ValueError("non-delete memory history events require after")
        if self.operation == "replace" and self.before is None:
            raise ValueError("replace memory history events require before")
        return self


class DiagnosticEvent(BaseModel):
    layer: Literal["message_log", "recall", "archival", "core", "composer", "kernel"]
    event_type: str = Field(min_length=1)
    item_id: str | None = None
    reason_code: str = Field(min_length=1)
    score: float | None = None
    included: bool = False
    dropped: bool = False
    budget_tokens: int | None = Field(default=None, ge=0)
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LayerBudgetDecision(BaseModel):
    layer: Literal["task", "core", "recall", "archival", "recent", "fallback"]
    requested_tokens: int = Field(ge=0)
    allocated_tokens: int = Field(ge=0)
    used_tokens: int = Field(ge=0)
    dropped_item_ids: list[str] = Field(default_factory=list)
    reason_code: str = Field(min_length=1)


class MessageLogEntry(BaseModel):
    id: str
    session_id: str
    role: Role
    content: str
    created_at: datetime
    token_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)


class RecallMemoryEntry(BaseModel):
    id: str
    session_id: str
    message_id: str
    role: Role
    text: str
    index_text: str
    position: int
    source_message_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    temporal_scope: dict[str, Any] = Field(default_factory=dict)
    rank_features: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ArchivalDocument(BaseModel):
    id: str
    archive_id: str | None = None
    title: str
    text: str
    version: int = 1
    source_id: str | None = None
    file_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    producer: Literal["explicit_document", "message", "sleep", "retrieval"] | str = (
        "explicit_document"
    )
    legacy_page_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ArchivalChunk(BaseModel):
    id: str
    document_id: str
    archive_id: str | None = None
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_range(self) -> ArchivalChunk:
        if self.start > self.end:
            raise ValueError("ArchivalChunk.start must be less than or equal to end")
        return self


class ArchivalPassage(BaseModel):
    id: str
    document_id: str | None = None
    chunk_id: str | None = None
    archive_id: str | None = None
    text: str
    citation: SourceSpan | None = None
    source_id: str | None = None
    file_id: str | None = None
    scope: IdentityScope | None = None
    tags: list[str] = Field(default_factory=list)
    score: float | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    legacy_item_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ArchivalMemory(BaseModel):
    id: str
    archive_id: str | None = None
    memory_type: Literal["fact", "preference", "event", "procedure", "knowledge"]
    content: str
    identity_scope: IdentityScope | None = None
    source_id: str | None = None
    file_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    history: list[MemoryHistoryEvent] = Field(default_factory=list)
    entity_links: list[str] = Field(default_factory=list)
    legacy_item_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None


class ArchiveAttachment(BaseModel):
    id: str
    archive_id: str
    scope_type: Literal["agent", "project", "source", "user", "run", "session"]
    scope_id: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ArchiveEligibilityScope(BaseModel):
    session_id: str
    identity_scope: IdentityScope | None = None
    source_ids: list[str] = Field(default_factory=list)
    archive_ids: list[str] = Field(default_factory=list)


class ArchiveEligibilityResult(BaseModel):
    scope: ArchiveEligibilityScope
    eligible_archive_ids: list[str] = Field(default_factory=list)
    eligible_passages: list[ArchivalPassage] = Field(default_factory=list)
    scope_excluded_passages: list[ArchivalPassage] = Field(default_factory=list)
    scope_excluded_passage_ids: list[str] = Field(default_factory=list)
    no_match_passage_ids: list[str] = Field(default_factory=list)
    selected_passage_ids: list[str] = Field(default_factory=list)
    selected_source_refs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def eligible_passage_count(self) -> int:
        return len(self.eligible_passages)

    @property
    def selected_passage_count(self) -> int:
        return len(self.selected_passage_ids)

    @property
    def archival_scope_excluded(self) -> int:
        return len(self.scope_excluded_passage_ids)

    @property
    def archival_no_match(self) -> int:
        return len(self.no_match_passage_ids)

    def diagnostics_payload(self) -> dict[str, Any]:
        return {
            "eligible_archive_ids": list(self.eligible_archive_ids),
            "eligible_passage_count": self.eligible_passage_count,
            "selected_passage_ids": list(self.selected_passage_ids),
            "selected_passage_count": self.selected_passage_count,
            "selected_source_refs": list(self.selected_source_refs),
            "scope_excluded_passage_ids": list(self.scope_excluded_passage_ids),
            "archival_scope_excluded": self.archival_scope_excluded,
            "no_match_passage_ids": list(self.no_match_passage_ids),
            "archival_no_match": self.archival_no_match,
            "no_attached_archive": not self.eligible_archive_ids and not self.scope.source_ids,
            "archival_no_attached_archive": (
                not self.eligible_archive_ids and not self.scope.source_ids
            ),
        }


class CoreMemoryBlock(BaseModel):
    id: str
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    value: str = ""
    limit_tokens: int = Field(gt=0)
    read_only: bool = False
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None
    deleted_by_event_id: str | None = None


ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]


class ApprovalState(BaseModel):
    id: str
    session_id: str
    tool_name: str
    requested_action: dict[str, Any]
    status: ApprovalStatus
    requested_by: str
    approved_by: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_resolution(self) -> ApprovalState:
        if self.status == "approved" and (not self.approved_by or self.resolved_at is None):
            raise ValueError("approved approval states require approved_by and resolved_at")
        if self.status in {"rejected", "expired", "cancelled"} and self.resolved_at is None:
            raise ValueError("resolved non-approved approval states require resolved_at")
        return self


class CoreMemoryUpdate(BaseModel):
    block_id: str = Field(min_length=1)
    operation: Literal["append", "replace", "update", "delete"]
    content: str
    old: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    approval_state: ApprovalState | None = None

    @model_validator(mode="after")
    def require_source_or_approval(self) -> CoreMemoryUpdate:
        if not self.source_refs:
            if self.approval_state is None or self.approval_state.status != "approved":
                raise ValueError(
                    "core memory updates require source_refs or approved approval_state"
                )
        if self.operation == "replace" and not self.old:
            raise ValueError("replace core memory updates require old")
        return self


MemoryWriteSource = Literal[
    "explicit_instruction",
    "message_extraction",
    "sleep_consolidation",
]
PromotionStatus = Literal["pending", "approved", "applied", "rejected", "deferred"]


class PromotionCandidate(BaseModel):
    id: str = Field(default_factory=lambda: new_id("pcand"))
    source_layer: Literal["recall", "archival", "document", "message_log"]
    target_layer: Literal["archival", "core"]
    operation: Literal["add", "update", "delete", "promote"]
    content: str = Field(min_length=1)
    source_refs: list[SourceRef] = Field(default_factory=list)
    identity_scope: IdentityScope | None = None
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    status: PromotionStatus = "pending"
    write_source: MemoryWriteSource
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


ContextPolicyCandidateStatus = Literal["pending", "applied", "rejected", "deferred"]
ContextPolicyType = Literal["context_quality"]
ContextPolicyFeedbackType = Literal[
    "dropped_high_value_evidence",
    "layer_budget_pressure",
    "recall_archive_quality_issue",
    "recall_budget_pressure",
]


class ContextPolicyCandidate(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cpcand"))
    session_id: str = Field(min_length=1)
    policy_type: ContextPolicyType = "context_quality"
    feedback_type: ContextPolicyFeedbackType
    suggested_action: str = Field(min_length=1)
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: ContextPolicyCandidateStatus = "pending"
    fingerprint: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_source_refs(self) -> ContextPolicyCandidate:
        if not self.source_refs:
            raise ValueError("context policy candidates require source_refs")
        return self


class ContextLayerItem(BaseModel):
    layer: Literal["task", "core", "recall", "archival", "recent", "fallback"]
    item_id: str
    text: str
    estimated_tokens: int = Field(ge=0)
    source_refs: list[SourceRef] = Field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextComposerRequest(BaseModel):
    session_id: str
    task: str
    budget: int = Field(gt=0)
    retrieval_query: str | None = None
    identity_scope: IdentityScope | None = None
    source_ids: list[str] = Field(default_factory=list)
    archive_ids: list[str] = Field(default_factory=list)
    include_layers: list[str] = Field(default_factory=list)


class ContextPackageV3(BaseModel):
    session_id: str
    task: str
    items: list[ContextLayerItem] = Field(default_factory=list)
    budget_decisions: list[LayerBudgetDecision] = Field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextComposer(Protocol):
    def build(self, request: ContextComposerRequest) -> ContextPackageV3: ...


def message_to_log_entry(message: Message) -> MessageLogEntry:
    return MessageLogEntry(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        token_count=message.token_count,
        metadata=message.metadata,
        source_refs=[
            SourceRef(
                source_type=SourceType.MESSAGE,
                source_id=message.id,
                session_id=message.session_id,
            )
        ],
    )


def episode_to_recall_entry(episode: Episode) -> RecallMemoryEntry:
    return RecallMemoryEntry(
        id=episode.id,
        session_id=episode.session_id,
        message_id=episode.message_id,
        role=episode.role,
        text=episode.text,
        index_text=episode.index_text,
        position=episode.position,
        source_message_ids=episode.source_message_ids,
        source_refs=[
            SourceRef(
                source_type=SourceType.MESSAGE,
                source_id=source_id,
                session_id=episode.session_id,
            )
            for source_id in episode.source_message_ids
        ],
        temporal_scope={
            key: value
            for key, value in {
                "benchmark_session_id": episode.benchmark_session_id,
                "benchmark_date": episode.benchmark_date,
            }.items()
            if value is not None
        },
        created_at=episode.created_at,
    )


def page_to_archival_document(page: MemoryPage) -> ArchivalDocument:
    return ArchivalDocument(
        id=f"adoc_{page.id}",
        title=page.title,
        text=page.summary,
        version=page.version,
        source_refs=[
            SourceRef(
                source_type=SourceType.MESSAGE,
                source_id=source_id,
                session_id=page.session_id,
            )
            for source_id in page.source_message_ids
        ],
        legacy_page_id=page.id,
        metadata={"legacy_page_type": page.page_type.value},
        created_at=page.created_at,
    )


def item_to_archival_memory(item: MemoryItem) -> ArchivalMemory:
    type_map: dict[str, Literal["fact", "preference", "event", "procedure", "knowledge"]] = {
        "profile": "fact",
        "event": "event",
        "knowledge": "knowledge",
        "behavior": "procedure",
    }
    return ArchivalMemory(
        id=f"amem_{item.id}",
        memory_type=type_map.get(item.item_type.value, "knowledge"),
        content=item.content,
        source_refs=[
            SourceRef(
                source_type=SourceType.MESSAGE,
                source_id=source_id,
                session_id=item.session_id,
            )
            for source_id in item.source_message_ids
        ],
        legacy_item_id=item.id,
        created_at=item.created_at,
    )


def item_to_archival_passage(
    item: MemoryItem,
    document_id: str | None = None,
) -> ArchivalPassage:
    source_id = item.source_message_ids[0] if item.source_message_ids else None
    return ArchivalPassage(
        id=f"apsg_{item.id}",
        document_id=document_id,
        text=item.content,
        source_id=source_id,
        source_refs=[
            SourceRef(
                source_type=SourceType.MESSAGE,
                source_id=source_id,
                session_id=item.session_id,
            )
            for source_id in item.source_message_ids
        ],
        legacy_item_id=item.id,
        metadata={"legacy_page_id": item.page_id, "legacy_item_type": item.item_type.value},
    )


V3_KEEP_TABLES: set[str] = {
    "sessions",
    "messages",
    "episodes",
    "memory_pages",
    "memory_items",
    "memory_patches",
    "trace_events",
    "alembic_version",
}

V3_FUTURE_TABLES: set[str] = {
    "archival_documents",
    "archival_chunks",
    "archival_passages",
    "archival_memories",
    "archival_memory_history",
    "archive_attachments",
    "core_memory_blocks",
    "core_memory_history",
    "promotion_candidates",
    "context_policy_candidates",
    "tool_policy_rules",
    "approval_states",
    "kernel_traces",
}

V3_NO_NEW_TARGETS: set[str] = {"MemoryPage", "MemoryItem"}

REQUIRED_V3_ADAPTERS: dict[str, str] = {
    "Message": "MessageLogEntry adapter",
    "Episode": "RecallMemoryEntry adapter over episodes table",
    "MemoryPage": "ArchivalDocument migration input",
    "MemoryItem": "ArchivalMemory or ArchivalPassage adapter",
    "ContextPackage": "ContextPackageV3 compatibility payload",
    "agent_graph": "Agentic kernel request/result adapter",
}


ToolPolicyEffect = Literal["allow", "deny", "require_approval"]
ToolSelectionOrigin = Literal["deterministic", "llm", "fallback"]


class ToolPolicyRule(BaseModel):
    id: str
    tool_name: str
    scope: IdentityScope | None = None
    effect: ToolPolicyEffect
    reason: str = Field(min_length=1)
    priority: int = 0
    source_refs: list[SourceRef] = Field(default_factory=list)


class ToolPolicyDecision(BaseModel):
    tool_name: str
    effect: ToolPolicyEffect
    matched_rule_ids: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    reason: str = Field(min_length=1)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def forbid_implicit_allow(self) -> ToolPolicyDecision:
        if self.effect == "allow" and not self.matched_rule_ids:
            raise ValueError("allow decisions require an explicit matched rule")
        if self.effect == "require_approval" and not self.requires_approval:
            raise ValueError("require_approval decisions must set requires_approval")
        return self


class ToolCandidate(BaseModel):
    tool_call_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    source_refs: list[SourceRef] = Field(default_factory=list)
    approval_id: str | None = None
    candidate_reason: str = Field(min_length=1)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ToolSelectionChoice(BaseModel):
    tool_call_id: str | None = None
    selection_origin: ToolSelectionOrigin
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_noop_reason(self) -> ToolSelectionChoice:
        if self.tool_call_id is None and not self.reason.strip():
            raise ValueError("no-op selections require a reason")
        return self


class KernelTraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ktrace"))
    step_id: str
    session_id: str
    sequence: int = Field(gt=0)
    event_type: str = Field(min_length=1)
    payload: dict[str, Any]
    source_refs: list[SourceRef] = Field(default_factory=list)
    approval_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentStepRequest(BaseModel):
    session_id: str
    input_messages: list[MessageLogEntry] = Field(default_factory=list)
    context: ContextPackageV3
    identity_scope: IdentityScope | None = None


class AgentStepResult(BaseModel):
    session_id: str
    step_id: str
    messages: list[MessageLogEntry] = Field(default_factory=list)
    trace: list[KernelTraceEvent] = Field(default_factory=list)
    continuation: str


class ToolExecutionRequest(BaseModel):
    session_id: str
    tool_name: str
    arguments: dict[str, Any]
    source_refs: list[SourceRef] = Field(default_factory=list)
    approval_id: str | None = None
    tool_call_id: str | None = None
    selection_origin: ToolSelectionOrigin | None = None
    candidate_reason: str | None = None


class ToolExecutionResult(BaseModel):
    tool_name: str
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)


class ContinuationDecision(BaseModel):
    action: Literal["continue", "stop", "pause", "compact", "escalate"]
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStepRunner(Protocol):
    def run_step(self, request: AgentStepRequest) -> AgentStepResult: ...


class ToolPolicyEngine(Protocol):
    def decide(self, request: ToolExecutionRequest) -> ToolPolicyDecision: ...


class ApprovalGate(Protocol):
    def request_or_resume(self, request: ToolExecutionRequest) -> ApprovalState: ...


class ToolExecutionManager(Protocol):
    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult: ...


class ContinuationController(Protocol):
    def decide(self, result: AgentStepResult) -> ContinuationDecision: ...


__all__ = [
    "AgentStepRequest",
    "AgentStepResult",
    "AgentStepRunner",
    "ApprovalGate",
    "ApprovalState",
    "ArchiveAttachment",
    "ArchivalChunk",
    "ArchivalDocument",
    "ArchivalMemory",
    "ArchivalPassage",
    "ContextComposer",
    "ContextComposerRequest",
    "ContextLayerItem",
    "ContextPackageV3",
    "ContinuationController",
    "ContinuationDecision",
    "ContextPolicyCandidate",
    "ContextPolicyCandidateStatus",
    "ContextPolicyFeedbackType",
    "ContextPolicyType",
    "CoreMemoryBlock",
    "CoreMemoryUpdate",
    "DiagnosticEvent",
    "IdentityScope",
    "KernelTraceEvent",
    "LayerBudgetDecision",
    "MemoryWriteSource",
    "MemoryHistoryEvent",
    "MessageLogEntry",
    "PromotionCandidate",
    "PromotionStatus",
    "REQUIRED_V3_ADAPTERS",
    "RecallMemoryEntry",
    "SourceRef",
    "SourceSpan",
    "ToolExecutionManager",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolCandidate",
    "ToolPolicyDecision",
    "ToolPolicyEngine",
    "ToolPolicyRule",
    "ToolSelectionChoice",
    "ToolSelectionOrigin",
    "V3_FUTURE_TABLES",
    "V3_KEEP_TABLES",
    "V3_NO_NEW_TARGETS",
    "ensure_persisted_identity_scope",
    "episode_to_recall_entry",
    "item_to_archival_memory",
    "item_to_archival_passage",
    "message_to_log_entry",
    "page_to_archival_document",
]
