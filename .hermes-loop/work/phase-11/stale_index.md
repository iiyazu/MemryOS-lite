# phase: phase-11

# Phase 11 Stale Artifact Quarantine

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

## Quarantined Phase Artifacts

- `stale/review_verdict_20260523T045232Z_fail.json`
  - Reason: FAIL verdict for the superseded `20260523T045232Z` gate. It found the `conv-26_qa_007` shortened-citation source-grounding regression and stale summaries.
- `stale/result_20260523T045232Z.md`
  - Reason: ACK-facing result summary for the superseded `20260523T045232Z` gate. It omits the source-grounding regression later caught by review.
- `stale/execute_review_20260523T045232Z.md`
  - Reason: execute self-review for the superseded `20260523T045232Z` gate. It does not include the follow-up exact-citation and qualifier-repair fixes.
- `stale/case_matrix_20260523T045232Z.md`
  - Reason: case matrix for the superseded `20260523T045232Z` gate. It undercounted the LoCoMo unsupported-citation row.

## Invalid External Eval Evidence

Do not use the killed `20260523T061159Z` partial gate for promotion or ACK:

- `.memoryos/evals/phase11_lme30_handoff_20260523T061159Z_longmemeval.partial.json`
- `.memoryos/evals/phase11_locomo30_handoff_20260523T061159Z_locomo.partial.json`

Reason: the run was stopped after live RED evidence showed LongMemEval `3b6f954b` regressed to `pass_to_fail`; code changed afterward, so the partials are mixed-state stale evidence.

## Current Gate

Current ACK/REVIEW evidence must use only the completed parallel `20260523T064411Z` gate:

- `.memoryos/evals/phase11_lme30_handoff_20260523T064411Z_longmemeval.json`
- `.memoryos/evals/phase11_locomo30_handoff_20260523T064411Z_locomo.json`
- `.hermes-loop/work/phase-11/eval_parallel_30_summary_20260523T064411Z.json`
