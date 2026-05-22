# phase: phase-5

# Context Bundle - Phase 5

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Current Phase

- Phase id: `phase-5`
- Blueprint phase: `Context Composer And Accounting`
- Execute lane state: repeat from Phase 5 review failure. An earlier
  controller snapshot had drifted to Phase 8 without usable Phase 5 ACK
  evidence under the active goal; the live controller state is now reset to
  Phase 5 as the controlling execute lane until this
  bundle/result/review/ACK sequence completes.
- Target chain component: v3 `ContextComposer` packaging, per-component accounting, and public benchmark traceability.

## Why This Phase Exists Now

Phase 4 reached a usable archive/passage scope diagnostic gate, but it did not produce a benchmark-quality improvement claim. The Phase 4 milestone showed:

- LongMemEval 30 full-chain v3: 17 pass / 13 fail.
- LoCoMo 30 full-chain v3: 0 pass / 30 fail.
- LoCoMo failure classes: 11 retrieval miss, 10 context missing evidence, 9 evidence hit answer fail.
- Attached-archive benchmark totals were zero, so Phase 4 proved diagnostic plumbing, not archive-quality improvement.

Phase 5 exists to make the v3 context package explainable enough to trace every case from query to retrieval candidate to included/dropped component to final answerer input.

## Current Hypothesis

The most useful narrow Phase 5 improvement is not a broad composer rewrite. It is to make v3 component accounting and temporal/session neighbor handling explicit, so LoCoMo failures can be separated into:

- source never retrieved;
- source retrieved but dropped by component budget;
- source and required temporal/session neighbor retrieved but not rendered;
- evidence rendered but answer projection failed.

This hypothesis is disproved if focused tests show selected recall evidence and temporal neighbors already survive into `ContextPackage.metadata["v3_context"]` and public case diagnostics with clear component-level token/drop reasons.

## Scope

In scope:

- Add or tighten per-component context accounting for `task`, `core`, `recall`, `archival`, `recent`, and kernel/tool trace only when applicable.
- Add explicit inclusion/drop reasons and source ids for every v3 component item.
- Add query-to-evidence-to-final-context trace metadata usable by public benchmark diagnostics.
- Add a LoCoMo-shaped temporal/session RED test where selected evidence needs neighboring context.
- Preserve current public benchmark compatibility fields.

Non-goals:

- Do not enable `MEMORYOS_AGENT_KERNEL` by default.
- Do not change the default `v3` architecture or remove explicit `MEMORYOS_MEMORY_ARCH=v1`.
- Do not tune LLM answer prompts as a Phase 5 architecture claim.
- Do not add benchmark case-id or expected-answer hacks.
- Do not rewrite Hermes orchestration.
- Do not broadly redesign retrieval ranking unless a focused composer/accounting test proves it is needed.

## State Snapshot

Relevant controller values for this repeat:

```json
{
  "current_state": "GOD_DISPATCH",
  "current_phase_idx": 5,
  "execute_lane": {"phase": "phase-5", "state": "GOD_DISPATCH"},
  "plan_lane": {"phase": "phase-6", "state": "PLAN_STORM"},
  "research_lane": {"phases": ["phase-7"]},
  "review_lane": {"active": false, "phase": null},
  "phase-5": {"name": "Context Composer And Accounting", "status": "in_progress"}
}
```

State drift evidence found at repeat start:

- live `.hermes-loop/state.json` pointed to `current_phase_idx = 8`;
- `.hermes-loop/work/phase-5/reviews/codex-review-current.md` had `Verdict: FAIL`;
- `.hermes-loop/work/phase-5/review_fail_discussion_current.md` recommended repeating Phase 5;
- stale Phase 8 ACK evidence predates the active review-fail remediation and must not be used as a promotion gate.

## Active Blueprint Section

Phase 5 requires:

- split context into components: task, core memory, recall evidence, archival passages, recent messages, kernel/tool trace when applicable;
- per-component budgets and inclusion/drop reasons;
- token estimates per component;
- source-grounded evidence preferred over summaries;
- selected evidence surviving into answerer input;
- failing tests for evidence not silently disappearing, component budget drops, LoCoMo temporal/session neighboring context, and v1/v3/kernel constraints;
- 30-50 full-chain LongMemEval and LoCoMo milestone eval, with LoCoMo capped by local data if needed.

No promoted Phase 5 amendment exists yet.

## Superseded Phase-Local Artifacts

At repeat start, the following pre-existing phase-5 artifacts were stale
because they bound `phase-5` to an older "Memory Lifecycle + Promotion Policy"
phase and did not cite this context bundle:

- `work/phase-5/brainstorm.md`
- `work/phase-5/spec.md`
- `work/phase-5/plan.md`
- `work/phase-5/plan_final.md`
- `work/phase-5/result.md`
- `work/phase-5/execute_review.md`
- `work/phase-5/reviews/codex-review.md`
- `work/phase-5/ack.json`
- `work/phase-5/reflect_phase-5.md`

Lane agents must overwrite or supersede these files with current Phase 5
artifacts that cite this bundle. Files with the same names are usable only if
their first line is `# phase: phase-5` and they cite this context bundle or the
current active goal.

## Required MemoryOS Files

Read these before planning or executing:

- `src/memoryos_lite/config.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/v3_contracts.py`
- `tests/test_context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_engine.py`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`

## Required Letta Reference Files

Use `/home/iiyatu/projects/python/letta` only as a design reference:

- `letta/schemas/block.py`
- `letta/schemas/memory.py`
- `letta/schemas/archive.py`
- `letta/schemas/passage.py`
- `letta/services/block_manager.py`
- `letta/services/archive_manager.py`
- `letta/services/passage_manager.py`
- `letta/services/tool_executor/tool_execution_manager.py`
- `letta/services/tool_executor/core_tool_executor.py`
- `letta/agents/letta_agent_v3.py`
- `letta/services/context_window_calculator/context_window_calculator.py`

Borrow component/context accounting semantics where useful. Do not add Letta as a runtime dependency.

## Previous Evidence To Carry Forward

Phase 4 ACK: `work/phase-4/ack.json`.

Phase 4 review: `work/phase-4/reviews/codex-review.md` and `work/phase-4/review_verdict.json`.

Phase 4 reflection: `work/phase-4/reflect_phase-4.md`.

Concrete Phase 4 case-level findings:

- LongMemEval retrieval misses: `58bf7951`, `6ade9755`, `75499fd8`.
- LoCoMo retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- LoCoMo context missing evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- LoCoMo evidence hit answer fail: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`.

## Pass-To-Fail Risks

- `source_hit` can look stable while selected evidence or rendered evidence regresses.
- LoCoMo can stay 0/30 while LongMemEval looks acceptable; do not claim chain-level improvement from LongMemEval alone.
- `v3_context` item dumps can omit source ids in a shape that public diagnostics cannot read.
- Budget-dropped items must not appear as selected.
- Temporal questions can accidentally rely on raw recent-message bypass instead of the v3 final context trace.
- v1 fallback must not receive v3 diagnostics.
- Kernel traces must remain empty unless `MEMORYOS_AGENT_KERNEL=v1`.

## Starting RED Evidence

Before production changes, add or run a failing test for:

- selected recall evidence cannot silently disappear from final `v3_context`/public diagnostics;
- component-level budget drops include layer, item id, source id, token count, and reason;
- LoCoMo-shaped temporal/session evidence includes enough neighboring same benchmark-session context and records why;
- explicit v1 fallback excludes v3 diagnostics;
- kernel trace remains default-off.

## Expected Focused Verification

Guard command before depending on Phase 4 behavior:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Focused Phase 5 tests should include:

```bash
uv run pytest tests/test_context_composer.py tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail -q
```

Required baseline checks before ACK:

```bash
uv run pytest -q
uv run ruff check .
```

Mandatory milestone eval for usable ACK if Phase 5 changes public benchmark path behavior:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/public_20260521_213550_longmemeval.json --run-id phase5_repeat_20260522_1315_lme_30
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/public_20260521_214906_locomo.json --run-id phase5_repeat_20260522_1315_locomo_30
```

Run LongMemEval and LoCoMo milestone commands in parallel if both are required.

## Anti-Demo Completion Criteria

Phase 5 is usable only if:

- the real v3 `MemoryOSService.build_context()` path emits the new accounting/trace metadata;
- public benchmark reports consume or expose that metadata case by case;
- tests prove selected evidence cannot silently disappear from the final context trace;
- LoCoMo temporal/session neighbor behavior is tested with stable source ids;
- case-level eval reports fail-to-pass, pass-to-fail, retrieval miss, context missing evidence, evidence hit answer fail, and judge questionable separately;
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback;
- v3 remains default;
- kernel remains opt-in/default-off.
