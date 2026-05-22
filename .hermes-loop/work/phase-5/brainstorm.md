# phase: phase-5

# Brainstorm: Context Composer And Accounting

## Inputs Used

- Primary bundle: `.hermes-loop/work/phase-5/context_bundle.md`.
- Dispatch: `.hermes-loop/work/phase-5/god_dispatch.json`.
- Required MemoryOS files read: `src/memoryos_lite/config.py`, `src/memoryos_lite/context_composer.py`, `src/memoryos_lite/engine.py`, `src/memoryos_lite/public_benchmarks.py`, `src/memoryos_lite/public_case_diagnostics.py`, `src/memoryos_lite/retrieval/recall_pipeline.py`, `src/memoryos_lite/retrieval/episode_searcher.py`, `src/memoryos_lite/v3_contracts.py`, `tests/test_context_composer.py`, `tests/test_public_benchmarks.py`, `tests/test_engine.py`, `docs/public-benchmark-diagnosis.md`, `docs/known-issues.md`, and `docs/agentic-memory-roadmap-zh.md`.
- Letta reference read for design semantics: blocks/core memory, archive/passage managers, tool execution, agent v3 context loop, and `ContextWindowCalculator` token/component accounting. Letta is a reference only, not a runtime dependency.
- Phase 4 carry-forward: `.hermes-loop/work/phase-4/ack.json` and `.hermes-loop/work/phase-4/reflect_phase-4.md`.

## Current Problem

Phase 5 is not the older lifecycle/promotion scope. Existing phase-5 lifecycle artifacts are stale and are superseded by this document.

The active phase is v3 context composer accounting. Phase 4 proved scoped archival diagnostics and append-only public fields, but LoCoMo remained 0/30. The useful next step is not a broad retrieval rewrite or answer-prompt change. It is making the real v3 `MemoryOSService.build_context()` path explain exactly which source-bearing items were retrieved, included, dropped, and rendered into the final answerer input.

## Approach A: Metadata-first composer accounting

Add a compact accounting builder inside `V3ContextComposer` that emits:

- per-layer component accounting for `task`, `core`, `recall`, `archival`, `recent`, and kernel/tool trace only when present downstream;
- one final-context trace row per included or dropped item, with flat `source_ids`, `source_refs`, `estimated_tokens`, `reason_code`, `included`, `dropped`, `component`, and `rendered_index`;
- budget-drop diagnostics that can be read without reconstructing Pydantic models.

Tradeoffs:

- Low blast radius and fits existing `ContextPackageV3.metadata`, `LayerBudgetDecision`, and `DiagnosticEvent`.
- Does not create a richer typed contract yet; field shape must be tested carefully to avoid accidental public report churn.
- Best match for the active goal because public benchmark reports can consume the same metadata without changing default architecture or enabling kernel.

## Approach B: Formal accounting contracts in `v3_contracts.py`

Add typed models such as `ComponentAccountingEntry`, `FinalContextTraceEntry`, and `TemporalNeighborDiagnostic`, then make composer and public reports serialize those models.

Tradeoffs:

- Stronger internal schema and easier future validation.
- More files change and larger migration surface for a phase that should stay narrow.
- Risk of overbuilding before the benchmark diagnostics prove the exact shape needed.

## Approach C: Retrieval and answer-path rewrite

Rewrite recall ordering, context packing, and answer projection together so LoCoMo gets more evidence into answers.

Tradeoffs:

- Could improve benchmark pass rate if correct, but it violates the narrow Phase 5 scope.
- Higher overfitting risk because LoCoMo failures include retrieval misses, context missing evidence, and answer failures.
- Makes it harder to explain pass-to-fail regressions because accounting and behavior changes land together.

## Recommendation

Use Approach A, with one narrow retrieval-adjacent change only if the RED test proves the current neighbor policy is insufficient.

The implementation should:

- keep v3 as the default memory architecture and keep `MEMORYOS_MEMORY_ARCH=v1` as explicit fallback;
- keep `MEMORYOS_AGENT_KERNEL` default-off and only report kernel/tool trace when enabled by existing opt-in wiring;
- add component accounting and final-context trace metadata to the real v3 composer path;
- teach public diagnostics to read flat `source_ids` and nested `source_refs` from `v3_context`, `v3_diagnostics`, and the new final-context trace;
- add LoCoMo-shaped temporal/session neighbor diagnostics around benchmark session ids without case-id or answer-string rules.

## Risks

- Public `source_hit` can still look stable while selected or rendered evidence regresses; the plan must keep retrieval, selected context, rendered context, and answer support separate.
- LoCoMo may remain 0/30 after Phase 5. That is acceptable if case-level diagnostics make the bottleneck visible; it is not acceptable to hide LoCoMo behind LongMemEval.
- Existing `EpisodeSearcher` adds neighbors by MemoryOS session and position; LoCoMo benchmark sessions live in message metadata, so neighbor diagnostics must not accidentally cross `benchmark_session_id` boundaries.
- `v3_context` currently serializes nested `source_refs`; public diagnostics that only read flat ids can misclassify selected evidence as missing.
- Budget-dropped items must not be counted as selected/rendered. Dropped rows belong in diagnostics and accounting, not in final-context selected ids.

## Demo-only Completion

Phase 5 would be demo-only if any of these happen:

- metadata is produced by a synthetic test helper but not by `MemoryOSService.build_context()` on the v3 path;
- public benchmark JSON does not expose the new accounting and final-context trace per case;
- LoCoMo neighbor behavior is asserted only with generic recent-message bypass rather than v3 recall/final-context trace;
- selected evidence is inferred from aggregate `source_hit` instead of item-level source ids;
- kernel trace appears when `MEMORYOS_AGENT_KERNEL` is not set to `v1`;
- small 10-case or 30-case results are described as benchmark improvement without case-level fail-to-pass and pass-to-fail evidence.
