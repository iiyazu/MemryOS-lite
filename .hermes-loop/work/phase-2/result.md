# phase: phase-2

# Phase 2 Result - Diagnostic Public Benchmark Evidence Harness

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Changed Real Chain

- Added `src/memoryos_lite/public_case_diagnostics.py` for per-case diagnostic taxonomy:
  - retrieval evidence ids
  - selected context ids
  - rendered answer-context ids
  - cited/unsupported citation ids
  - answer support status
  - judge status
  - failure class
  - movement status
- Added `src/memoryos_lite/public_case_movement.py` for loading prior public JSON reports and computing:
  - `pass_to_fail`
  - `fail_to_pass`
  - `unchanged_pass`
  - `unchanged_fail`
  - `new_case_no_baseline`
- Wired diagnostics into the real `run_public_benchmark()` path in `src/memoryos_lite/public_benchmarks.py`.
- Added append-only report fields:
  - `case_diagnostics`
  - `failure_class`
  - `movement_status`
  - `answer_support_status`
  - `judge_status`
- Added CLI `memoryos eval public --comparison-report PATH`.
- Updated `src/memoryos_lite/diagnostic_report.py` to prefer `case_diagnostics.failure_class` while preserving legacy fallback.
- Fixed `MemoryOSService._should_route_to_v3_context()` so default resolved `v3` routes to v3; explicit `memoryos_memory_arch="v1"` still uses v1.
- Kept v3 kernel opt-in only; default reports keep `kernel_trace_events == []`.

## RED Evidence

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_classifies_unsupported_answer_separately -q
```

Expected failing output observed:

```text
2 failed
KeyError: 'case_diagnostics'
ModuleNotFoundError: No module named 'memoryos_lite.public_case_diagnostics'
```

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs tests/test_public_benchmarks.py::test_public_case_movement_missing_baseline_is_not_anti_demo_evidence tests/test_public_benchmarks.py::test_public_benchmark_movement_status_uses_comparison_report tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_partial_and_final_reports_have_diagnostic_schema_parity tests/test_public_benchmarks.py::test_public_benchmark_source_hit_is_not_retrieval_localization -q
```

Expected failing output observed:

```text
6 failed
ModuleNotFoundError: No module named 'memoryos_lite.public_case_movement'
ModuleNotFoundError: No module named 'memoryos_lite.public_case_diagnostics'
TypeError: run_public_benchmark() got an unexpected keyword argument 'comparison_report_paths'
AssertionError: assert 'case_diagnostics' in report
KeyError: 'case_diagnostics'
```

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics_by_default tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q
```

Expected failing output observed:

```text
3 failed
AssertionError: assert None == 'v3'
KeyError: 'case_diagnostics'
```

## Verification Commands

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py tests/test_llm_judge.py -q
```

Result:

```text
33 passed in 22.39s
```

```bash
uv run pytest -q
```

Result:

```text
366 passed, 1 warning in 567.22s
```

```bash
uv run ruff check .
```

Result:

```text
All checks passed!
```

## Milestone Eval Evidence

Full-chain LLM answer and judge were available through `DEEPSEEK_API_KEY`.

LongMemEval command:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase0_v3_lme_5case_longmemeval.json
```

Result:

```text
exit 0
Report: .memoryos/evals/public_20260521_213550_longmemeval.json
```

LoCoMo command:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase0_v3_locomo_5case_locomo.json
```

Result:

```text
exit 0
Report: .memoryos/evals/public_20260521_214906_locomo.json
```

## LongMemEval Case-Level Evidence

Report: `.memoryos/evals/public_20260521_213550_longmemeval.json`

- pass rate: `18/30`
- retrieval_miss: `58bf7951`, `6ade9755`, `75499fd8`
- context_missing_evidence: `e47becba`, `118b2229`, `58ef2f1c`, `5d3d2817`, `7527f7e2`, `94f70d80`, `66f24dbb`, `af8d2e46`, `c8c3f81d`, `8ebdbe50`, `0862e8bf`, `853b0a1d`
- evidence_hit_answer_fail: none
- unsupported_answer: `51a45a95`, `1e043500`, `c5e8278d`, `6f9b354f`, `f8c5f88b`, `c960da58`, `3b6f954b`, `726462e0`, `ad7109d1`, `dccbc061`, `6b168ec8`, `21436231`, `95bcc1c8`, `a06e4cfe`, `37d43f65`
- supported_cited_answer: none
- judge_questionable: none
- fail_to_pass: none
- pass_to_fail: none
- unchanged_pass: `1e043500`
- unchanged_fail: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`
- new_case_no_baseline: 25 cases; these do not satisfy movement evidence.
- movement baseline source coverage: `5/30`
- answer mode coverage: `llm=30`
- judge status coverage: `judge_pass=18`, `judge_fail=12`, `not_run=0`
- representative ids:
  - `e47becba`: expected `e47becba:answer_280352e9:005`, retrieved includes same, selected includes same, rendered `e47becba:02bd2b90_3:002`, cited none, class `context_missing_evidence`
  - `51a45a95`: expected `51a45a95:answer_d61669c7:005`, retrieved includes same, selected includes same, rendered same, cited none, class `unsupported_answer`

## LoCoMo Case-Level Evidence

Report: `.memoryos/evals/public_20260521_214906_locomo.json`

- pass rate: `7/30`
- retrieval_miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`
- context_missing_evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`
- evidence_hit_answer_fail: none
- unsupported_answer: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`
- supported_cited_answer: none
- judge_questionable: none
- fail_to_pass: `conv-26_qa_001`
- pass_to_fail: none
- unchanged_pass: none
- unchanged_fail: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`
- new_case_no_baseline: 25 cases; these do not satisfy movement evidence.
- movement baseline source coverage: `5/30`
- answer mode coverage: `llm=30`
- judge status coverage: `judge_pass=7`, `judge_fail=23`, `not_run=0`
- representative ids:
  - `conv-26_qa_001`: expected `conv-26_qa_001:conv-26:D1:3`, retrieved includes same, selected includes same, rendered same, cited none, class `unsupported_answer`, movement `fail_to_pass`
  - `conv-26_qa_002`: expected `conv-26_qa_002:conv-26:D1:12`, retrieved did not include expected evidence, selected did not include expected evidence, rendered `conv-26_qa_002:conv-26:D14:6`, cited none, class `retrieval_miss`

## Remaining Gaps

- This phase is diagnostic-only. It does not claim benchmark improvement from diagnostics.
- Full-chain answers currently do not cite sources, so many judge-pass rows are classified as `unsupported_answer` rather than `supported_cited_answer`; no prompt tuning was performed in this phase.
- Movement coverage is limited to the executable Phase 0 five-case comparison reports. The other 25 rows per benchmark are `new_case_no_baseline` and are not counted as anti-demo movement evidence.
- No retrieval ranking, prompt tuning, archive scope, kernel tool expansion, case-id hack, or default kernel enablement was introduced.
