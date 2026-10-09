import itertools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ID_SOURCE: ContextVar[Callable[[str], str] | None] = ContextVar("memoryos_id_source", default=None)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    source = _ID_SOURCE.get()
    if source is not None:
        return source(prefix)
    return f"{prefix}_{uuid4().hex[:12]}"


@contextmanager
def deterministic_ids(seed: str) -> Iterator[None]:
    """Make ``new_id`` reproducible inside the block (evaluation harnesses only).

    The n-th id created in the block is ``<prefix>_<sha256(seed:n)[:12]>``, so
    replaying the same operations yields the same ids and prompts that embed
    them (e.g. curator windows) hit an on-disk LLM cache across reruns.
    """

    counter = itertools.count()

    def source(prefix: str) -> str:
        digest = sha256(f"{seed}:{next(counter)}".encode()).hexdigest()
        return f"{prefix}_{digest[:12]}"

    token = _ID_SOURCE.set(source)
    try:
        yield
    finally:
        _ID_SOURCE.reset(token)


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class PageType(StrEnum):
    CORE_PROFILE = "core_profile_page"
    TASK_STATE = "task_state_page"
    DECISION = "decision_page"
    SOURCE_SUMMARY = "source_summary_page"
    TOOL_OBSERVATION = "tool_observation_page"


class PatchOperation(StrEnum):
    ADD = "add"
    REPLACE = "replace"
    DELETE = "delete"


class MessageCreate(BaseModel):
    role: Role
    content: str
    external_id: str | None = Field(default=None, min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(MessageCreate):
    id: str = Field(default_factory=lambda: new_id("msg"))
    session_id: str
    created_at: datetime = Field(default_factory=utc_now)
    token_count: int = 0


class Episode(BaseModel):
    id: str = Field(default_factory=lambda: new_id("epi"))
    session_id: str
    message_id: str
    role: Role
    text: str
    index_text: str
    benchmark_session_id: str | None = None
    benchmark_date: str | None = None
    position: int
    source_message_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ses"))
    title: str = "Untitled session"
    created_at: datetime = Field(default_factory=utc_now)


class MemoryPageDraft(BaseModel):
    page_type: PageType = PageType.SOURCE_SUMMARY
    title: str
    summary: str
    facts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    discarded_noise: list[str] = Field(default_factory=list)
    source_message_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.8


class MemoryPage(MemoryPageDraft):
    id: str = Field(default_factory=lambda: new_id("page"))
    session_id: str
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    superseded_by: str | None = None
    """ID of a newer page that has replaced this one via conflict detection.

    When set, retrieval and context-building skip this page by default.
    The field is advisory — raw ``list_pages`` still returns it so callers
    can audit the history of a session's memory.
    """


class MemoryItemType(StrEnum):
    PROFILE = "profile"
    EVENT = "event"
    KNOWLEDGE = "knowledge"
    BEHAVIOR = "behavior"


class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("item"))
    page_id: str
    session_id: str
    item_type: MemoryItemType = MemoryItemType.KNOWLEDGE
    content: str
    source_message_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class MemoryPatch(BaseModel):
    id: str = Field(default_factory=lambda: new_id("patch"))
    operation: PatchOperation
    target_page_id: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    reason: str
    source_refs: list[str] = Field(default_factory=list)
    verified: bool = False
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ContextPage(BaseModel):
    page_id: str
    title: str
    reason: str
    estimated_tokens: int


class ContextEvidence(BaseModel):
    message_id: str
    text: str
    role: Role
    reason: str
    estimated_tokens: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    page_id: str | None = None
    superseded: bool = False


class ContextPackage(BaseModel):
    session_id: str
    task: str
    task_tokens: int = 0
    task_truncated: bool = False
    pinned_core: list[str] = Field(default_factory=list)
    active_task_pages: list[ContextPage] = Field(default_factory=list)
    retrieved_evidence: list[ContextEvidence] = Field(default_factory=list)
    recent_messages: list[Message] = Field(default_factory=list)
    dropped_recent_messages: list[str] = Field(default_factory=list)
    retrieved_pages: list[ContextPage] = Field(default_factory=list)
    dropped_pages: list[ContextPage] = Field(default_factory=list)
    superseded_source_recovered: int = 0
    candidate_budget_dropped: int = 0
    active_overlap_not_top5: int = 0
    estimated_tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("trace"))
    session_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class BuildContextResponseProfile(StrEnum):
    FULL = "full"
    SOURCE_EVIDENCE_V1 = "source_evidence/v1"
    SOURCE_EVIDENCE_V2 = "source_evidence/v2"


class SupersededQuotePayload(BaseModel):
    """A verbatim quote that grounded a superseded memory, and the current statement."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=8, max_length=2000)
    current: str | None = Field(default=None, max_length=2000)


class BuildContextRequest(BaseModel):
    task: str
    budget: int | None = Field(default=None, gt=0)
    retrieval_query: str | None = None
    include_global_core: bool = False
    response_profile: BuildContextResponseProfile = BuildContextResponseProfile.FULL
    # source_evidence/v2 only: evidence stating one of these superseded values is
    # ranked behind the rest (and dropped first when the envelope is full).
    superseded: list[SupersededQuotePayload] = Field(default_factory=list, max_length=64)


class ArchiveSourceSpanPayload(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> "ArchiveSourceSpanPayload":
        if self.start > self.end:
            raise ValueError("span start must be less than or equal to end")
        return self


class ArchiveIdentityScopePayload(BaseModel):
    user_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    archive_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ArchiveSourceRefPayload(BaseModel):
    source_type: Literal[
        "message",
        "episode",
        "document",
        "passage",
        "memory",
        "core_block",
        "tool_call",
        "approval",
        "manual",
    ]
    source_id: str = Field(min_length=1)
    session_id: str | None = None
    identity_scope: ArchiveIdentityScopePayload | None = None
    span: ArchiveSourceSpanPayload | None = None
    quote: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    approval_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_manual_approval(self) -> "ArchiveSourceRefPayload":
        if self.source_type == "manual" and not self.approval_id:
            raise ValueError("manual source refs require approval_id")
        return self


class ArchiveIdentityArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["archive"]
    archive_id: str = Field(min_length=1)


class ArchiveIdentitySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["source"]
    source_id: str = Field(min_length=1)
    file_id: str | None = None


class ArchiveIdentityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["file"]
    file_id: str = Field(min_length=1)


ArchiveDocumentIdentity = Annotated[
    ArchiveIdentityArchive | ArchiveIdentitySource | ArchiveIdentityFile,
    Field(discriminator="kind"),
]


class ArchiveDocumentIngestRequest(BaseModel):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str
    source_refs: list[ArchiveSourceRefPayload] = Field(min_length=1)
    identity: ArchiveDocumentIdentity
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    producer: str = "explicit_document"


class ArchiveDiagnosticResponse(BaseModel):
    event_type: str
    reason_code: str
    item_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchiveDocumentIngestResponse(BaseModel):
    document_id: str
    chunk_ids: list[str]
    passage_ids: list[str]
    diagnostics: list[ArchiveDiagnosticResponse] = Field(default_factory=list)


class ArchiveAttachmentRequest(BaseModel):
    archive_id: str = Field(min_length=1)
    scope_type: Literal["agent", "project", "source", "user", "run", "session"]
    scope_id: str = Field(min_length=1)
    source_refs: list[ArchiveSourceRefPayload] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchiveAttachmentResponse(BaseModel):
    attachment_id: str
    archive_id: str
    scope_type: str
    scope_id: str
    passage_count: int
    diagnostics: list[ArchiveDiagnosticResponse] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    title: str = "Untitled session"


class IngestResponse(BaseModel):
    message: Message
    should_page: bool
    session_token_count: int
    replayed: bool = False


class EvalCase(BaseModel):
    case_id: str
    conversation: list[MessageCreate]
    question: str
    expected_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    required_sources: list[str] = Field(default_factory=list)
    required_fact_sources: dict[str, list[str]] = Field(default_factory=dict)
    query_in_new_session: bool = False
    include_global_core: bool = False

    @model_validator(mode="after")
    def require_fact_sources_for_multi_fact_cases(self) -> "EvalCase":
        if (
            len(self.expected_facts) > 1
            and self.required_sources
            and not self.required_fact_sources
        ):
            raise ValueError(
                "multi-fact eval cases with required sources must use "
                "required_fact_sources for per-fact source mapping"
            )
        if self.required_fact_sources:
            expected = set(self.expected_facts)
            provided = set(self.required_fact_sources)
            missing = sorted(expected - provided)
            unknown = sorted(provided - expected)
            if missing or unknown:
                details: list[str] = []
                if missing:
                    details.append(f"missing keys: {', '.join(missing)}")
                if unknown:
                    details.append(f"unknown keys: {', '.join(unknown)}")
                raise ValueError(
                    "eval cases must provide required_fact_sources "
                    f"for exactly the expected facts ({'; '.join(details)})"
                )
            empty_sources = sorted(
                fact for fact, source_ids in self.required_fact_sources.items() if not source_ids
            )
            if empty_sources:
                raise ValueError(
                    "required_fact_sources entries must contain at least one source id "
                    f"(empty keys: {', '.join(empty_sources)})"
                )
        return self
