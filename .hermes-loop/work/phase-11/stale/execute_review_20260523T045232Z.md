# phase: phase-11

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Real Chain Changed

Yes. The real public benchmark path computes structured answer evidence from `BaselineOutput`, passes compact answer evidence into `PublicAnswerer`, serializes full answer-evidence diagnostics on `PublicBenchmarkResult`, and feeds answer-evidence ids/details into `build_case_diagnostics()`.

`public_case_diagnostics` exposes an append-only handoff ledger across retrieved, selected, rendered, answer-evidence, and cited stages. `public_failure_replay` carries the handoff fields into replay rows. `public_case_movement.movement_status()` treats baseline `pass` plus current `error` as `pass_to_fail`.

The repeat fix keeps internal report metadata out of the answerer prompt while preserving it in public report rows.

## Demo-Only Or Partial Remaining

The code is not demo-only: it is exercised by `run_public_benchmark()` and by the current 30-case public eval reports.

Remaining partial work is diagnostic, not hidden:

- LoCoMo still has retrieval misses: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`.
- LoCoMo still has evidence-hit-answer-fail rows: `conv-26_qa_006`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`.
- LongMemEval still has unchanged fail `51a45a95`.

Those rows are visible in report diagnostics and are not counted as phase-completion proof.

## Tests Proving Behavior

RED tests failed before the original diagnostic implementation:

- selected/render handoff diagnostics failed with missing `evidence_handoff`;
- answer-evidence report plumbing failed because `_to_public_result()` had no `answer_evidence` parameter;
- movement reporting failed because baseline `pass` plus current `error` returned `unchanged_fail`.

Repeat-fix regression tests cover the review blockers:

- noisy internal answer-evidence metadata must not enter the LLM prompt;
- explicit location qualifiers must still be preserved when answer evidence has metadata.

Current verification:

- focused answerer tests: `5 passed`.
- focused diagnostics/movement tests: `3 passed`.
- `uv run pytest tests/test_public_benchmarks.py tests/test_public_failure_replay.py tests/test_agent_answer_eval.py -q` -> `58 passed`.
- `uv run ruff check .` -> `All checks passed!`.
- `uv run pytest -q` -> `430 passed, 1 warning`.

## Benchmark Cases Moved Or Regressed

Current reports:

- LongMemEval: `.memoryos/evals/phase11_lme30_handoff_20260523T045232Z_longmemeval.json`
- LoCoMo: `.memoryos/evals/phase11_locomo30_handoff_20260523T045232Z_locomo.json`

LongMemEval 30:

- `29 pass / 1 fail / 0 error`
- fail-to-pass: none
- pass-to-fail: none
- prior blockers cleared: `3b6f954b=pass`, `ad7109d1=pass`
- unchanged fail: `51a45a95`

LoCoMo 30:

- `21 pass / 9 fail / 0 error`
- fail-to-pass: `conv-26_qa_003`
- pass-to-fail: none
- prior blocker cleared: `conv-26_qa_028=pass`
- remaining retrieval-miss rows: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`
- remaining evidence-hit-answer-fail rows: `conv-26_qa_006`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`

## Preservation Review

- v1 fallback was not modified.
- v3 remains the default architecture.
- The v3 kernel remains opt-in through `MEMORYOS_AGENT_KERNEL=v1`; no kernel default change was made.
- Existing dirty controller files were preserved.

## Overfitting And Scoring Review

- No case-id branches, expected-answer leaks, benchmark scoring changes, broad retrieval retuning, or kernel-default changes were added.
- The fix is general: answer prompts use compact evidence fields, while full diagnostic metadata remains report-only.
- Remaining retrieval misses are still visible and were not relabeled as answer failures.

## Execute-Lane Recommendation

Move to REVIEW for the current Phase 11 result. The old `review_verdict.json` should be treated as superseded by the `20260523T045232Z` repeat evidence.
