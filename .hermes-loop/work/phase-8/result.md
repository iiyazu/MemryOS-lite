# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context: `work/phase-8/context_bundle.md`.

## Result

Phase 8 reached a usable promotion-gate result, but not a promotion result.

Decision: `continue_targeted`.

The real MemoryOS v3 public benchmark path was exercised with full-chain LLM answer and judge on 50 LongMemEval cases and 50 LoCoMo cases. The eval commands used `MEMORYOS_MEMORY_ARCH=v3`; they did not set `MEMORYOS_AGENT_KERNEL=v1`, so kernel default stayed off.

No production memory behavior was changed in this completion step. A small reliability diagnostic fix was made in `.hermes-loop/hermes_hardening.py` so the phase status helper counts real report `movement_status` fields instead of only the legacy `movement` key.

## Verification Commands

- `uv run pytest tests/test_hermes_hardening.py::test_summarize_eval_report_counts_real_movement_status_field -q` -> RED: failed because `movement_counts` was `{}` for real `movement_status`.
- `uv run pytest tests/test_hermes_hardening.py -q` -> GREEN: `10 passed`.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q` -> `3 passed`.
- `uv run pytest -q` -> `410 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.
- `python .hermes-loop/hermes_hardening.py --write` -> LongMemEval and LoCoMo final reports classified as `completed`; ACK gate initially blocked only by missing `ack.json`, `review_verdict.json`, and `result.md`.

## Eval Evidence

LongMemEval command:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 50 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase6_god_adjust_prompt2_lme_30_longmemeval.json --run-id phase8_lme50_20260522T151605Z
```

LoCoMo command:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 50 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase6_god_adjust_prompt2_locomo_30_locomo.json --run-id phase8_locomo50_20260522T151605Z
```

Reports:

- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`

The later `phase8_lme50_hb_20260522T160637Z` and `phase8_locomo50_hb_20260522T160637Z` retries ended with status `143` and partial projected/no-judge reports. They are recorded as reliability evidence only, not promotion evidence.

## Case-Level Analysis

LongMemEval:

- Pass/fail: `47 pass / 3 fail`.
- Fail-to-pass: none.
- Pass-to-fail: none.
- Unchanged fail: `51a45a95`.
- New failures without same-subset baseline: `b86304ba`, `ccb36322`.
- Retrieval miss: `b86304ba`, `ccb36322`.
- Evidence hit but answer fail: `51a45a95`.
- Context missing evidence: `b86304ba`, `ccb36322`.
- Unsupported answer or judge questionable: none.

LoCoMo:

- Pass/fail: `30 pass / 20 fail`.
- Fail-to-pass: none.
- Pass-to-fail: none.
- Unchanged fail: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_027`.
- New failures without same-subset baseline: `conv-26_qa_033`, `conv-26_qa_035`, `conv-26_qa_036`, `conv-26_qa_039`, `conv-26_qa_041`, `conv-26_qa_044`, `conv-26_qa_048`, `conv-26_qa_050`.
- Retrieval miss: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_035`, `conv-26_qa_036`, `conv-26_qa_039`, `conv-26_qa_044`, `conv-26_qa_050`.
- Evidence hit but answer fail: `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`, `conv-26_qa_033`, `conv-26_qa_041`, `conv-26_qa_048`.
- Context missing evidence: same as retrieval miss list.
- Source not indexed: `conv-26_qa_038`.
- Judge questionable/source-support mismatch: `conv-26_qa_015`.

## Active Goal Alignment

This result supports the active goal only as a diagnostic gate: the system is now better measured on both benchmarks, but LoCoMo is not benchmark-usable yet. Advancing to broader eval or production-style claims would hide case-level failures, so the correct controller action is targeted continuation rather than promotion.
