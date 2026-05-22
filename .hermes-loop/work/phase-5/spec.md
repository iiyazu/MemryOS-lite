# phase: phase-5

# Spec: Context Composer And Accounting

## Goal

Make the default v3 context path benchmark-usable by exposing component-level accounting, final-context trace metadata, and LoCoMo temporal/session neighbor diagnostics without changing v3 defaulting, v1 fallback, or kernel opt-in behavior.

## Context

This spec supersedes stale phase-5 lifecycle artifacts. It is based on `.hermes-loop/work/phase-5/context_bundle.md` and `.hermes-loop/work/phase-5/god_dispatch.json`.

Phase 4 left these facts:

- LongMemEval 30 full-chain v3: 17 pass / 13 fail.
- LoCoMo 30 full-chain v3: 0 pass / 30 fail.
- LoCoMo split: 11 retrieval miss, 10 context missing evidence, 9 evidence hit answer fail.
- Phase 4 archival totals were zero for public benchmark cases, so that phase proved diagnostic plumbing, not archive-quality improvement.

## Functional Requirements

1. `MemoryOSService.build_context()` on the v3 path must emit component accounting for:
   - `task`
   - `core`
   - `recall`
   - `archival`
   - `recent`
   - `kernel` or `tool` only when an opt-in kernel/tool trace exists downstream.

2. Each accounting row must include:
   - component/layer name;
   - item id;
   - flat source ids;
   - serialized source refs;
   - estimated token count;
   - included/dropped booleans;
   - reason code;
   - score when available;
   - rendered order when included in final context;
   - diagnostic metadata such as `benchmark_session_id`, `benchmark_date`, `neighbor_of`, and `neighbor_offset` when available.

3. Final-context trace metadata must distinguish:
   - retrieved candidate;
   - selected into `ContextPackageV3.items`;
   - dropped by budget;
   - rendered into legacy-compatible `ContextPackage.retrieved_evidence`, `pinned_core`, or `recent_messages`.

4. Public benchmark reports must expose the new metadata append-only:
   - existing fields remain present;
   - new fields are added without removing or renaming `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, `kernel_trace_events`, or `case_diagnostics`;
   - partial and final reports have schema parity.

5. Public case diagnostics must read selected evidence from:
   - `v3_context.metadata.final_context_trace`;
   - `v3_context.items[*].source_refs`;
   - `v3_diagnostics[*].source_refs`;
   - existing flat fallback fields.

6. LoCoMo temporal/session neighbor behavior must be testable with stable source ids:
   - selected recall evidence can include same-benchmark-session neighbors;
   - neighbor diagnostics record `neighbor_of`, offset, benchmark session id, and whether the neighbor was included or dropped;
   - same-session neighbors must not be silently lost before final-context trace generation.

7. Budget drops must be explicit:
   - dropped layer;
   - item id;
   - source id;
   - token count;
   - reason code;
   - whether the dropped item was relevant to expected evidence in public diagnostics when that can be derived.

## Non-goals

- Do not enable `MEMORYOS_AGENT_KERNEL` by default.
- Do not remove or weaken `MEMORYOS_MEMORY_ARCH=v1`.
- Do not tune LLM answer prompts as a Phase 5 success claim.
- Do not add benchmark case-id hacks, expected-answer leaks, or LoCoMo-specific string shortcuts.
- Do not rewrite broad retrieval ranking unless the LoCoMo neighbor RED test proves the current neighbor policy is the blocker.
- Do not claim benchmark improvement from small samples.

## Proposed Design

### Composer metadata

Add small helper methods in `src/memoryos_lite/context_composer.py`:

- `_source_ids(item: ContextLayerItem) -> list[str]`
- `_accounting_row(...) -> dict[str, object]`
- `_refresh_component_accounting(package: ContextPackageV3) -> None`

`_try_add_layer()` remains the point where inclusion/drop decisions are made. It should append diagnostics as today, then refresh package metadata after all layers are processed. The metadata keys should be:

- `component_accounting`
- `final_context_trace`
- `component_token_totals`
- `component_drop_counts`
- `component_included_counts`
- `locomo_neighbor_diagnostics`

The row shape is intentionally plain dict JSON to keep public report compatibility simple.

### Recall neighbor metadata

Use the existing `EpisodeHit.neighbor_of` and temporal scope instead of adding a new retriever. The narrow change is in:

- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`

The searcher should not add a benchmark neighbor from a different `benchmark_session_id` when both hit and neighbor have that metadata. The recall pipeline should carry `neighbor_of`, `neighbor_offset`, `benchmark_session_id`, and `benchmark_date` into `ContextEvidence.metadata`, then `V3ContextComposer._recall_items()` should carry the same metadata into `ContextLayerItem.metadata`.

### Engine and eval propagation

`src/memoryos_lite/engine.py` should copy v3 metadata into legacy-compatible `ContextPackage.metadata` and the `context_built` trace payload.

`src/memoryos_lite/evals.py` and `src/memoryos_lite/public_benchmarks.py` should expose append-only fields:

- `v3_component_accounting`
- `v3_final_context_trace`
- `v3_component_token_totals`
- `v3_component_drop_counts`
- `locomo_neighbor_diagnostics`

### Public diagnostics

`src/memoryos_lite/public_case_diagnostics.py` should flatten nested `source_refs` before classifying selected context. It should keep `source_hit_semantics = "final_projection_source_overlap"` and add diagnostic keys that compare expected evidence with selected/final-context trace ids.

## Acceptance Criteria

- Focused RED tests fail before implementation for selected evidence disappearing, budget-drop accounting, LoCoMo same-session neighbor diagnostics, v1 exclusion, and kernel default-off.
- The v3 service path emits new metadata through `MemoryOSService.build_context()`, not through a test-only helper.
- Public benchmark JSON exposes new fields per case and preserves old fields.
- `build_case_diagnostics()` can classify retrieval miss, context missing evidence, evidence hit answer fail, unsupported answer, and judge questionable using selected/rendered evidence separately.
- `MEMORYOS_MEMORY_ARCH=v1` reports no v3 component/final trace metadata.
- `MEMORYOS_MEMORY_ARCH=v3` remains the default.
- `MEMORYOS_AGENT_KERNEL` remains opt-in/default-off.
- Milestone eval reports LongMemEval and LoCoMo case-level outcomes separately, including fail-to-pass and pass-to-fail when a comparison report is available.
