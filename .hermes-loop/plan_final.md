# Memory v3 Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Memory v3 contract definitions and adapter boundaries while keeping legacy behavior unchanged.

**Architecture:** Create a standalone `memoryos_lite.v3_contracts` module containing Pydantic contracts, Protocol interfaces, table-boundary constants, and legacy adapter helpers. Existing runtime paths continue importing and using legacy `schemas.py`, `store.py`, and retrieval modules until later opt-in phases.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, SQLAlchemy-backed legacy store.

---

## File Structure

- Create: `src/memoryos_lite/v3_contracts.py`
  - Owns all phase-1 v3 contract models, enums, protocol interfaces, table-boundary constants, and adapter helpers.
- Create: `tests/test_v3_contracts.py`
  - Verifies shared formats, source-backed core-memory rules, table boundaries, legacy adapters, and kernel policy/approval contracts.
- Modify: no runtime modules in phase 1.
  - Do not modify `src/memoryos_lite/engine.py`, `src/memoryos_lite/cli.py`, `src/memoryos_lite/api/app.py`, or default recall configuration.

## Task 1: Shared Provenance and Diagnostic Contracts

**Files:**
- Create: `tests/test_v3_contracts.py`
- Create: `src/memoryos_lite/v3_contracts.py`

- [ ] **Step 1: Write failing tests for shared formats**

Add this initial test file:

```python
import pytest
from pydantic import ValidationError

from memoryos_lite.v3_contracts import (
    DiagnosticEvent,
    IdentityScope,
    LayerBudgetDecision,
    MemoryHistoryEvent,
    ensure_persisted_identity_scope,
    SourceRef,
    SourceSpan,
)


def test_source_ref_requires_non_empty_source_id_and_valid_span():
    ref = SourceRef(
        source_type="message",
        source_id="msg_1",
        span=SourceSpan(start=3, end=9),
        quote="source",
        confidence=0.75,
    )

    assert ref.source_id == "msg_1"
    assert ref.span.start == 3
    assert ref.confidence == 0.75

    with pytest.raises(ValidationError):
        SourceRef(source_type="message", source_id="")

    with pytest.raises(ValidationError):
        SourceRef(
            source_type="message",
            source_id="msg_1",
            span=SourceSpan(start=10, end=4),
        )

    manual_ref = SourceRef(
        source_type="manual",
        source_id="policy_1",
        approval_id="appr_1",
    )
    assert manual_ref.approval_id == "appr_1"

    with pytest.raises(ValidationError):
        SourceRef(source_type="manual", source_id="policy_2")


def test_identity_scope_allows_ephemeral_values_but_persisted_scope_is_guarded():
    empty_scope = IdentityScope()
    scope = IdentityScope(user_id="user_1", session_id="ses_1", tags=["project"])

    assert empty_scope.tags == []
    assert scope.user_id == "user_1"
    assert scope.tags == ["project"]

    with pytest.raises(ValueError):
        ensure_persisted_identity_scope(empty_scope)

    assert ensure_persisted_identity_scope(scope) is scope


def test_history_diagnostics_and_budget_decisions_share_source_refs():
    ref = SourceRef(source_type="message", source_id="msg_1", session_id="ses_1")
    history = MemoryHistoryEvent(
        memory_id="mem_1",
        memory_type="core_block",
        operation="replace",
        actor="agent",
        reason="newer user correction",
        before={"value": "old"},
        after={"value": "new"},
        source_refs=[ref],
    )
    diagnostic = DiagnosticEvent(
        layer="recall",
        event_type="rank",
        item_id="rec_1",
        reason_code="bm25_overlap",
        score=3.5,
        included=True,
        source_refs=[ref],
    )
    decision = LayerBudgetDecision(
        layer="archival",
        requested_tokens=1200,
        allocated_tokens=400,
        used_tokens=376,
        dropped_item_ids=["passage_2"],
        reason_code="budget_limit",
    )

    assert history.source_refs == [ref]
    assert diagnostic.layer == "recall"
    assert decision.dropped_item_ids == ["passage_2"]

    with pytest.raises(ValidationError):
        MemoryHistoryEvent(
            memory_id="mem_2",
            memory_type="archival_memory",
            operation="replace",
            actor="agent",
            reason="bad replace",
            after={"value": "new"},
            source_refs=[ref],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'memoryos_lite.v3_contracts'`.

- [ ] **Step 3: Write minimal shared contracts**

Create `src/memoryos_lite/v3_contracts.py`:

```python
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
    def validate_order(self) -> "SourceSpan":
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
    def validate_manual_source(self) -> "SourceRef":
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
    def validate_operation_payload(self) -> "MemoryHistoryEvent":
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: PASS for the three tests in Task 1.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py
git commit -m "feat: add memory v3 shared contracts"
```

## Task 2: Memory Layer Contracts and Source-Backed Core Updates

**Files:**
- Modify: `tests/test_v3_contracts.py`
- Modify: `src/memoryos_lite/v3_contracts.py`

- [ ] **Step 1: Write failing tests for memory layer contracts**

Append to `tests/test_v3_contracts.py`:

```python
from memoryos_lite.schemas import Episode, MemoryItem, MemoryItemType, MemoryPage, Message, PageType, Role
from memoryos_lite.v3_contracts import (
    ArchivalDocument,
    ArchivalMemory,
    ArchivalPassage,
    ApprovalState,
    ContextComposerRequest,
    ContextLayerItem,
    ContextPackageV3,
    CoreMemoryBlock,
    CoreMemoryUpdate,
    MessageLogEntry,
    RecallMemoryEntry,
    message_to_log_entry,
    page_to_archival_document,
    episode_to_recall_entry,
    item_to_archival_memory,
    item_to_archival_passage,
)


def test_legacy_message_and_episode_adapt_to_v3_layer_contracts():
    message = Message(
        id="msg_1",
        session_id="ses_1",
        role=Role.USER,
        content="Alice moved to Shanghai.",
        token_count=5,
    )
    episode = Episode(
        id="epi_1",
        session_id="ses_1",
        message_id="msg_1",
        role=Role.USER,
        text="Alice moved to Shanghai.",
        index_text="[speaker=user] Alice moved to Shanghai.",
        position=1,
        source_message_ids=["msg_1"],
    )

    log_entry = message_to_log_entry(message)
    recall_entry = episode_to_recall_entry(episode)

    assert isinstance(log_entry, MessageLogEntry)
    assert log_entry.source_refs[0].source_id == "msg_1"
    assert isinstance(recall_entry, RecallMemoryEntry)
    assert recall_entry.source_message_ids == ["msg_1"]
    assert recall_entry.source_refs[0].source_type == "message"


def test_page_and_item_are_legacy_inputs_not_archival_targets():
    page = MemoryPage(
        id="page_1",
        session_id="ses_1",
        page_type=PageType.SOURCE_SUMMARY,
        title="Trip summary",
        summary="Alice discussed Shanghai.",
        source_message_ids=["msg_1"],
    )
    item = MemoryItem(
        id="item_1",
        page_id="page_1",
        session_id="ses_1",
        item_type=MemoryItemType.PROFILE,
        content="Alice lives in Shanghai.",
        source_message_ids=["msg_1"],
    )

    document = page_to_archival_document(page)
    memory = item_to_archival_memory(item)
    passage = item_to_archival_passage(item, document_id=document.id)

    assert isinstance(document, ArchivalDocument)
    assert document.legacy_page_id == "page_1"
    assert isinstance(memory, ArchivalMemory)
    assert memory.legacy_item_id == "item_1"
    assert isinstance(passage, ArchivalPassage)
    assert passage.document_id == document.id
    assert passage.legacy_item_id == "item_1"
    assert document.id.startswith("adoc_")
    assert memory.id.startswith("amem_")
    assert passage.id.startswith("apsg_")


def test_core_memory_update_requires_source_refs_or_approval():
    block = CoreMemoryBlock(
        id="core_1",
        label="human",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=200,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )

    update = CoreMemoryUpdate(
        block_id=block.id,
        operation="append",
        content="Alice prefers rail travel.",
        source_refs=[SourceRef(source_type="message", source_id="msg_2")],
    )

    assert update.source_refs[0].source_id == "msg_2"

    with pytest.raises(ValidationError):
        CoreMemoryUpdate(block_id=block.id, operation="append", content="source-less")

    approved_state = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"block": "human", "content": "manually approved"},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=block.created_at,
    )
    approved = CoreMemoryUpdate(
        block_id=block.id,
        operation="append",
        content="manually approved",
        approval_state=approved_state,
    )
    assert approved.approval_state is approved_state

    with pytest.raises(ValidationError):
        CoreMemoryUpdate(
            block_id=block.id,
            operation="append",
            content="pending approval cannot write",
            approval_state=ApprovalState(
                id="appr_2",
                session_id="ses_1",
                tool_name="memory_core_append",
                requested_action={"block": "human", "content": "pending"},
                status="pending",
                requested_by="agent",
            ),
        )


def test_context_package_v3_groups_layer_items_and_budget_decisions():
    package = ContextPackageV3(
        session_id="ses_1",
        task="answer the user",
        items=[
            ContextLayerItem(
                layer="core",
                item_id="core_1",
                text="Alice lives in Shanghai.",
                estimated_tokens=5,
                source_refs=[SourceRef(source_type="core_block", source_id="core_1")],
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="core",
                requested_tokens=200,
                allocated_tokens=100,
                used_tokens=5,
                reason_code="always_in_context",
            )
        ],
    )
    request = ContextComposerRequest(session_id="ses_1", task="answer the user", budget=1000)

    assert package.items[0].layer == "core"
    assert request.budget == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: FAIL with import errors for the new memory layer, core approval, and adapter contracts.

- [ ] **Step 3: Add memory layer contracts and adapters**

Append these definitions to `src/memoryos_lite/v3_contracts.py`:

```python
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
    tags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    legacy_page_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ArchivalPassage(BaseModel):
    id: str
    document_id: str | None = None
    archive_id: str | None = None
    text: str
    citation: SourceSpan | None = None
    tags: list[str] = Field(default_factory=list)
    score: float | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    legacy_item_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchivalMemory(BaseModel):
    id: str
    memory_type: Literal["fact", "preference", "event", "procedure", "knowledge"]
    content: str
    identity_scope: IdentityScope | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    history: list[MemoryHistoryEvent] = Field(default_factory=list)
    entity_links: list[str] = Field(default_factory=list)
    legacy_item_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class CoreMemoryBlock(BaseModel):
    id: str
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    value: str = ""
    limit_tokens: int = Field(gt=0)
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
    def validate_resolution(self) -> "ApprovalState":
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
    def require_source_or_approval(self) -> "CoreMemoryUpdate":
        if not self.source_refs:
            if self.approval_state is None or self.approval_state.status != "approved":
                raise ValueError("core memory updates require source_refs or approved approval_state")
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
        source_refs=[SourceRef(source_type=SourceType.MESSAGE, source_id=message.id, session_id=message.session_id)],
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
            SourceRef(source_type=SourceType.MESSAGE, source_id=source_id, session_id=episode.session_id)
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
            SourceRef(source_type=SourceType.MESSAGE, source_id=source_id, session_id=page.session_id)
            for source_id in page.source_message_ids
        ],
        legacy_page_id=page.id,
        metadata={"legacy_page_type": page.page_type.value},
        created_at=page.created_at,
    )


def item_to_archival_memory(item: MemoryItem) -> ArchivalMemory:
    type_map = {
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
            SourceRef(source_type=SourceType.MESSAGE, source_id=source_id, session_id=item.session_id)
            for source_id in item.source_message_ids
        ],
        legacy_item_id=item.id,
        created_at=item.created_at,
    )


def item_to_archival_passage(
    item: MemoryItem,
    document_id: str | None = None,
) -> ArchivalPassage:
    return ArchivalPassage(
        id=f"apsg_{item.id}",
        document_id=document_id,
        text=item.content,
        source_refs=[
            SourceRef(source_type=SourceType.MESSAGE, source_id=source_id, session_id=item.session_id)
            for source_id in item.source_message_ids
        ],
        legacy_item_id=item.id,
        metadata={"legacy_page_id": item.page_id, "legacy_item_type": item.item_type.value},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: PASS for Task 1 and Task 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py
git commit -m "feat: define memory v3 layer contracts"
```

## Task 3: Persistence Boundary and Adapter Manifest

**Files:**
- Modify: `tests/test_v3_contracts.py`
- Modify: `src/memoryos_lite/v3_contracts.py`

- [ ] **Step 1: Write failing tests for table boundaries**

Append to `tests/test_v3_contracts.py`:

```python
from memoryos_lite.v3_contracts import (
    REQUIRED_V3_ADAPTERS,
    V3_FUTURE_TABLES,
    V3_KEEP_TABLES,
    V3_NO_NEW_TARGETS,
)


def test_v3_table_boundary_keeps_legacy_tables_and_defers_recall_split():
    assert V3_KEEP_TABLES == {
        "sessions",
        "messages",
        "episodes",
        "memory_pages",
        "memory_items",
        "memory_patches",
        "trace_events",
        "alembic_version",
    }
    assert "recall_memory_entries" not in V3_FUTURE_TABLES
    assert "archival_documents" in V3_FUTURE_TABLES
    assert "kernel_traces" in V3_FUTURE_TABLES


def test_page_and_item_are_declared_legacy_adapter_inputs_only():
    assert V3_NO_NEW_TARGETS == {"MemoryPage", "MemoryItem"}
    assert REQUIRED_V3_ADAPTERS["MemoryPage"] == "ArchivalDocument migration input"
    assert REQUIRED_V3_ADAPTERS["MemoryItem"] == "ArchivalMemory or ArchivalPassage adapter"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: FAIL with import errors for `V3_KEEP_TABLES`, `V3_FUTURE_TABLES`, `V3_NO_NEW_TARGETS`, and `REQUIRED_V3_ADAPTERS`.

- [ ] **Step 3: Add boundary constants**

Append to `src/memoryos_lite/v3_contracts.py`:

```python
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
    "archival_passages",
    "archival_memories",
    "archival_memory_history",
    "core_memory_blocks",
    "core_memory_history",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: PASS for all table-boundary tests.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py
git commit -m "feat: declare memory v3 persistence boundaries"
```

## Task 4: Kernel Policy, Approval, Trace, and Protocol Contracts

**Files:**
- Modify: `tests/test_v3_contracts.py`
- Modify: `src/memoryos_lite/v3_contracts.py`

- [ ] **Step 1: Write failing tests for kernel contracts**

Append to `tests/test_v3_contracts.py`:

```python
from memoryos_lite.v3_contracts import (
    ApprovalState,
    KernelTraceEvent,
    ToolPolicyDecision,
    ToolPolicyRule,
)


def test_tool_policy_decision_never_allows_unknown_tool_implicitly():
    rule = ToolPolicyRule(
        id="rule_1",
        tool_name="memory_core_append",
        effect="require_approval",
        reason="core memory mutation",
        priority=10,
        source_refs=[SourceRef(source_type="manual", source_id="policy")],
    )
    decision = ToolPolicyDecision(
        tool_name="memory_core_append",
        effect="require_approval",
        matched_rule_ids=[rule.id],
        requires_approval=True,
        reason=rule.reason,
    )

    assert decision.effect == "require_approval"
    assert decision.requires_approval is True

    with pytest.raises(ValidationError):
        ToolPolicyDecision(
            tool_name="unknown_tool",
            effect="allow",
            matched_rule_ids=[],
            requires_approval=False,
            reason="implicit allow is forbidden",
        )


def test_approval_state_requires_resolution_metadata_when_approved():
    pending = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"block": "human", "content": "Alice likes rail."},
        status="pending",
        requested_by="agent",
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"block": "human", "content": "Alice likes rail."},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=pending.created_at,
    )

    assert pending.status == "pending"
    assert approved.approved_by == "user"

    with pytest.raises(ValidationError):
        ApprovalState(
            id="appr_2",
            session_id="ses_1",
            tool_name="memory_core_append",
            requested_action={"block": "human"},
            status="approved",
            requested_by="agent",
        )


def test_kernel_trace_events_are_ordered_and_replayable():
    event = KernelTraceEvent(
        step_id="step_1",
        session_id="ses_1",
        sequence=1,
        event_type="tool_policy_decision",
        payload={"tool_name": "memory_core_append", "effect": "require_approval"},
        source_refs=[SourceRef(source_type="approval", source_id="appr_1")],
        approval_id="appr_1",
    )

    assert event.sequence == 1
    assert event.payload["effect"] == "require_approval"

    with pytest.raises(ValidationError):
        KernelTraceEvent(
            step_id="step_1",
            session_id="ses_1",
            sequence=0,
            event_type="bad",
            payload={},
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: FAIL with import errors for the tool-policy, kernel-trace, and protocol models.

- [ ] **Step 3: Add kernel contracts and protocols**

`ApprovalState` was introduced in Task 2 because source-less core-memory writes
must link to an approved approval contract. This task adds the remaining kernel
policy, trace, and protocol contracts, and keeps the ApprovalState tests in the
same kernel section for review clarity.

Append to `src/memoryos_lite/v3_contracts.py`:

```python
ToolPolicyEffect = Literal["allow", "deny", "require_approval"]


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
    def forbid_implicit_allow(self) -> "ToolPolicyDecision":
        if self.effect == "allow" and not self.matched_rule_ids:
            raise ValueError("allow decisions require an explicit matched rule")
        if self.effect == "require_approval" and not self.requires_approval:
            raise ValueError("require_approval decisions must set requires_approval")
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


class ToolExecutionResult(BaseModel):
    tool_name: str
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
```

Expected: PASS for all v3 contract tests.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py
git commit -m "feat: define memory v3 kernel contracts"
```

## Task 5: Contract Export Hygiene and Regression Guard

**Files:**
- Modify: `src/memoryos_lite/v3_contracts.py`
- Modify: `tests/test_v3_contracts.py`

- [ ] **Step 1: Write failing tests for public exports and legacy stability**

Append to `tests/test_v3_contracts.py`:

```python
import memoryos_lite.v3_contracts as contracts


def test_v3_contract_module_exports_expected_public_names():
    expected = {
        "SourceRef",
        "IdentityScope",
        "MemoryHistoryEvent",
        "DiagnosticEvent",
        "MessageLogEntry",
        "RecallMemoryEntry",
        "ArchivalDocument",
        "ArchivalPassage",
        "ArchivalMemory",
        "CoreMemoryBlock",
        "CoreMemoryUpdate",
        "ContextComposer",
        "AgentStepRunner",
        "ToolPolicyEngine",
        "ApprovalGate",
        "ToolExecutionManager",
        "ContinuationController",
        "ensure_persisted_identity_scope",
        "V3_KEEP_TABLES",
        "V3_FUTURE_TABLES",
        "REQUIRED_V3_ADAPTERS",
    }

    assert expected.issubset(set(contracts.__all__))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_v3_contracts.py::test_v3_contract_module_exports_expected_public_names -v
```

Expected: FAIL with `AttributeError: module 'memoryos_lite.v3_contracts' has no attribute '__all__'`.

- [ ] **Step 3: Add explicit `__all__`**

Append to `src/memoryos_lite/v3_contracts.py`:

```python
__all__ = [
    "AgentStepRequest",
    "AgentStepResult",
    "AgentStepRunner",
    "ApprovalGate",
    "ApprovalState",
    "ArchivalDocument",
    "ArchivalMemory",
    "ArchivalPassage",
    "ContextComposer",
    "ContextComposerRequest",
    "ContextLayerItem",
    "ContextPackageV3",
    "ContinuationController",
    "ContinuationDecision",
    "CoreMemoryBlock",
    "CoreMemoryUpdate",
    "DiagnosticEvent",
    "IdentityScope",
    "KernelTraceEvent",
    "LayerBudgetDecision",
    "MemoryHistoryEvent",
    "MessageLogEntry",
    "REQUIRED_V3_ADAPTERS",
    "RecallMemoryEntry",
    "SourceRef",
    "SourceSpan",
    "ensure_persisted_identity_scope",
    "ToolExecutionManager",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolPolicyDecision",
    "ToolPolicyEngine",
    "ToolPolicyRule",
    "V3_FUTURE_TABLES",
    "V3_KEEP_TABLES",
    "V3_NO_NEW_TARGETS",
    "episode_to_recall_entry",
    "item_to_archival_memory",
    "item_to_archival_passage",
    "message_to_log_entry",
    "page_to_archival_document",
]
```

- [ ] **Step 4: Run targeted and full verification**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -v
uv run pytest -q
```

Expected:

- `tests/test_v3_contracts.py`: PASS.
- Full suite: PASS, with no legacy runtime behavior changes.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py
git commit -m "test: guard memory v3 contract exports"
```

## Final Verification

- [ ] Run `uv run pytest -q`.
- [ ] Confirm no phase-1 migrations were added under `alembic/versions/`.
- [ ] Confirm no default runtime modules were modified:

```bash
git diff --name-only HEAD~5..HEAD | sort
```

Expected changed files:

```text
src/memoryos_lite/v3_contracts.py
tests/test_v3_contracts.py
```

- [ ] Write `.hermes-loop/result.md` during EXECUTE with changed files, test results,
  and any implementation deviations.
