from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from memoryos_lite.schemas import Episode, MemoryItem, MemoryPage, Message, Role, utc_now


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


ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]


class ContextLayerItem(BaseModel):
    layer: Literal["task", "core", "page", "recall", "archival", "recent", "fallback"]
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
}


__all__ = [
    "ArchiveAttachment",
    "ArchivalChunk",
    "ArchivalDocument",
    "ArchivalPassage",
    "ContextComposer",
    "ContextComposerRequest",
    "ContextLayerItem",
    "ContextPackageV3",
    "DiagnosticEvent",
    "IdentityScope",
    "LayerBudgetDecision",
    "MessageLogEntry",
    "REQUIRED_V3_ADAPTERS",
    "RecallMemoryEntry",
    "SourceRef",
    "SourceSpan",
    "V3_FUTURE_TABLES",
    "V3_KEEP_TABLES",
    "V3_NO_NEW_TARGETS",
    "ensure_persisted_identity_scope",
    "episode_to_recall_entry",
    "item_to_archival_passage",
    "message_to_log_entry",
    "page_to_archival_document",
]
