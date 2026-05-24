# phase: phase-17

# Phase Status

Context bundle: `work/phase-17/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Status: phase-17 entered `GOD_DISPATCH` after phase-16 usable ACK and commit
`f96c611`.

## Bootstrap Decision

At startup, `work/phase-17/` was missing required phase-local artifacts, so the
Phase Bootstrap Safety rule allows only context, dispatch, and planning
artifacts in this controller pass.

Generated or confirmed:

- `work/phase-17/context_bundle.md`
- `work/phase-17/god_dispatch.json`
- `work/phase-17/stale_index.md`

Implementation, tests, evals, product-code edits, benchmark report edits, and
state transitions are not allowed until planning artifacts exist and a later
bootstrap promotes the phase to `EXECUTE`.

## Next Allowed Controller Action

Run `PLAN_STORM`, `PLAN_DRAFT`, and `PLAN_SELF_REVIEW` for phase-17. If
planning passes, write `work/phase-17/plan_final.md` and leave the controller
in `GOD_DISPATCH` for a future bootstrap promotion to `EXECUTE`.

## PLAN_STORM Complete

Artifact: `work/phase-17/brainstorm.md`.

Decision: recommended Approach 1, an explicit opt-in repair-smoke harness around
the real public v3 path. Rejected direct fixture writes, preseed-only reruns as
the primary path, broad retrieval/composer repair, Level 2/3 tool opening, and
any gold-field executable input.

## PLAN_DRAFT And PLAN_SELF_REVIEW Complete

Artifacts:

- `work/phase-17/spec.md`
- `work/phase-17/plan.md`
- `work/phase-17/plan_review.md`
- `work/phase-17/plan_final.md`

PLAN_SELF_REVIEW iteration 1 failed on invalid full-chain command semantics and
a gold-leakage conflict in the positive repair-smoke test. The plan was revised
to require explicit `--llm-answer` and `--llm-judge` for all full-chain public
eval gates and to require sanitized/aliased executable repair inputs.

PLAN_SELF_REVIEW iteration 2 passed and promoted `plan_final.md`.

## Bootstrap Promotion To EXECUTE

The required execute bootstrap artifacts now exist:

- `work/phase-17/context_bundle.md`
- `work/phase-17/god_dispatch.json`
- `work/phase-17/plan_final.md`

Per Phase Bootstrap Safety, the controller promoted `.hermes-loop/state.json`
from `GOD_DISPATCH` to `EXECUTE` for `execute_lane.phase = phase-17` and is
continuing into the phase-17 `EXECUTE` section in the same run.

## Review Repair Complete

The review FAIL in `work/phase-17/review_verdict.json` was classified as
`repair`, not `repeat_phase`, `god_adjust`, or `hold`.

Blocking items fixed:

- `source_miss_judge_pass` is now reported for judge-pass/source-localization
  misses.
- Missing, extra, or duplicate same-slice baseline rows now block the
  repair-smoke gate through `baseline_coverage`.
- Context-selection/rendering diagnostic classes now map into
  `context_missing_evidence`.

Fresh artifacts:

- `work/phase-17/result.md`
- `work/phase-17/execute_review.md`
- `work/phase-17/eval_heartbeat_phase17_locomo10_baseline_r3.json`
- `work/phase-17/eval_heartbeat_phase17_locomo10_kernel_repair_smoke_r3.json`

Controller state was promoted from `EXECUTE` to `REVIEW` for a read-only review
lane. No ACK may be written unless the new review passes and aligns with the
active goal.
