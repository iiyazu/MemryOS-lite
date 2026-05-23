# phase: phase-11

# Codex Review: Phase 11

Verdict: FAIL.

Phase 11 is not ACK-eligible. The implementation adds real-path diagnostics, but the milestone eval and case matrix do not satisfy the usable anti-demo gate: LongMemEval has a pass-to-error regression, LoCoMo has no aggregate gain, and LoCoMo introduces a pass-to-fail case.

## Review Inputs

- Read first: `.hermes-loop/work/phase-11/context_bundle.md`.
- Then read: `god_dispatch.json`, `plan_final.md`, `red_result.md`, `result.md`, `execute_review.md`, `case_matrix.md`, active blueprint excerpts, Phase 9/10 comparison artifacts, and current `git diff`.
- Spot-checked current report JSON with a read-only Python probe because `jq` is unavailable in this environment.

## Findings

1. Blocker: milestone eval fails the ACK gate.
   - `.hermes-loop/work/phase-11/result.md:74` records LongMemEval 30 as `29 pass / 0 fail / 1 error`, with `ad7109d1` as a pass-to-error regression.
   - `.hermes-loop/work/phase-11/result.md:75` records LoCoMo 30 as `20 pass / 10 fail`, with `conv-26_qa_028` as pass-to-fail.
   - `.hermes-loop/work/phase-11/case_matrix.md:58-61` explicitly says LongMemEval is not clean promotion evidence, LoCoMo is not ACK-usable, and the next decision should be repeat/adjust.
   - This violates the phase gate requiring no material LongMemEval collapse and no unexplained LoCoMo pass-to-fail.

2. Blocker: Phase 11 did not prove same-case handoff improvement.
   - `.hermes-loop/work/phase-11/case_matrix.md:44-53` shows no selected-drop, render-drop, or answer-evidence-drop rows in the 30-case gate.
   - The only LoCoMo fail-to-pass is `conv-26_qa_003`, but it remains classified as `retrieval_miss`, not as a handoff improvement.
   - The targeted evidence-hit-answer-fail cases `conv-26_qa_006`, `conv-26_qa_016`, `conv-26_qa_024`, and `conv-26_qa_027` remain failed in `.hermes-loop/work/phase-11/result.md:75`.

3. Blocker: milestone report artifact is stale relative to the movement-status fix.
   - `src/memoryos_lite/public_case_movement.py:46-58` now correctly maps baseline `pass` plus current non-pass to `pass_to_fail`.
   - But `.memoryos/evals/phase11_lme30_handoff_20260522T234828Z_longmemeval.json:407295-407301` records `ad7109d1` as `error`, while `.memoryos/evals/phase11_lme30_handoff_20260522T234828Z_longmemeval.json:430247` and `:433225` still record `movement_status: unchanged_fail`.
   - `.hermes-loop/work/phase-11/case_matrix.md:18` calls this out, but ACK cannot rely on a report whose persisted movement fields still hide the pass-to-error regression.

4. Regression: LoCoMo pass-to-fail is real in the current report.
   - `.memoryos/evals/phase11_locomo30_handoff_20260522T234828Z_locomo.json:909302` identifies `conv-26_qa_028`.
   - `.memoryos/evals/phase11_locomo30_handoff_20260522T234828Z_locomo.json:939872-939873` records `failure_class: evidence_hit_answer_fail` and `movement_status: pass_to_fail`.
   - `.memoryos/evals/phase11_locomo30_handoff_20260522T234828Z_locomo.json:942373` records `failure_boundary: citation_drop`.

## Non-Blocker Review Notes

- Real-path wiring exists: `run_public_benchmark()` now computes answer evidence once and passes it into `PublicAnswerer` and `_to_public_result()` in `src/memoryos_lite/public_benchmarks.py:220-228` and `:270-291`.
- Diagnostic fields are append-only: `PublicBenchmarkResult.answer_evidence` is added at `src/memoryos_lite/public_benchmarks.py:128-131`, and the report still uses `asdict()` in `:137-140`.
- The handoff ledger is present in `src/memoryos_lite/public_case_diagnostics.py:141-208` and splits retrieval, selected, rendered, answer-evidence, and citation boundaries.
- RED coverage was present for selected/render split, answer-evidence metadata, and pass-to-error movement classification in `.hermes-loop/work/phase-11/red_result.md`.
- I did not see a case-id branch, expected-answer leak, scoring change, broad retrieval retune, Letta runtime dependency, or prompt-only claim masquerading as architecture.
- v1 fallback/v3 default/kernel default-off appear preserved: defaults remain `memoryos_memory_arch = "v3"` and `memoryos_agent_kernel = "off"` in `src/memoryos_lite/config.py:29-30`, and kernel construction remains gated by `resolved_agent_kernel == "v1"` in `src/memoryos_lite/engine.py:1490-1506`.

## Required Gate Checks

- Behavioral regression: FAIL due LongMemEval pass-to-error and LoCoMo pass-to-fail.
- Source grounding: PARTIAL. New diagnostics expose handoff stages, but LoCoMo `conv-26_qa_028` regressed at citation/support level.
- LoCoMo failure modes: FAIL. Remaining retrieval misses and evidence-hit-answer-fail cases are visible, but no ACK-grade improvement occurred.
- Prompt-hack risk: PASS. No obvious case-id or expected-answer branch in the diff.
- Benchmark overfitting: PASS on code shape, FAIL on evidence because the phase did not generalize to the gate cases.
- Missing RED tests: PASS for implemented diagnostic changes; no additional projection RED was required by the observed diff.
- Stale phase artifacts: FAIL due stale LongMemEval report movement fields after the movement-status fix.
- Context bundle coverage: PASS. Plan/result/review artifacts cite the Phase 11 context bundle.
- v1 fallback: PASS by diff review and existing tests.
- v3 default: PASS by diff review and existing tests.
- Kernel default-off: PASS by diff review and existing tests.

## Recommended Next Action

Do not write `ack.json` and do not advance the phase.

Return to `GOD_ADJUST` or repeat a narrow Phase 11 pass. First regenerate the milestone reports after the movement-status fix so persisted movement fields match current code, then investigate the two regressions: LongMemEval `ad7109d1` judge-parse error and LoCoMo `conv-26_qa_028` citation-drop/pass-to-fail. Only reconsider ACK after the refreshed 30-case gate has no pass-to-fail/pass-to-error and shows same-case explainable LoCoMo handoff or answer-evidence improvement.
