# phase: phase-13

# Phase 13 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make core memory promotion source-backed, conflict-aware, history-preserving, and renderable through the real v3 path without changing defaults.

**Architecture:** `MemoryLifecycleService` will decide whether a candidate creates or updates a core block. `CoreMemoryService` will own label lookup, provenance metadata propagation, and the service-level mutation rules. `MemoryStore` will expose an audited core-block update/delete boundary that records actor, reason, source refs, and history in one place, and it will reject read-only records there too. Sourceless mutable core writes cannot bypass `CoreMemoryService` or the promotion approval path. `V3ContextComposer` should remain a renderer only; it should surface the durable block state and token accounting, not pending candidates.

**Tech Stack:** Python 3.11, Pydantic, SQLAlchemy, pytest, ruff, uv, existing MemoryOS Lite v3 modules only.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-13/context_bundle.md`.
Brainstorm: `.hermes-loop/work/phase-13/brainstorm.md`.
Dispatch: `.hermes-loop/work/phase-13/god_dispatch.json`.

---

## File Map

- `src/memoryos_lite/memory_lifecycle.py`: candidate application route for create-vs-update promotion decisions.
- `src/memoryos_lite/core_memory.py`: label lookup, metadata-aware updates, and service-level read-only enforcement.
- `src/memoryos_lite/store.py`: audited core block update/delete boundary, read-only guards, and history emission.
- `tests/test_memory_lifecycle.py`: promotion, conflict, and approved-path RED tests.
- `tests/test_core_memory_store.py`: direct-store audit/read-only tests and soft-delete regression preservation.
- `tests/test_context_composer.py`: v3 rendering test for approved core promotion output and budget accounting.
- `tests/test_engine.py` and `tests/test_public_benchmarks.py`: explicit preservation checks for v3 default, v1 fallback, and kernel default-off.

## Task 1: RED tests for promotion, conflict, and direct-store bypasses

**Files:**
- Modify: `tests/test_memory_lifecycle.py`
- Modify: `tests/test_core_memory_store.py`
- Modify: `tests/test_context_composer.py`

- [ ] **Step 1: Add a failing promotion test**

Add a test that creates an existing mutable core block, applies an approved `archival_to_core_candidate()` with the same label, and asserts the existing block is updated in place rather than duplicated.

```python
def test_archival_to_core_candidate_updates_existing_core_block_in_place_with_history(tmp_path):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    lifecycle = MemoryLifecycleService(store, core)
    ref = _ref()

    existing = core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed core profile",
    )

    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[ref],
        reason="promote corrected preference",
        confidence=0.95,
        label="human",
        limit_tokens=40,
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_update",
        requested_action={"content": candidate.content},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=candidate.created_at,
    )

    applied = lifecycle.apply_candidate(candidate, actor="agent", approval_state=approved)

    blocks = store.list_core_memory_blocks()
    history = store.list_core_memory_history(existing.id)

    assert applied.status == "applied"
    assert len(blocks) == 1
    assert blocks[0].id == existing.id
    assert blocks[0].value == "Alice prefers rail travel."
    assert blocks[0].metadata["promotion_candidate_id"] == candidate.id
    assert blocks[0].metadata["approval_id"] == approved.id
    assert [event.operation for event in history] == ["add", "update"]
    assert history[1].before["value"] == "Alice prefers trains."
    assert history[1].after["value"] == "Alice prefers rail travel."
```

- [ ] **Step 2: Add a failing duplicate-label conflict test**

Add a test that creates two live core blocks with the same target label, applies an approved core candidate for that label, and asserts the lifecycle rejects the ambiguous label rather than picking one silently.

```python
def test_archival_to_core_candidate_rejects_duplicate_label_conflict(tmp_path):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    lifecycle = MemoryLifecycleService(store, core)
    ref = _ref()
    first = core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed human profile",
    )
    second = core.create_block(
        label="human",
        description="secondary live facts",
        value="Alice prefers buses.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed human profile duplicate",
    )

    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[ref],
        reason="promote corrected preference",
        confidence=0.95,
        label="human",
        limit_tokens=40,
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_update",
        requested_action={"content": candidate.content},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=candidate.created_at,
    )

    with pytest.raises(ValueError, match="multiple live core memory blocks share label"):
        lifecycle.apply_candidate(candidate, actor="agent", approval_state=approved)

    assert [block.value for block in store.list_core_memory_blocks()] == [
        "Alice prefers trains.",
        "Alice prefers buses.",
    ]
    assert [event.operation for event in store.list_core_memory_history(first.id)] == ["add"]
    assert [event.operation for event in store.list_core_memory_history(second.id)] == ["add"]
```

- [ ] **Step 3: Add a failing audited direct-store update test**

Add a test that exercises `MemoryStore.update_core_memory_block()` directly and expects the update to require audit metadata and emit history instead of silently mutating a copied block.

```python
def test_core_memory_store_update_requires_audit_metadata(tmp_path):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    ref = _ref()
    block = core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="agent",
        reason="seed core profile",
    )

    with pytest.raises(ValueError, match="core memory store updates require actor"):
        store.update_core_memory_block(block.model_copy(update={"value": "Alice prefers buses."}))

    assert store.get_core_memory_block(block.id).value == "Alice prefers trains."
    assert [event.operation for event in store.list_core_memory_history(block.id)] == ["add"]
```

- [ ] **Step 4: Add a failing direct-store read-only bypass test**

Add a test that hits the store boundary directly for a read-only block and expects both update and delete to fail there, not just in `CoreMemoryService`.

```python
def test_read_only_core_block_rejects_store_update_and_delete(tmp_path):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    ref = _ref()
    block = core.create_block(
        label="persona",
        description="stable assistant facts",
        value="I prefer concise answers.",
        limit_tokens=40,
        source_refs=[ref],
        actor="agent",
        reason="seed persona",
        read_only=True,
    )

    with pytest.raises(ValueError, match="read-only core memory block cannot be mutated"):
        store.update_core_memory_block(
            block.model_copy(update={"value": "I prefer detailed answers."}),
            actor="agent",
            reason="mutate read-only block",
            source_refs=[ref],
        )

    with pytest.raises(ValueError, match="read-only core memory block cannot be mutated"):
        store.delete_core_memory_block(block.id, source_refs=[ref], actor="agent", reason="delete read-only")
```

- [ ] **Step 5: Add a failing v3-rendering test for approved core promotion**

Switch the existing core-render test to apply an approved candidate onto a live block and assert the rendered item still carries source refs, merged provenance metadata, and token accounting.

```python
def test_v3_composer_renders_approved_core_promotion_with_provenance(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    core = CoreMemoryService(store, TokenEstimator())
    lifecycle = MemoryLifecycleService(store, core)

    core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed human profile",
    )

    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[ref],
        reason="promote stable preference",
        confidence=0.95,
        label="human",
        limit_tokens=40,
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_update",
        requested_action={"content": candidate.content},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=candidate.created_at,
    )
    lifecycle.apply_candidate(candidate, actor="agent", approval_state=approved)

    package = V3ContextComposer(
        store=store,
        settings=Settings(data_dir=tmp_path / "data", memoryos_memory_arch="v3"),
        tokenizer=TokenEstimator(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What does Alice prefer?",
            budget=80,
        )
    )

    core_items = [item for item in package.items if item.layer == "core"]
    assert len(core_items) == 1
    assert core_items[0].text.endswith("Alice prefers rail travel.")
    assert core_items[0].source_refs[0].source_id == "msg_1"
    assert core_items[0].metadata["metadata"]["promotion_candidate_id"] == candidate.id
    assert core_items[0].metadata["metadata"]["approval_id"] == approved.id
    assert core_items[0].metadata["tokens_current"] > 0
```

- [ ] **Step 6: Run the RED tests**

Run:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_updates_existing_core_block_in_place_with_history -q
uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_rejects_duplicate_label_conflict -q
uv run pytest tests/test_core_memory_store.py::test_core_memory_store_update_requires_audit_metadata -q
uv run pytest tests/test_core_memory_store.py::test_read_only_core_block_rejects_store_update_and_delete -q
uv run pytest tests/test_context_composer.py::test_v3_composer_renders_approved_core_promotion_with_provenance -q
```

Expected: each test fails before implementation because the current lifecycle still creates a fresh core block for promotion, does not reject duplicate live labels, and still allows a direct mutable store write to bypass the audited path.

## Task 2: Implement the promotion boundary and label-scoped conflict check

**Files:**
- Modify: `src/memoryos_lite/core_memory.py`
- Modify: `src/memoryos_lite/memory_lifecycle.py`

- [ ] **Step 1: Add label lookup and metadata-aware update support**

Add a block lookup helper to `CoreMemoryService` and allow update operations to merge promotion metadata into the stored block.

```python
def get_block_by_label(self, label: str, *, include_deleted: bool = False) -> CoreMemoryBlock | None:
    matches = [
        block
        for block in self.store.list_core_memory_blocks(include_deleted=include_deleted)
        if block.label == label
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"multiple live core memory blocks share label {label!r}")
    return matches[0]
```

Extend `update_block()` and `_persist_update()` so the caller can pass provenance metadata that is merged into the stored block and carried through the audited store boundary.

```python
def update_block(..., metadata: dict[str, object] | None = None, approval_state: ApprovalState | None = None) -> CoreMemoryBlock:
    ...
    return self._persist_update(..., metadata=metadata)
```

```python
def _persist_update(..., metadata: dict[str, object] | None = None) -> CoreMemoryBlock:
    updated = block.model_copy(update={
        "value": next_value,
        "source_refs": source_refs,
        "metadata": {**block.metadata, **(metadata or {})},
        "updated_at": utc_now(),
    })
```

- [ ] **Step 2: Route core promotion through create-or-update instead of always creating**

Change `MemoryLifecycleService.apply_candidate()` so core promotion resolves the target block by label, updates the existing block if present, and only creates a new block when the label is not yet present.

```python
label = str(candidate.metadata.get("label") or "promotion")
provenance = {
    **candidate.metadata,
    "promotion_candidate_id": candidate.id,
    "approval_id": approval_state.id,
}
existing = self.core_memory.get_block_by_label(label)
if existing is None:
    self.core_memory.create_block(...)
else:
    self.core_memory.update_block(
        existing.id,
        candidate.content,
        source_refs=list(candidate.source_refs),
        actor=actor,  # type: ignore[arg-type]
        reason=candidate.reason,
        approval_state=approval_state,
        metadata=provenance,
    )
```

Keep the approval gate intact: no approved `approval_state`, no core promotion.

- [ ] **Step 3: Re-run the promotion tests**

Run:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_updates_existing_core_block_in_place_with_history -q
uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_rejects_duplicate_label_conflict -q
uv run pytest tests/test_context_composer.py::test_v3_composer_renders_approved_core_promotion_with_provenance -q
```

Expected: the tests pass once core promotion updates the existing block, preserves history, and rejects ambiguous labels before mutation.

## Task 3: Enforce an audited store boundary for mutable core writes

**Files:**
- Modify: `src/memoryos_lite/store.py`
- Modify: `src/memoryos_lite/core_memory.py`

- [ ] **Step 1: Guard direct update writes with audit metadata and history**

Make `update_core_memory_block()` require audit metadata and emit its own history event so a copied mutable block cannot be rewritten without actor, reason, source refs, and durable provenance.

```python
def update_core_memory_block(
    self,
    block: CoreMemoryBlock,
    *,
    actor: str | None = None,
    reason: str | None = None,
    source_refs: list[SourceRef] | None = None,
) -> CoreMemoryBlock | None:
    if not actor:
        raise ValueError("core memory store updates require actor")
    if not reason:
        raise ValueError("core memory store updates require reason")
    if not source_refs:
        raise ValueError("core memory store updates require source_refs")
    with self.db() as db:
        record = db.get(CoreMemoryBlockRecord, block.id)
        if record is None:
            return None
        if record.read_only:
            raise ValueError("read-only core memory block cannot be mutated")
        before = self._core_block_from_record(record)
        record.label = block.label
        record.description = block.description
        record.value = block.value
        record.limit_tokens = block.limit_tokens
        record.read_only = block.read_only
        record.tags_json = json.dumps(block.tags, ensure_ascii=False)
        record.source_refs_json = self._dump_source_refs(block.source_refs)
        record.metadata_json = json.dumps(block.metadata, ensure_ascii=False)
        record.deleted_at = block.deleted_at
        record.deleted_by_event_id = block.deleted_by_event_id
        record.updated_at = block.updated_at
        after = self._core_block_from_record(record)
        db.add(
            self._history_record_from_event(
                MemoryHistoryEvent(
                    memory_id=before.id,
                    memory_type="core_block",
                    operation="update",
                    actor=actor,
                    reason=reason,
                    before=before.model_dump(mode="json"),
                    after=after.model_dump(mode="json"),
                    source_refs=list(source_refs),
                )
            )
        )
        return after
```

Apply the same read-only guard before soft deletion, but keep delete soft and history-preserving for mutable blocks.

Update `CoreMemoryService._persist_update()` so it calls the audited store helper instead of appending history separately.

```python
saved = self.store.update_core_memory_block(
    updated,
    actor=actor,
    reason=reason,
    source_refs=source_refs,
)
if saved is None:
    raise KeyError(f"core memory block not found: {block.id}")
return saved
```

- [ ] **Step 2: Re-run the store-level bypass test**

Run:

```bash
uv run pytest tests/test_core_memory_store.py::test_core_memory_store_update_requires_audit_metadata -q
uv run pytest tests/test_core_memory_store.py::test_read_only_core_block_rejects_store_update_and_delete -q
uv run pytest tests/test_core_memory_store.py::test_core_memory_store_round_trip_history_and_soft_delete -q
uv run pytest tests/test_core_memory_service.py::test_core_memory_service_rejects_read_only_mutations -q
```

Expected: PASS.

## Task 4: REFACTOR and verify the real chain stays stable

**Files:**
- Verify: `tests/test_memory_lifecycle.py`
- Verify: `tests/test_core_memory_store.py`
- Verify: `tests/test_core_memory_service.py`
- Verify: `tests/test_context_composer.py`
- Verify: `tests/test_engine.py`
- Verify: `tests/test_public_benchmarks.py`

- [ ] **Step 1: Clean up the implementation without changing behavior**

Keep the promotion path narrow and readable:

- no extra candidate store;
- no new runtime dependency;
- no direct mutable store path that bypasses audit metadata;
- no kernel-default change;
- no benchmark scoring change;
- no prompt-only shortcuts.

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py -q
```

Expected: all focused lifecycle tests pass.

- [ ] **Step 3: Verify default and fallback preservation explicitly**

Run:

```bash
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off \
  tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics_by_default \
  tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context -q
```

Expected: v3 remains the default, explicit v1 fallback still bypasses v3 context diagnostics, and kernel default stays off.

- [ ] **Step 4: Run the baseline checks**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: full suite stays green and lint remains clean.

- [ ] **Step 5: Run structural smoke only if the default v3 context output changed**

If the v3 context structure or default core rendering changed in a way that affects public benchmark context composition, run:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

If the default v3 public context did not change, do not promote on eval noise; record the phase as structural only.

- [ ] **Step 6: Hand off to review**

Write `result.md` and `execute_review.md` only after the regression suite and lint are green, then move to review with the same active goal and phase binding.
