# Spec: Phase 3 - Core Memory Blocks

## Goal

Add Letta-style core memory blocks with durable shadow-write persistence and
traceable mutation history while keeping default `v1` behavior and the opt-in
`v2` recall path unchanged.

Target compatibility state: `shadow-write`.

Phase 3 must add a real core-memory persistence boundary, but it must not feed
core memory into the default legacy context path yet.

## Source Inputs

- `.hermes-loop/god_dispatch.json`: phase `phase-3`, target `shadow-write`.
- `.hermes-loop/brainstorm.md`: recommends SQLite shadow-store + internal
  core-memory service over contract-only or legacy page/item reuse.
- `.hermes-loop/blueprint.md`: phase-3 tasks and acceptance criteria.
- `src/memoryos_lite/v3_contracts.py`: already defines `CoreMemoryBlock`,
  `CoreMemoryUpdate`, `MemoryHistoryEvent`, `SourceRef`, and `ApprovalState`.
- `src/memoryos_lite/store.py`: current SQLite store, Alembic stamping, and
  legacy page/item/episode persistence.
- `src/memoryos_lite/engine.py`: default context builder must remain unchanged.
- `tests/test_v3_contracts.py`: existing core-memory contract coverage.

## Non-Goals

- Do not change default `build_context()` behavior.
- Do not wire core memory into `ContextBuilder` or `RecallPipeline`.
- Do not add public API routes for core memory in this phase.
- Do not add automatic source-less core-memory writes.
- Do not invent a second public core-memory schema outside `v3_contracts.py`.
- Do not merge core memory with archival memory or recall memory.

## Design

### Contract Boundary

`v3_contracts.py` stays the canonical contract layer. Phase 3 may tighten
validators there, but it should not move the core-memory models into
`schemas.py`.

The existing `CoreMemoryBlock` model is the persisted block shape. Phase 3 may
extend it with soft-delete metadata (`deleted_at`, `deleted_by_event_id`) so the
store can hide deleted blocks by default while preserving audit history.

`CoreMemoryUpdate` remains the mutation contract for append / replace / update.
Delete is better represented as a service/store operation with explicit reason
and history fields than as a fake content update.

### Persistence Boundary

Add first-class SQLite records for:

- `core_memory_blocks`
- `core_memory_history`

The block record should persist:

- block id
- label
- description
- value
- limit tokens
- source refs
- metadata
- created / updated timestamps
- optional soft-delete metadata

The history record should persist:

- history id
- memory id
- memory type `core_block`
- operation
- actor
- reason
- source refs
- before snapshot
- after snapshot
- created timestamp

History is append-only. Every mutation writes one `MemoryHistoryEvent`.

### Mutation Semantics

Implement a small internal core-memory service, for example
`src/memoryos_lite/core_memory.py`, that owns behavior:

- create requires source refs or approved manual provenance.
- append concatenates onto the current value with a stable separator.
- update replaces the whole value.
- replace requires `old`, verifies it exists in the current value, and replaces
  the first exact match deterministically.
- delete soft-deletes the block and keeps it out of default reads.
- any mutation that would exceed `limit_tokens` is rejected instead of
  truncated.

Manual provenance must use the existing approval machinery, not a weaker custom
flag. The manual path must use `source_type="manual"` with a real non-empty
`approval_id`.

### Rendering

Add an explicit renderer, such as `render_core_memory_blocks(blocks) -> str`,
that formats blocks deterministically and is not called by default context
building.

Recommended output shape:

```text
[Core Memory]
- <label> (<limit_tokens> tokens)
  <description>
  <value>
```

Ordering should be deterministic: created time, then label, then id. Deleted
blocks should be skipped by default.

### Compatibility

`MemoryOSService.build_context()` stays as-is. The default legacy context path
must not pick up core memory automatically. The new service and renderer are
opt-in internal helpers for future composer work.

Fresh SQLite databases must be stamped to the new Alembic head that includes the
core-memory migration.

## Error Handling

- Missing block ids should raise `LookupError`.
- Invalid provenance or invalid mutation shape should raise `ValueError` or
  `ValidationError` at the contract boundary.
- Over-limit writes should raise `ValueError`.
- Replace should fail if `old` is absent from the current value.
- Deleted blocks should stay readable only through explicit `include_deleted`
  access in the store.

## Acceptance Criteria

- Blocks can be created, read, updated, and deleted.
- Update history is traceable in `core_memory_history`.
- Blocks persist limit, label, description, value, and source refs.
- Source-backed enforcement is tested.
- Render format exists but is opt-in only.
- Default `build_context()` output remains unchanged.
- Full test suite remains green.
