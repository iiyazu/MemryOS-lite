# phase: phase-5

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context source: `.hermes-loop/work/phase-5/context_bundle.md`.

# Result: Context Composer And Accounting Repeat

## Controller Decision

Phase 5 was repeated because the live Phase 5 review failure blocked a usable ACK:

- dropped v3 diagnostics had to be excluded from selected-context evidence;
- previous milestone evidence used `judge_status=not_run`;
- previous movement was all `new_case_no_baseline`;
- the root `state.json` had drifted to Phase 8 despite Phase 5 not having usable evidence.

The current result is usable for Phase 5 as context-accounting and diagnostic plumbing only. It does not claim benchmark-quality answer improvement. The next phase must prioritize Phase 6 answer projection/citation because both full-chain reports still show unsupported answer grounding.

## Files Changed

- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`
- `tests/test_public_benchmarks.py`
- `.hermes-loop/work/phase-5/context_bundle.md`
- `.hermes-loop/work/phase-5/god_dispatch.json`
- `.hermes-loop/work/phase-5/result.md`
- `.hermes-loop/work/phase-5/execute_review.md`

## Real Chain Changed

- `V3ContextComposer` emits append-only component accounting, final-context trace metadata, component token/drop counts, and LoCoMo neighbor diagnostics.
- `MemoryOSService.build_context()` propagates v3 accounting and final-context trace into `ContextPackage.metadata` and `context_built` traces.
- Recall budget-drop and neighbor diagnostics preserve source refs and benchmark-session metadata.
- Public benchmark reports expose v3 accounting fields append-only.
- Public case diagnostics consume final-context trace source refs and no longer count dropped v3 diagnostics as selected evidence.

## RED And Review-Fix Evidence

The original RED commands failed before implementation with missing `component_accounting`, `final_context_trace`, public report fields, and `locomo_neighbor_diagnostics`.

Post-review regression proof:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_does_not_select_dropped_v3_diagnostics -q
```

Result:

```text
1 passed in 0.05s
```

Focused Phase 5 proof:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_records_component_accounting_for_included_and_budget_dropped_items tests/test_context_composer.py::test_v3_composer_final_context_trace_flattens_selected_source_refs tests/test_context_composer.py::test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session tests/test_context_composer.py::test_v3_composer_records_locomo_neighbor_budget_drop tests/test_engine.py::test_v3_build_context_trace_includes_component_accounting_and_final_context_trace tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_component_accounting tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_component_accounting_append_only tests/test_public_benchmarks.py::test_public_case_diagnostics_uses_v3_final_context_trace_source_refs tests/test_public_benchmarks.py::test_public_benchmark_reports_locomo_neighbor_diagnostics -q
```

Result:

```text
9 passed in 10.24s
```

Phase 4 guard:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Result:

```text
4 passed in 3.95s
```

Full verification:

```bash
uv run pytest -q
```

Result:

```text
388 passed, 1 warning in 549.00s (0:09:09)
```

```bash
uv run ruff check .
```

Result:

```text
All checks passed!
```

## Milestone Eval

LongMemEval and LoCoMo were run in parallel with explicit run ids, full LLM answer/judge, and Phase 2 full-chain comparison reports:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/public_20260521_213550_longmemeval.json --run-id phase5_repeat_20260522_1315_lme_30
```

Report: `.memoryos/evals/phase5_repeat_20260522_1315_lme_30_longmemeval.json`.

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/public_20260521_214906_locomo.json --run-id phase5_repeat_20260522_1315_locomo_30
```

Report: `.memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json`.

### LongMemEval

- Rows: 30.
- Pass/fail: 18 pass / 12 fail.
- Judge: 18 `judge_pass`, 12 `judge_fail`.
- Movement: 18 `unchanged_pass`, 12 `unchanged_fail`, 0 `fail_to_pass`, 0 `pass_to_fail`, 0 `new_case_no_baseline`.
- Failure classes: `retrieval_miss=3`, `context_missing_evidence=12`, `unsupported_answer=15`, `evidence_hit_answer_fail=0`, `supported_cited_answer=0`, `judge_questionable=0`.
- Answer support: `unsupported_answer=30`.
- v3 accounting fields present on all 30 rows: `v3_component_accounting`, `v3_final_context_trace`, `v3_component_token_totals`, `v3_component_drop_counts`, `locomo_neighbor_diagnostics`.

Case lists:

- `pass_to_fail`: none.
- `fail_to_pass`: none.
- `unchanged_fail`: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`, `6ade9755`, `58ef2f1c`, `5d3d2817`, `94f70d80`, `66f24dbb`, `c8c3f81d`, `75499fd8`, `0862e8bf`.
- `retrieval_miss`: `58bf7951`, `6ade9755`, `75499fd8`.
- `context_missing_evidence`: `e47becba`, `118b2229`, `58ef2f1c`, `5d3d2817`, `7527f7e2`, `94f70d80`, `66f24dbb`, `af8d2e46`, `c8c3f81d`, `8ebdbe50`, `0862e8bf`, `853b0a1d`.
- `unsupported_answer`: `51a45a95`, `1e043500`, `c5e8278d`, `6f9b354f`, `f8c5f88b`, `c960da58`, `3b6f954b`, `726462e0`, `ad7109d1`, `dccbc061`, `6b168ec8`, `21436231`, `95bcc1c8`, `a06e4cfe`, `37d43f65`.

### LoCoMo

- Rows: 30.
- Pass/fail: 7 pass / 23 fail.
- Judge: 7 `judge_pass`, 23 `judge_fail`.
- Movement: 7 `unchanged_pass`, 23 `unchanged_fail`, 0 `fail_to_pass`, 0 `pass_to_fail`, 0 `new_case_no_baseline`.
- Failure classes: `retrieval_miss=11`, `context_missing_evidence=10`, `unsupported_answer=9`, `evidence_hit_answer_fail=0`, `supported_cited_answer=0`, `judge_questionable=0`.
- Answer support: `unsupported_answer=30`.
- v3 accounting fields present on all 30 rows: `v3_component_accounting`, `v3_final_context_trace`, `v3_component_token_totals`, `v3_component_drop_counts`, `locomo_neighbor_diagnostics`.

Case lists:

- `pass_to_fail`: none.
- `fail_to_pass`: none.
- `unchanged_fail`: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_009`, `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_013`, `conv-26_qa_014`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_026`, `conv-26_qa_027`, `conv-26_qa_029`, `conv-26_qa_030`.
- `retrieval_miss`: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- `context_missing_evidence`: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- `unsupported_answer`: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`.

## Constraints Checked

- No benchmark case-id rules or expected-answer leaks were added.
- Public benchmark fields were extended append-only.
- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback and excludes v3 component accounting in focused tests.
- `MEMORYOS_AGENT_KERNEL` remains opt-in/default-off and kernel trace stays default-off in focused tests.
- LongMemEval and LoCoMo are reported separately.

## Carry Forward

- Phase 5 should ACK only as a usable diagnostic/context-accounting phase, not as a benchmark improvement.
- Phase 6 should be the next execute lane because both full-chain reports still have `answer_support_status=unsupported_answer` for every row.
- The Phase 8 promotion gate is stale until Phase 6 and later gates are rerun from current evidence.
