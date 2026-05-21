# PLAN_STORM Brainstorm — Phase 3 Core Memory Blocks

## Inputs Read

- `.hermes-loop/god_dispatch.json`: phase-3 requires Letta-style core blocks, history, append / replace / update semantics, render format, opt-in/internal only, and source-backed enforcement.
- `.hermes-loop/state.json`: current state is `PLAN_STORM`, current phase is `phase-3`.
- `.hermes-loop/contracts/state_machine.json`: `PLAN_STORM` output is `.hermes-loop/brainstorm.md`; next state is `PLAN_DRAFT`.
- `.hermes-loop/blueprint.md`: Phase 3 target state is `shadow-write`; legacy context must not become v3 by default.
- `CLAUDE.md` / `AGENTS.md`: default recall path remains `v1`; v2 remains opt-in; SQLite is authoritative; filesystem outputs are debug mirrors.
- `src/memoryos_lite/v3_contracts.py`: already defines `CoreMemoryBlock`, `CoreMemoryUpdate`, `MemoryHistoryEvent`, `SourceRef`, `ApprovalState`, and v3 future table names.
- `src/memoryos_lite/store.py`: SQLite store currently has records and CRUD for sessions, messages, episodes, pages, items, patches, and traces; no core-memory tables or CRUD yet.
- `src/memoryos_lite/engine.py`: service facade owns ingest/context/search flows; default context routing should remain untouched.
- `tests/test_v3_contracts.py`: source-ref and core-update validation already exist at contract level; persistence and operation semantics are not yet covered.

## Current Shape

Phase 1 already established v3 contracts, so Phase 3 should not invent a second core-memory schema in `schemas.py`. The missing layer is the shadow-write implementation boundary:

- persistent core-memory blocks,
- persistent history events,
- operation semantics for create / append / replace / update / delete,
- a renderer that can be called explicitly later by the v3 composer,
- tests proving source-backed enforcement and traceability.

The safest phase boundary is internal/store-level APIs plus focused service helpers. Do not inject rendered core memory into `MemoryOSService.build_context()` yet.

## Option A — Contract-Only Expansion

Extend `v3_contracts.py` with stricter validators and helper functions, but avoid new SQLite tables in this phase.

Expected implementation:

- Add validators such as `CoreMemoryUpdate.operation == "replace"` requiring `old`.
- Add pure helpers for append / replace / update and render formatting.
- Keep all tests in `tests/test_v3_contracts.py`.

Pros:

- Very low regression risk.
- Minimal surface area.
- Fast to implement and review.

Cons:

- Fails the phase acceptance that blocks can be created, read, updated, and deleted.
- History would not be durable.
- Does not achieve `shadow-write`; it remains contract-only.

Verdict: reject. Useful as part of the implementation, but insufficient for Phase 3.

## Option B — Recommended: SQLite Shadow Store + Internal Core Service

Add first-class shadow-write persistence for core blocks and history, using the existing SQLite store pattern and v3 contract models.

Expected implementation:

- Add SQLAlchemy records in `src/memoryos_lite/store.py`:
  - `CoreMemoryBlockRecord` for `core_memory_blocks`.
  - `CoreMemoryHistoryRecord` for `core_memory_history`.
- Add Alembic migration `0005_add_core_memory.py`, and stamp fresh local DBs to the new head only when creating a fresh DB.
- Add store CRUD:
  - `create_core_memory_block(block)`
  - `get_core_memory_block(block_id)`
  - `list_core_memory_blocks(session_id=None, include_deleted=False)`
  - `update_core_memory_block(block)`
  - `delete_core_memory_block(block_id, source_refs, actor, reason)`
  - `append_core_memory_history(event)`
  - `list_core_memory_history(block_id)`
- Add a small internal module, for example `src/memoryos_lite/core_memory.py`, that owns semantics:
  - create requires non-empty `source_refs` or explicit manual provenance via `SourceRef(source_type="manual", approval_id=...)`.
  - append adds content to existing value with stable separator.
  - replace requires `old`, verifies the old text exists, and replaces it.
  - update sets the full block value to the supplied content when the caller has source refs or approved manual provenance.
  - delete marks the block deleted or removes it while preserving history; soft delete is safer for audit.
  - every mutation writes `MemoryHistoryEvent` with before / after snapshots.
- Add render helper:
  - explicit method such as `render_core_memory_blocks(blocks) -> str`.
  - deterministic format, e.g. `[Core Memory]\n<label> (<limit>): <value>`.
  - not called from default `build_context()`.
- Add tests:
  - store-level CRUD and history roundtrip.
  - append / replace / update semantics.
  - delete keeps traceable history.
  - source-less create/update fails.
  - render format is deterministic and opt-in.
  - legacy `build_context()` output is unchanged unless an explicit future v3 hook calls the renderer.

Pros:

- Directly satisfies Phase 3 acceptance.
- Keeps v1/v2 behavior stable because APIs are internal/opt-in.
- Reuses existing `v3_contracts.py` models instead of duplicating schema.
- Creates a durable foundation for Phase 5 promotion policy and Phase 6 composer.
- Review can verify behavior with deterministic tests, no LLM required.

Cons:

- Adds migration and store surface area.
- Requires careful JSON serialization for `SourceRef` / history snapshots.
- Soft-delete design must be explicit so deleted blocks do not render later.

Verdict: recommended. This is the smallest implementation that actually reaches `shadow-write`.

## Option C — Reuse Legacy MemoryPage / MemoryItem as Core Blocks

Represent core memory through existing `MemoryPage(page_type=CORE_PROFILE)` and `MemoryItem` records, then add thin wrappers.

Expected implementation:

- Create core blocks as `MemoryPage` or `MemoryItem`.
- Use existing page/item CRUD and trace events for audit.
- Render from `list_global_core_pages()` or page summaries.

Pros:

- No migration needed.
- Lower immediate implementation cost.
- Existing retrieval/search code can see the data.

Cons:

- Violates the v3 direction that Page/Item are legacy archival inputs, not new v3 targets.
- Audit history would be ad hoc and incomplete.
- Source refs are weaker because `MemoryItem` only stores source message IDs.
- Raises risk that core pages accidentally leak into legacy context/retrieval.
- Makes later archival/core separation harder.

Verdict: reject. It saves time now but works against the blueprint.

## Recommendation

Choose Option B.

Design the Phase 3 plan around a narrow shadow-write slice:

1. Strengthen v3 core-memory contracts only where needed for unambiguous semantics.
2. Add durable SQLite tables and migration for core blocks and core history.
3. Add store CRUD and a small internal core-memory service for operation semantics.
4. Add deterministic render formatting, but keep it out of default context building.
5. Prove source-backed enforcement and history traceability with focused tests.

## Key Design Decisions for PLAN_DRAFT

- Source-backed enforcement should live in both contracts and service/store entry points. Pydantic validation catches invalid `CoreMemoryUpdate`; service methods should also reject source-less block creation.
- Manual provenance should use existing `SourceRef(source_type="manual", approval_id=...)` or an approved `ApprovalState`; do not invent a weaker `manual=True` flag.
- History should use `MemoryHistoryEvent(memory_type="core_block")` for every create/update/delete. For create, use operation `add`; for append/update, use `update`; for replace, use `replace`; for delete, use `delete`.
- Prefer soft delete with `deleted_at` / `deleted_by_event_id` metadata or columns so audit survives and render/list defaults can hide deleted blocks.
- Keep `CoreMemoryBlock` in `v3_contracts.py` for this phase rather than moving it into `schemas.py`; `schemas.py` remains legacy/public API until v3 is promoted.
- Add no automatic LLM extraction, promotion, or default composer integration in Phase 3. Those belong to later phases.

## Risks

- Migration stamping risk: fresh DB stamping must move to the new head without breaking existing Alembic upgrades.
- Token-limit semantics: `limit_tokens` exists, but enforcing exact token budgets may require `TokenEstimator`. The implementation plan should either enforce via existing estimator or explicitly cap by estimated tokens in service tests.
- Replace ambiguity: plan should require `old` for replace and fail if `old` is not found, avoiding silent full-block replacement.
- Delete semantics: hard delete would satisfy CRUD but weaken traceability. Soft delete is better for this phase.
- API exposure risk: adding FastAPI endpoints now may imply public behavior. Keep this internal unless the spec explicitly opts into API routes.

## Acceptance Mapping

- Blocks can be created, read, updated, and deleted: Option B store/service CRUD tests.
- Update history is traceable: `core_memory_history` table plus `list_core_memory_history(block_id)` tests.
- Blocks have limit, label, description, value, and source refs: `CoreMemoryBlockRecord` roundtrip tests.
- Source-backed enforcement is tested: source-less create/update tests and manual provenance tests.
- Render format exists without default legacy context: renderer unit test plus legacy `build_context()` regression test.
