# phase: phase-3

## Context Used

I used `.hermes-loop/work/phase-3/context_bundle.md` as the starting handoff before reading other phase-local artifacts. I then read `.hermes-loop/work/phase-3/god_dispatch.json`, the active blueprint/state excerpts, the listed MemoryOS source/tests/docs, and the Letta reference files needed for Phase 3 semantics.

The existing `.hermes-loop/work/phase-3/result.md`, `.hermes-loop/work/phase-3/ack.json`, and related phase-3 ack/review artifacts are stale under the active-goal contract. They should be treated as implementation inventory only, not usable completion evidence.

## Current Read

Phase 3 is not a greenfield feature. MemoryOS already has `CoreMemoryBlock`, `CoreMemoryService`, SQLite store/history, and v3 composer inclusion. The remaining gap is whether those pieces satisfy the active Letta-style contract on the real v3/public benchmark path:

- `CoreMemoryBlock` currently has label, description, value, token limit, source refs, metadata, and soft delete fields.
- It does not yet expose first-class `read_only` or `tags` fields like Letta `Block`.
- The service enforces source refs or approved manual provenance and enforces token limits.
- The service does not visibly enforce read-only edit/delete protection because the contract field is absent.
- `V3ContextComposer._core_items()` includes core blocks, but renders them as `label: value` and only puts label/description in metadata.
- Existing `tests/test_engine.py::test_build_context_ignores_core_memory_blocks` is stale under the active blueprint and should be replaced by explicit v3 inclusion plus v1 fallback isolation tests.
- Public benchmark diagnostics already carry `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics`; Phase 3 needs core-specific visibility without changing those fields destructively.

Letta semantics to borrow are semantic, not runtime dependency:

- Block shape: label, value, limit, description, read_only, metadata, tags.
- Rendering: structured `<memory_blocks>` style output with description, metadata, read-only marker, current/limit accounting, and value.
- Edit invariants: read-only blocks reject core memory append/replace/patch/update operations.
- Context accounting: core memory is a named component with token/cost visibility.

## Implementation Options

### Option 1: Minimal contract completion in current core path

Add first-class `read_only` and `tags` to `CoreMemoryBlock`, store/migration support, service create/update handling, and read-only checks in append/replace/update/delete. Replace plain core text rendering with a structured renderer reused by `V3ContextComposer._core_items()`. Extend composer diagnostics metadata for core items with label, description, tags, metadata, read_only, limit/current token count, and source refs. Keep public benchmark schema append-only by preserving existing `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics` while making core diagnostics visible inside those structures.

Tradeoffs:

- Lowest blast radius and best fit for Phase 3.
- Directly targets active ACK requirements.
- Does not solve answer quality, LoCoMo recall gaps, archive scope, or kernel behavior.
- Requires a schema migration and compatibility care for existing SQLite rows.

### Option 2: Add a dedicated core block render contract object

Introduce a small `CoreMemoryRender` or `CoreMemoryContextItem` contract that separates storage from context rendering. The service/store remain mostly unchanged except for read_only/tags, while the composer calls a renderer that returns structured text plus diagnostics payload. Tests assert renderer output independently and then assert composer/public benchmark propagation.

Tradeoffs:

- Cleaner boundary and easier tests for structured context.
- Reduces future coupling if core rendering evolves toward Letta XML-like memory blocks.
- Slightly more design surface than Option 1.
- Still requires the same schema/read-only work, so it is not materially cheaper.

### Option 3: Phase 3 plus public benchmark seed core blocks

In addition to Option 1/2, add benchmark ingestion heuristics that automatically promote stable facts into core blocks during LongMemEval/LoCoMo public eval runs.

Tradeoffs:

- Might affect benchmark behavior sooner.
- High risk of source-less or heuristic writes, benchmark overfitting, and demo-only completion.
- Increases pass-to-fail risk by consuming context budget before recall evidence.
- Violates the Phase 3 non-goal unless every write is source-backed, audited, and case-level safe.

## Recommended Route

Use Option 2 as a narrow implementation shape, with Option 1-level scope. That means: add the missing Letta-style block fields and enforcement, create/update the structured renderer as a testable boundary, wire that renderer into the existing real v3 composer, and expose core layer inclusion/cost through existing v3 diagnostics.

Do not do Option 3 in Phase 3. Phase 3 should make core memory usable, bounded, auditable, and visible. It should not add automatic benchmark memory-writing behavior or answer-prompt tuning. Benchmark smokes should validate that the real v3 path remains diagnosable and does not hide pass-to-fail movement.

## RED Tests Before Production Changes

Create or update RED tests before code changes:

- `tests/test_v3_contracts.py`: `CoreMemoryBlock` accepts/defaults `read_only=False` and `tags=[]`; serialized model preserves tags/read_only/source refs/metadata.
- `tests/test_core_memory_store.py`: SQLite round trip preserves `read_only` and `tags`; history before/after snapshots include them; soft delete remains source-backed.
- `tests/test_core_memory_service.py`: read-only block cannot be appended, replaced, fully updated, or deleted without an explicit allowed contract; source-less writes still fail; over-limit create/update remains rejected by documented token-limit behavior.
- `tests/test_core_memory_service.py` or a new focused renderer test: structured core render includes label, description, tags, metadata, read_only, source refs, current/limit token count, and value.
- `tests/test_context_composer.py`: v3 composer includes core layer items using structured render and emits diagnostics with core label, description, tags/metadata, source refs, and token budget cost.
- `tests/test_engine.py`: replace stale `test_build_context_ignores_core_memory_blocks` with two tests: v3 `build_context()` includes core diagnostics when blocks exist, and explicit `MEMORYOS_MEMORY_ARCH=v1` fallback does not include v3 core blocks.
- `tests/test_public_benchmarks.py`: public benchmark reports preserve append-only `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics`; when core blocks exist in the path, core layer inclusion/cost is visible without polluting retrieval-only metrics.
- Add or update a kernel default test if needed: default settings remain `MEMORYOS_AGENT_KERNEL=off`; kernel diagnostics appear only when explicitly opted in.

If an existing test already passes after being updated to the active contract, record it as verification rather than changing behavior.

## Preservation Requirements

- Preserve v3 as the default memory architecture: `MEMORYOS_MEMORY_ARCH=v3`.
- Preserve explicit v1 fallback: `MEMORYOS_MEMORY_ARCH=v1` must route through the legacy context path and must not render v3 core blocks.
- Preserve kernel opt-in: `MEMORYOS_AGENT_KERNEL=v1` must remain explicit and must not become required for normal v3 context building.
- Preserve SQLite as the authoritative store; filesystem/debug outputs remain mirrors.
- Preserve public benchmark report compatibility by adding diagnostic detail inside existing fields or append-only fields, not by renaming/removing current report keys.

## Demo-Only Or Partial Risks

- Tests only cover `CoreMemoryService` while `MemoryOSService.build_context()` or public eval still misses core diagnostics.
- Core blocks render as plain `label: value` without description, tags/metadata, source refs, or budget cost.
- Read-only exists as a field but append/replace/update/delete paths ignore it.
- Over-limit content is silently accepted or truncated without a documented contract and diagnostics.
- Source-less automatic core writes are introduced to improve benchmark cases.
- Public benchmark reports show aggregate improvement but omit case-level pass-to-fail, retrieval miss, evidence-hit-answer-fail, or LoCoMo-specific movement.
- Core memory consumes budget and drops recall evidence without `v3_budget_decisions` and `v3_diagnostics` explaining the drop.
- `MEMORYOS_MEMORY_ARCH=v1` starts including v3 core blocks, or the v3 kernel becomes default/required.

## Verification Shape For Execute Lane

Focused RED/green tests first:

```bash
uv run pytest tests/test_v3_contracts.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py tests/test_engine.py -q
```

Full verification after implementation:

```bash
uv run pytest -q
uv run ruff check .
```

Phase 3 benchmark smoke, no LLM answer/judge:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge
```

The result should report case-level diagnostics and explicitly list regressions or state that no comparison baseline was supplied. No Phase 3 ACK should be accepted from aggregate-only smoke output.
