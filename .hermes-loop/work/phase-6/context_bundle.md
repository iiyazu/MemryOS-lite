# phase: phase-6

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase 6 is **Answer Projection And Citation Contract**. Its target chain component is the retrieval-to-answer boundary in the real MemoryOS Lite v3 public benchmark path.

The phase exists now because Phase 5 made final-context trace and component accounting visible, then full-chain 30-case reports still showed answer grounding weakness:

- LongMemEval: `18/30`, no fail-to-pass, no pass-to-fail, `unsupported_answer=30`, `retrieval_miss=3`, `context_missing_evidence=12`.
- LoCoMo: `7/30`, no fail-to-pass, no pass-to-fail, `unsupported_answer=30`, `retrieval_miss=11`, `context_missing_evidence=10`.

Phase 6 must not claim benchmark improvement from a prompt tweak. It must create a testable answer evidence contract: answers cite selected evidence IDs or explicitly refuse as unsupported.

## Current Hypothesis

Hypothesis: a large part of current public-benchmark weakness is that selected/rendered evidence is not projected into answers with durable citation IDs, so LLM and deterministic projected answers are classified as unsupported even when evidence is present.

Disconfirming evidence:

- selected/rendered evidence with valid source IDs is still not enough to reduce or explain unsupported/evidence-hit-answer-fail cases;
- LoCoMo regressions or unexplained failures appear after citation changes;
- citations can refer to IDs not present in selected/rendered evidence;
- deterministic no-LLM diagnostics lose retrieval/context failure separation.

## Scope

In scope:

- structured evidence input for the public LLM answerer;
- citation contract for deterministic projected public benchmark answers;
- diagnostics that distinguish missing citations, unsupported citations, explicit no-evidence refusal, judge-questionable cases, and evidence-hit-answer-fail;
- focused tests that fail before implementation;
- milestone LongMemEval and LoCoMo full-chain LLM judge reports, run in parallel when both are required.

Non-goals:

- no default kernel enablement;
- no Letta runtime dependency;
- no benchmark case-id hacks or expected-answer leakage;
- no storage or retrieval rewrite unless a failing test proves the answer contract cannot be wired otherwise;
- no aggregate-only benchmark claim.

## State Excerpt

Root `.hermes-loop/state.json` currently has:

- `current_state`: `GOD_DISPATCH`
- `current_phase_idx`: `6`
- `execute_lane`: `phase-6`, state `GOD_DISPATCH`
- `plan_lane`: `phase-7`, state `PLAN_STORM`
- `research_lane`: `phase-8`

Current phase statuses:

- `phase-5` completed with usable ACK at `2026-05-22T14:29:45+08:00`.
- `phase-6` is `in_progress`, but existing phase-6 artifacts are stale from the older "Context Composer + Agentic Kernel" scope and did not use a context bundle.
- `phase-7` and `phase-8` have stale pre-blueprint artifacts and must not be promoted from old evidence.

## Active Blueprint Section

Use `.hermes-loop/blueprint.md` section `## Phase 6 - Answer Projection And Citation Contract`.

Key requirements:

- replace loose answer prompt/context text with structured evidence input;
- require answer projection to cite evidence IDs or mark unsupported;
- preserve deterministic/no-LLM diagnostics;
- add confidence/unsupported handling for missing evidence;
- calibrate judge prompt only after answer evidence contract is clear.

Required failing tests:

- context contains correct evidence but projected answer ignores it;
- answer cites a source not present in selected evidence;
- no-evidence case returns unsupported/refusal instead of hallucinated answer;
- temporal LoCoMo answer preserves date/session grounding.

Mandatory milestone eval:

- LongMemEval 30-50 full-chain LLM judge.
- LoCoMo 30-50 full-chain LLM judge or local cap.

## Required Read-First Files

MemoryOS files:

- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/work/phase-5/result.md`
- `.hermes-loop/work/phase-5/ack.json`
- `.hermes-loop/work/phase-5/reflect_phase-5.md`
- `docs/known-issues.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/agentic-memory-roadmap-zh.md`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/agent_answer_eval.py`
- `src/memoryos_lite/context_composer.py`
- `tests/test_evals.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_answer_eval.py`

Letta reference files, design-only:

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

Borrow semantics only where useful: evidence block identity, rendered memory with metadata, passage/source citation, tool/approval trace durability, and component accounting. Do not port Letta internals or add Letta as a dependency.

## RED Evidence To Start From

Use Phase 5 reports as the baseline comparison:

- `.memoryos/evals/phase5_repeat_20260522_1315_lme_30_longmemeval.json`
- `.memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json`

Known case-level findings from Phase 5:

- LongMemEval unchanged failures: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`, `6ade9755`, `58ef2f1c`, `5d3d2817`, `94f70d80`, `66f24dbb`, `c8c3f81d`, `75499fd8`, `0862e8bf`.
- LongMemEval retrieval misses: `58bf7951`, `6ade9755`, `75499fd8`.
- LongMemEval context-missing-evidence: `e47becba`, `118b2229`, `58ef2f1c`, `5d3d2817`, `7527f7e2`, `94f70d80`, `66f24dbb`, `af8d2e46`, `c8c3f81d`, `8ebdbe50`, `0862e8bf`, `853b0a1d`.
- LoCoMo unchanged failures: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_009`, `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_013`, `conv-26_qa_014`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_026`, `conv-26_qa_027`, `conv-26_qa_029`, `conv-26_qa_030`.
- LoCoMo retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- LoCoMo context-missing-evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.

Start focused tests with public benchmark answer projection/citation behavior before editing production code.

## Expected Commands

Focused RED/GREEN tests:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_projected_answer_cites_selected_evidence -q
uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_flags_projected_unretrieved_citation -q
uv run pytest tests/test_public_benchmarks.py::test_public_answerer_renders_structured_evidence_with_citation_contract -q
uv run pytest tests/test_agent_answer_eval.py -q
```

Regression:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py -q
uv run pytest -q
uv run ruff check .
```

Milestone eval, run LongMemEval and LoCoMo in parallel:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_lme_30_longmemeval.json \
  --run-id phase6_answer_contract_lme_30
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json \
  --run-id phase6_answer_contract_locomo_30
```

If provider access is unavailable, record the blocker, run deterministic no-LLM smoke only as fallback evidence, and do not treat that fallback as satisfying the milestone gate.

## Anti-Demo Usable ACK Criteria

Phase 6 is usable only if:

- the answer citation contract is wired into the real `run_public_benchmark(..., baseline="memoryos_lite")` path;
- focused tests fail before production code changes and pass after;
- deterministic/no-LLM diagnostics still separate retrieval miss, context missing evidence, unsupported answer, and evidence-hit-answer-fail;
- milestone reports list LongMemEval and LoCoMo case movements separately;
- pass-to-fail cases are explicit;
- source grounding does not regress silently;
- `MEMORYOS_MEMORY_ARCH=v1` fallback remains explicit and unbroken;
- v3 remains default;
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.
