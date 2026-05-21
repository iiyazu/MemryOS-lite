# Core Memory Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable shadow-write core memory blocks with traceable history, while keeping default `v1` behavior and the opt-in `v2` recall path unchanged.

**Architecture:** Keep `v3_contracts.py` as the contract layer, add SQLite persistence plus append-only history in `store.py`, and put the mutation semantics in a small internal `core_memory.py` service. The default legacy context path stays untouched; render support is explicit and opt-in only.

**Tech Stack:** Python 3.11, Pydantic v2, SQLAlchemy, Alembic, pytest.

---

## File Structure

- Modify: `src/memoryos_lite/v3_contracts.py`
  - Tighten `CoreMemoryUpdate` validation and add soft-delete fields to `CoreMemoryBlock`.
- Modify: `src/memoryos_lite/store.py`
  - Add core-memory SQLAlchemy records, CRUD helpers, history persistence, and Alembic head stamping.
- Create: `src/memoryos_lite/core_memory.py`
  - Own create / append / replace / update / delete semantics and deterministic render formatting.
- Create: `alembic/versions/0005_add_core_memory.py`
  - Add the new SQLite tables and downgrade path.
- Modify: `tests/test_v3_contracts.py`
  - Add contract regressions for replace validation and soft-delete defaults.
- Create: `tests/test_core_memory_store.py`
  - Cover persistence, history, soft delete, and migration stamping.
- Create: `tests/test_core_memory_service.py`
  - Cover provenance checks, append / replace / update semantics, token-limit enforcement, and renderer output.
- Modify: `tests/test_engine.py`
  - Prove `build_context()` still ignores core memory by default.

## Task 1: Tighten Core Contracts

**Files:**
- Modify: `src/memoryos_lite/v3_contracts.py`
- Modify: `tests/test_v3_contracts.py`

- [ ] **Step 1: Write the failing tests**

Add these assertions to `tests/test_v3_contracts.py`:

```python
def test_core_memory_block_defaults_soft_delete_fields():
    block = CoreMemoryBlock(
        id="core_1",
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=200,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )

    assert block.deleted_at is None
    assert block.deleted_by_event_id is None


def test_core_memory_replace_requires_old_value():
    with pytest.raises(ValidationError):
        CoreMemoryUpdate(
            block_id="core_1",
            operation="replace",
            content="Alice lives in Suzhou.",
            source_refs=[SourceRef(source_type="message", source_id="msg_2")],
        )
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -q
```

Expected: FAIL because `CoreMemoryBlock` does not yet expose the soft-delete fields and `CoreMemoryUpdate` still accepts `replace` without `old`.

- [ ] **Step 3: Write the minimal implementation**

Patch `src/memoryos_lite/v3_contracts.py` with:

```python
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
    deleted_at: datetime | None = None
    deleted_by_event_id: str | None = None


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
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_v3_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py
git commit -m "test: tighten core memory contracts"
```

## Task 2: Add SQLite Persistence and History

**Files:**
- Create: `alembic/versions/0005_add_core_memory.py`
- Modify: `src/memoryos_lite/store.py`
- Create: `tests/test_core_memory_store.py`

- [ ] **Step 1: Write the failing store tests**

Add these tests to `tests/test_core_memory_store.py`:

```python
from sqlalchemy import text

from memoryos_lite.config import Settings
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import CoreMemoryBlock, SourceRef


def _settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )


def test_core_memory_store_round_trip_history_and_soft_delete(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()

    block = CoreMemoryBlock(
        id="core_1",
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=100,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )

    created = store.create_core_memory_block(block)
    assert created.id == "core_1"
    assert store.get_core_memory_block("core_1").value == "Alice lives in Shanghai."

    history = store.list_core_memory_history("core_1")
    assert history[-1].operation == "add"

    deleted = store.delete_core_memory_block(
        "core_1",
        source_refs=[SourceRef(source_type="message", source_id="msg_2")],
        actor="agent",
        reason="user requested removal",
    )
    assert deleted.deleted_at is not None
    assert store.get_core_memory_block("core_1") is None
    assert store.get_core_memory_block("core_1", include_deleted=True).deleted_at is not None
    assert store.list_core_memory_history("core_1")[-1].operation == "delete"


def test_init_db_stamps_new_core_memory_head(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()
    with store.db() as db:
        version = db.scalar(text("select version_num from alembic_version limit 1"))
    assert version == "0005_add_core_memory"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_core_memory_store.py -q
```

Expected: FAIL because the new tables and store methods do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Add the record classes and helpers to `src/memoryos_lite/store.py`:

```python
class CoreMemoryBlockRecord(Base):
    __tablename__ = "core_memory_blocks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limit_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    deleted_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class CoreMemoryHistoryRecord(Base):
    __tablename__ = "core_memory_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
```

Add these `MemoryStore` methods with concrete behavior:

- `create_core_memory_block(block)`: insert `CoreMemoryBlockRecord`, append an
  `add` `MemoryHistoryEvent`, and return the block.
- `get_core_memory_block(block_id, include_deleted=False)`: return `None` when
  the record is missing or soft-deleted and `include_deleted` is false.
- `list_core_memory_blocks(include_deleted=False)`: order by `created_at`, then
  `label`, then `id`; hide soft-deleted records by default.
- `update_core_memory_block(block)`: update value, metadata, source refs,
  timestamps, and soft-delete fields for an existing block.
- `delete_core_memory_block(block_id, source_refs, actor, reason)`: write a
  `delete` history event, set `deleted_at` and `deleted_by_event_id`, and return
  the deleted block.
- `append_core_memory_history(event)`: insert `CoreMemoryHistoryRecord`.
- `list_core_memory_history(block_id)`: return events ordered by `created_at`
  and `id`.

Update `MemoryStore.init_db()` so fresh DBs stamp `0005_add_core_memory` instead
of `0004_add_episodes`.

Implement the Alembic migration with `upgrade()` creating both tables and
`downgrade()` dropping them in reverse order.

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_core_memory_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/0005_add_core_memory.py src/memoryos_lite/store.py tests/test_core_memory_store.py
git commit -m "feat: persist core memory blocks"
```

## Task 3: Add Core Memory Semantics and Rendering

**Files:**
- Create: `src/memoryos_lite/core_memory.py`
- Create: `tests/test_core_memory_service.py`

- [ ] **Step 1: Write the failing service tests**

Add these tests to `tests/test_core_memory_service.py`:

```python
import pytest

from memoryos_lite.config import Settings
from memoryos_lite.core_memory import CoreMemoryService, render_core_memory_blocks
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import CoreMemoryBlock, SourceRef


class FakeTokenizer:
    def count(self, text: str) -> int:
        return len(text.split())


def _service(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )
    store = MemoryStore(settings)
    store.init_db()
    return CoreMemoryService(store=store, tokenizer=FakeTokenizer())


def test_core_memory_service_requires_source_backed_writes(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError):
        service.create_block(
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=20,
            source_refs=[],
            actor="agent",
            reason="seed profile",
        )


def test_core_memory_service_append_replace_update_and_render(tmp_path):
    service = _service(tmp_path)
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = service.create_block(
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=20,
        source_refs=[ref],
        actor="agent",
        reason="seed profile",
    )

    appended = service.append_block(
        block.id,
        "Alice prefers rail travel.",
        source_refs=[ref],
        actor="agent",
        reason="new fact",
    )
    replaced = service.replace_block(
        block.id,
        old="Shanghai",
        content="Suzhou",
        source_refs=[ref],
        actor="agent",
        reason="correction",
    )
    updated = service.update_block(
        block.id,
        "Alice lives in Suzhou.",
        source_refs=[ref],
        actor="agent",
        reason="full rewrite",
    )

    assert "Alice prefers rail travel." in appended.value
    assert replaced.value != block.value
    assert updated.value == "Alice lives in Suzhou."
    assert render_core_memory_blocks([updated]) == (
        "[Core Memory]\n"
        "- profile (20 tokens)\n"
        "  Stable user facts\n"
        "  Alice lives in Suzhou."
    )


def test_core_memory_service_rejects_over_limit_updates(tmp_path):
    service = _service(tmp_path)
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = service.create_block(
        label="profile",
        description="Stable user facts",
        value="Alice",
        limit_tokens=2,
        source_refs=[ref],
        actor="agent",
        reason="seed profile",
    )

    with pytest.raises(ValueError):
        service.append_block(
            block.id,
            "prefers rail travel",
            source_refs=[ref],
            actor="agent",
            reason="overflow",
        )
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_core_memory_service.py -q
```

Expected: FAIL because the service module and renderer do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `src/memoryos_lite/core_memory.py` with a service boundary like this:

```python
from dataclasses import dataclass

from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ApprovalState,
    CoreMemoryBlock,
    MemoryHistoryEvent,
    SourceRef,
)


def render_core_memory_blocks(blocks: list[CoreMemoryBlock]) -> str:
    lines = ["[Core Memory]"]
    for block in sorted(blocks, key=lambda b: (b.created_at, b.label, b.id)):
        if block.deleted_at is not None:
            continue
        lines.append(f"- {block.label} ({block.limit_tokens} tokens)")
        lines.append(f"  {block.description}")
        lines.append(f"  {block.value}")
    return "\n".join(lines)


@dataclass
class CoreMemoryService:
    store: MemoryStore
    tokenizer: TokenEstimator
```

Implement public methods named `create_block`, `append_block`, `replace_block`,
`update_block`, and `delete_block`. Each method must require `actor` and
`reason`, reject source-less writes unless an approved `ApprovalState` is
provided, write a matching `MemoryHistoryEvent`, and return the resulting
`CoreMemoryBlock`.

Use these semantics inside the service:

```python
separator = "\n\n"
next_value = block.value + (separator if block.value else "") + addition
if self.tokenizer.count(next_value) > block.limit_tokens:
    raise ValueError("core memory block exceeds limit_tokens")

event = MemoryHistoryEvent(
    memory_id=block.id,
    memory_type="core_block",
    operation="update",
    actor=actor,
    reason=reason,
    before=block.model_dump(mode="json"),
    after=updated_block.model_dump(mode="json"),
    source_refs=source_refs,
)
```

For `replace`, use the first exact match of `old` and fail if the substring does
not exist. For `delete`, write a `delete` history event with `before` populated
and `after=None`, then soft-delete the block through the store.

Honor approved manual provenance through the existing `ApprovalState` model and
manual `SourceRef` values that include a real non-empty `approval_id`.

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_core_memory_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/core_memory.py tests/test_core_memory_service.py
git commit -m "feat: add core memory mutation service"
```

## Task 4: Lock the Default Context Regression

**Files:**
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Add the regression test**

Add a focused regression near the existing `build_context()` tests:

```python
from memoryos_lite.v3_contracts import CoreMemoryBlock, SourceRef


def test_build_context_ignores_core_memory_blocks(service):
    session = service.create_session("core-memory-regression")
    service.store.create_core_memory_block(
        CoreMemoryBlock(
            id="core_1",
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=100,
            source_refs=[SourceRef(source_type="message", source_id="msg_1")],
        )
    )

    context = service.build_context(session.id, "用户最终决定做什么？", budget=200)

    assert all(not key.startswith("core_") for key in context.metadata)
    assert "Alice lives in Shanghai." not in context.model_dump_json()
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
uv run pytest tests/test_engine.py -q
```

Expected: FAIL until the regression is in place or the imports are added.

- [ ] **Step 3: Write the minimal implementation**

Keep the engine unchanged. The only change should be the regression test that
proves the current default path does not pick up core memory automatically.

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest tests/test_engine.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full verification sweep**

Run:

```bash
uv run pytest -q
```

Expected: full suite stays green with no default-context regression.

- [ ] **Step 6: Commit**

```bash
git add tests/test_engine.py
git commit -m "test: protect default context from core memory"
```
