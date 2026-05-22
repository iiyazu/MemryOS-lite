# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context: `work/phase-8/context_bundle.md`.

Decision: `continue_targeted`.

## Evidence

Verification:

- Focused guard: `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q` -> `3 passed`.
- Full tests: `uv run pytest -q` -> `410 passed, 1 warning`.
- Lint: `uv run ruff check .` -> `All checks passed!`.
- Hardening focused test after diagnostic fix: `uv run pytest tests/test_hermes_hardening.py -q` -> `10 passed`.

Milestone evals:

- LongMemEval: `phase8_lme50_20260522T151605Z`, report `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`, command used `MEMORYOS_MEMORY_ARCH=v3`, `--llm-answer`, `--llm-judge`, and no `MEMORYOS_AGENT_KERNEL=v1`.
- LoCoMo: `phase8_locomo50_20260522T151605Z`, report `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`, command used `MEMORYOS_MEMORY_ARCH=v3`, `--llm-answer`, `--llm-judge`, and no `MEMORYOS_AGENT_KERNEL=v1`.

The later heartbeat retry run ids `phase8_lme50_hb_20260522T160637Z` and `phase8_locomo50_hb_20260522T160637Z` ended with status `143` and only partial projected/no-judge artifacts. They are excluded from promotion evidence.

## LongMemEval

- Result: `47/50` pass, `3/50` fail.
- Movement against the 30-case comparison report: `29` unchanged pass, `1` unchanged fail, `0` pass-to-fail, `0` fail-to-pass, `20` new cases with no baseline.
- Unchanged fail: `51a45a95`.
- New-case failures: `b86304ba`, `ccb36322`.
- Retrieval-miss failures: `b86304ba`, `ccb36322`.
- Evidence-hit-answer-fail: `51a45a95`.
- Unsupported answer / judge questionable: none.
- Source-grounding risk: expected source hit is false for `b86304ba`, `ccb36322`; planned evidence misses also appear on some passing cases, so source metrics remain separate from judged answer pass rate.

LongMemEval is strong enough to support more diagnostics, but it is not enough to promote the whole chain while LoCoMo remains much weaker.

## LoCoMo

- Result: `30/50` pass, `20/50` fail.
- Movement against the 30-case comparison report: `18` unchanged pass, `12` unchanged fail, `0` pass-to-fail, `0` fail-to-pass, `20` new cases with no baseline.
- Unchanged fail: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_027`.
- New-case failures: `conv-26_qa_033`, `conv-26_qa_035`, `conv-26_qa_036`, `conv-26_qa_039`, `conv-26_qa_041`, `conv-26_qa_044`, `conv-26_qa_048`, `conv-26_qa_050`.
- Retrieval-miss failures: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_035`, `conv-26_qa_036`, `conv-26_qa_039`, `conv-26_qa_044`, `conv-26_qa_050`.
- Evidence-hit-answer-fail: `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`, `conv-26_qa_033`, `conv-26_qa_041`, `conv-26_qa_048`.
- Source not indexed: `conv-26_qa_038`.
- Judge/source-support questionable: `conv-26_qa_015` was judge-pass but classified as unsupported answer by diagnostics.

LoCoMo remains the controlling bottleneck. The failures are not random aggregate noise: they split between source retrieval/session localization failures and cases where evidence is present but the answer still fails.

## Decision Rationale

Do not choose `expand_eval`: the 50-case evidence is stable enough to diagnose, but LoCoMo `30/50` with `20` failures is not benchmark-usable.

Do not choose `hold`: no pass-to-fail cases were observed on the same 30-case comparison subset, and kernel default stayed off.

Do not choose `promote_blueprint`: the active blueprint should not be silently overwritten from this evidence alone.

Choose `continue_targeted`: next work should target LoCoMo retrieval/session-temporal localization and answer use of already-selected evidence, with case-level gates from the failures listed above.
