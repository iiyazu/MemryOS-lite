# phase: phase-3

## Spec: Letta-Style Core Memory Blocks

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

This spec uses `.hermes-loop/work/phase-3/context_bundle.md` as the required handoff source. The existing phase-3 result/ack artifacts are stale inventory only.

## Objective

Phase 3 makes core memory blocks structured, bounded, auditable, and visible in the real MemoryOS v3 context path:

```text
SQLite store -> CoreMemoryService/contracts -> V3ContextComposer -> MemoryOSService.build_context() -> public benchmark diagnostics
```

It must not change answer projection, add benchmark-specific writes, change archive/passage scope, enable the v3 kernel by default, or alter explicit v1 fallback behavior.

## Letta Semantics To Borrow

Use Letta as a semantic reference only. Do not add Letta as a runtime dependency.

Core block contract:

- `label`: required non-empty context label such as `human`, `persona`, or `profile`.
- `value`: current block text.
- `limit_tokens`: positive MemoryOS token budget limit for `value`.
- `description`: required audit description of the block purpose.
- `read_only`: default `False`; when `True`, agent/service edit/delete APIs must reject mutation.
- `tags`: default empty list; persisted and rendered for grouping/audit.
- `metadata`: default empty dict; persisted and rendered for audit.
- `source_refs`: source-backed provenance for current block value.
- `deleted_at` and `deleted_by_event_id`: soft-delete state.

Rendering semantics:

- Core memory must render as a structured component, not plain `label: value`.
- Rendered text must expose label, description, tags, metadata, read-only state, source refs, current token count, token limit, and value.
- Rendering must exclude soft-deleted blocks.
- Rendering order must remain deterministic by `created_at`, then `label`, then `id`.

Mutation semantics:

- Source-less core writes remain rejected unless an approved manual provenance contract is present.
- Create/update/append/replace/delete must require actor and reason.
- Create/update/append/replace must reject values whose token count exceeds `limit_tokens`.
- Read-only blocks must reject append, replace, full update, and delete through `CoreMemoryService`.
- Store-level CRUD may remain low-level, but service-level contract tests must cover user-facing mutation protection.

History semantics:

- Create records an `add` history event with `after`.
- Append and full update record `update` history events with `before` and `after`.
- Replace records a `replace` history event with `before` and `after`.
- Delete records a `delete` history event with `before`, no `after`, and soft-delete fields.
- History snapshots must preserve `read_only`, `tags`, `metadata`, `source_refs`, and limit fields.

## Storage Contract

`src/memoryos_lite/store.py` remains SQLite authoritative. Filesystem/debug mirrors remain non-authoritative.

Required storage shape:

- Add `read_only` boolean storage for `core_memory_blocks`.
- Add `tags_json` text storage for `core_memory_blocks`.
- Preserve existing `metadata_json` and `source_refs_json`.
- Add an Alembic revision after `0006_add_archival_memory` to add these fields with backwards-compatible defaults:
  - `read_only`: false for existing rows.
  - `tags_json`: `[]` for existing rows.
- Update local DB stamping logic and migration-head tests to the new revision.

## Service Contract

`src/memoryos_lite/core_memory.py` owns high-level core block behavior.

Required APIs:

- `CoreMemoryService.create_block(...)` accepts optional `read_only: bool = False`, `tags: list[str] | None = None`, and `metadata: dict[str, object] | None = None`.
- Existing callers that omit those fields keep current behavior.
- `append_block`, `replace_block`, `update_block`, and `delete_block` reject read-only blocks with a stable `ValueError` message containing `read-only core memory block`.
- Limit enforcement remains reject-on-over-limit, not silent truncation.
- Provenance enforcement remains `source_refs` or approved `ApprovalState`.

## Renderer Contract

`render_core_memory_blocks(blocks, tokenizer)` or an equivalent focused renderer must produce structured text and structured diagnostics without depending on the v3 composer.

Required structured text fields:

- `<memory_blocks>` container.
- One nested block per active core block.
- A visible label marker.
- `<description>...</description>`.
- `<metadata>` with `read_only`, `tokens_current`, `tokens_limit`, `tags`, and user metadata.
- `<sources>` with source type and source id for each source ref.
- `<value>...</value>`.

Required diagnostic payload for each rendered block:

- `label`
- `description`
- `read_only`
- `tags`
- `metadata`
- `tokens_current`
- `tokens_limit`
- `source_refs`
- `source_ref_count`
- `reason = core_memory_block`

## V3 Context Composer Contract

`src/memoryos_lite/context_composer.py` must consume the structured renderer in the existing real v3 path.

Required behavior:

- `_core_items()` returns core `ContextLayerItem`s whose `text` is structured render text, not plain `label: value`.
- Each core item includes source refs and diagnostics metadata from the renderer.
- Core layer budget decisions include requested/used/dropped tokens as they do today.
- Core diagnostics use layer `core`, reason `core_memory_block`, and include token cost and block metadata.
- If core blocks exceed the caller budget, they may be dropped by the existing layer budget logic, but the drop must appear in `v3_budget_decisions` and `v3_diagnostics`.

## Engine And Public Benchmark Contract

`MemoryOSService.build_context()` must preserve existing routing:

- Default `MEMORYOS_MEMORY_ARCH=v3` routes to `V3ContextComposer`.
- Explicit `MEMORYOS_MEMORY_ARCH=v1` routes to the legacy path and must not render v3 core blocks.
- `MEMORYOS_AGENT_KERNEL` remains default `off`; normal v3 context must not require kernel opt-in.

The public benchmark report contract is append-only:

- Preserve `v3_layer_counts`.
- Preserve `v3_budget_decisions`.
- Preserve `v3_diagnostics`.
- Preserve retrieval/source metrics semantics; core memory source refs must not inflate retrieval-only metrics such as planned evidence source-hit.
- When core blocks exist in the real v3 path, the report must expose core layer inclusion and cost through existing v3 diagnostics fields or append-only extra keys.

## Non-Goals

- No answer prompt tuning.
- No automatic benchmark core-memory writes.
- No benchmark case-id rules, expected-answer leaks, or dataset hacks.
- No archive/passage scope changes beyond existing code.
- No kernel default change.
- No Letta runtime dependency.
- No broad Hermes infrastructure rewrite.

## Acceptance Criteria

Phase 3 is usable only if all are true:

- Contract tests prove `read_only`, `tags`, metadata, source refs, limit enforcement, and history persistence.
- Structured core render is tested directly.
- Real `V3ContextComposer` includes structured core blocks and records token/budget diagnostics.
- Real `MemoryOSService.build_context()` includes core diagnostics on v3 and excludes v3 core blocks on explicit v1 fallback.
- Public benchmark diagnostics preserve existing v3 keys and expose core layer inclusion/cost when present.
- `MEMORYOS_AGENT_KERNEL` remains default-off and not required by v3 context.
- 10-case LongMemEval and LoCoMo no-LLM smokes are run with `MEMORYOS_MEMORY_ARCH=v3`.
- Smoke reporting is case-level and lists regressions or states that no comparison baseline was available.
- No source-less automatic memory writes are introduced.
- Review checks source grounding, overfitting risk, v1 fallback, v3 default, kernel default, and anti-demo completion.
