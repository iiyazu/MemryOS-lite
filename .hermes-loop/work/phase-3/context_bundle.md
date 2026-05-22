# phase: phase-3

# Context Bundle - Phase 3 Letta-Style Core Memory Blocks

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Phase Objective

Phase 3 must make core memory blocks structured, bounded, auditable, and visible in the real MemoryOS v3 context composer path. It targets the `core` chain component: store -> core block service/contracts -> v3 context composer -> public benchmark diagnostics.

This phase exists now because Phase 2 made public benchmark failures diagnosable but did not change benchmark behavior. Phase 2 evidence showed weak full-chain results and many failures classified as `context_missing_evidence` or `unsupported_answer`, so later phases need auditable context components before answer projection work.

## Current Hypothesis

Hypothesis: Letta-style core memory blocks can be safely added to the real v3 context path as bounded, source-backed context components without changing v1 fallback or enabling the v3 kernel by default.

Disconfirming evidence:

- core blocks can be written without source refs or approved provenance;
- read-only blocks can be edited;
- over-limit blocks enter context without rejection or recorded truncation;
- v3 context packages omit core block description/metadata/source refs from diagnostics;
- explicit `MEMORYOS_MEMORY_ARCH=v1` includes v3 core blocks;
- public benchmark diagnostics cannot expose core layer inclusion or cost;
- any benchmark smoke hides pass-to-fail or LoCoMo regressions;
- `MEMORYOS_AGENT_KERNEL=v1` becomes default or required for normal v3 context.

## Scope

In scope:

- `CoreMemoryBlock` contract alignment with Letta `Block` semantics: label, value, limit, description, read_only, tags/metadata, source refs, delete state.
- Source-backed create/update/delete history.
- v3 composer structured rendering for core blocks, with source refs, description, metadata/tags, and token/budget diagnostics.
- Tests proving read-only enforcement, limit enforcement, structured render, v1 fallback isolation, and v3/public diagnostic visibility.
- 10-case LongMemEval and LoCoMo no-LLM diagnostic smoke through `MEMORYOS_MEMORY_ARCH=v3`.

Non-goals:

- no answer-prompt tuning;
- no benchmark case-id or expected-answer hacks;
- no archive/passage scope changes beyond what existing code already exposes;
- no kernel default change;
- no Letta runtime dependency;
- no broad Hermes infrastructure rewrite.

## State Excerpt

Root state:

```json
{
  "current_state": "GOD_DISPATCH",
  "current_phase_idx": 3,
  "execute_lane": {"phase": "phase-3", "state": "GOD_DISPATCH"},
  "plan_lane": {"phase": "phase-4", "state": "PLAN_STORM"},
  "research_lane": {"phases": ["phase-5"]},
  "review_lane": {"active": false, "phase": null}
}
```

Phase status:

- phase-0, phase-1, phase-2 have usable ACKs under the active goal.
- phase-3 is `in_progress`.
- Existing phase-3 `god_dispatch.json`, `result.md`, and `ack.json` are stale because they do not cite this context bundle or satisfy the active ACK schema.

## Active Blueprint Section

Use `.hermes-loop/blueprint.md`, especially:

- Hard Constraints.
- Context Bundle Requirement.
- Full-Chain LLM Judge Gates.
- Letta Comparison Map.
- Phase 3 - Letta-Style Core Memory Blocks.
- Stop Conditions.

Phase 3 required work from the active blueprint:

- align `CoreMemoryBlock` behavior with Letta `Block` semantics;
- render core memory as structured context, not plain `label: value` only;
- enforce read-only and limit behavior;
- preserve source-backed update history;
- ensure v3 composer consumes the structured render.

Phase 3 usable ACK requires:

- blocks wired into the real v3 context composer;
- no source-less automatic memory writes;
- context diagnostics expose block inclusion and token/budget cost.

## Read First - MemoryOS

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `docs/known-issues.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/agentic-memory-roadmap-zh.md`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/core_memory.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/public_benchmarks.py`
- `tests/test_v3_contracts.py`
- `tests/test_core_memory_store.py`
- `tests/test_core_memory_service.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`
- `tests/test_public_benchmarks.py`

## Read First - Letta Reference

Read these for semantics only. Do not add Letta as a runtime dependency.

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

## Relevant Previous Artifacts

- `.hermes-loop/work/phase-2/context_bundle.md`
- `.hermes-loop/work/phase-2/result.md`
- `.hermes-loop/work/phase-2/ack.json`
- `.hermes-loop/work/phase-2/reviews/codex-review.md`
- `.hermes-loop/work/phase-3/god_dispatch.json` (stale; old contract)
- `.hermes-loop/work/phase-3/result.md` (stale; useful only as implementation inventory)
- `.hermes-loop/work/phase-3/ack.json` (stale; not usable under active ACK contract)

## Current Baseline And Case-Level Findings

Phase 2 milestone evidence:

- LongMemEval 30 full-chain LLM judge: `18 pass / 12 fail`.
- LongMemEval retrieval miss: `58bf7951`, `6ade9755`, `75499fd8`.
- LongMemEval context missing evidence: `e47becba`, `118b2229`, `58ef2f1c`, `5d3d2817`, `7527f7e2`, `94f70d80`, `66f24dbb`, `af8d2e46`, `c8c3f81d`, `8ebdbe50`, `0862e8bf`, `853b0a1d`.
- LongMemEval unsupported answer: `51a45a95`, `1e043500`, `c5e8278d`, `6f9b354f`, `f8c5f88b`, `c960da58`, `3b6f954b`, `726462e0`, `ad7109d1`, `dccbc061`, `6b168ec8`, `21436231`, `95bcc1c8`, `a06e4cfe`, `37d43f65`.
- LoCoMo 30 full-chain LLM judge: `7 pass / 23 fail`.
- LoCoMo retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- LoCoMo context missing evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- LoCoMo unsupported answer: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`.
- Phase 2 did not claim benchmark improvement.

Recent code inspection:

- `src/memoryos_lite/core_memory.py` and store methods exist.
- `V3ContextComposer._core_items()` currently emits core layer items.
- Existing `tests/test_engine.py::test_build_context_ignores_core_memory_blocks` appears stale under the active blueprint and must be replaced with explicit v1 fallback isolation plus v3 inclusion checks.
- `CoreMemoryBlock` currently needs verification against read-only and tags requirements.

## Pass-To-Fail Risks

- v1 fallback starts rendering core blocks by accident.
- Existing public benchmark report schema changes instead of append-only diagnostics.
- Core memory source refs pollute retrieval/source-hit metrics.
- Core memory inclusion consumes budget and drops recall evidence without diagnostics.
- LoCoMo failures remain unexplained while LongMemEval smoke looks better.
- Tests pass only through service-level APIs while public benchmark path still ignores core diagnostics.

## RED Evidence To Start From

Before production changes, add failing tests or update existing tests for:

- read-only core block cannot be edited, deleted, or replaced without an explicit allowed contract;
- over-limit block create/update is rejected or safely truncated by documented contract;
- structured core render includes label, description, tags/metadata, source refs, and token cost;
- v3 `build_context()` includes core layer diagnostics when blocks exist;
- explicit v1 fallback does not include v3 core blocks;
- public benchmark diagnostics preserve `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics` with append-only schema.

If current implementation already passes any of these, record the command as verification rather than modifying behavior.

## Expected Commands

Focused tests first:

```bash
uv run pytest tests/test_v3_contracts.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py tests/test_engine.py -q
```

Required baseline checks:

```bash
uv run pytest -q
uv run ruff check .
```

Phase 3 smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Full-chain LLM judge is optional for Phase 3 unless answer path behavior changes.

## Anti-Demo Completion Criteria

Usable means:

- implementation is wired into real MemoryOS v3 `build_context()` and public benchmark diagnostics;
- tests cover contracts and fallback isolation;
- smoke reports are case-level and list regressions or explain why no comparison baseline is available;
- no source-less automatic core writes exist;
- no kernel default change exists;
- review confirms this result aligns with the active goal.

Plan-only, demo-only, or partial results must not be ACKed.

## Constraints To Preserve

- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and must not become default.
- SQLite remains authoritative; filesystem output remains a debug/report mirror.
