# god_context - phase-8

## Current State

`phase-8` is still recorded in `.hermes-loop/state.json` as `current_state=EXECUTE`, but the current phase gate artifacts now satisfy ACK consistency. Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## What's Done

- Confirmed `.hermes-loop/work/current_goal.md`.
- Refreshed `work/phase-8/context_bundle.md` and `god_dispatch.json` checksum for the current EXECUTE state and fresh phase-8 evidence.
- Fixed `.hermes-loop/hermes_hardening.py` movement counting for real eval reports that use `movement_status`.
- Added RED test `tests/test_hermes_hardening.py::test_summarize_eval_report_counts_real_movement_status_field`.
- Wrote `promotion_decision.md`, `result.md`, `execute_review.md`, `review_verdict.json`, `ack.json`, `blueprint_amendment.md`, `reviews/codex-review-current.md`, and `reflect_phase-8.md`.
- Ran `python .hermes-loop/hermes_hardening.py --write`; `ack_gate` is now `ok`.

## What's Next

Next action: run GOD_ADJUST or a careful GOD_ADVANCE equivalent from the current artifacts, but do not blindly commit the whole dirty tree. The phase decision is `continue_targeted`, represented in `ack.json` as `"decision": "adjust_blueprint"`.

## Key Evidence

- Focused guard: `3 passed`.
- Full pytest after hardening fix: `410 passed, 1 warning`.
- Ruff: `All checks passed!`.
- LongMemEval final evidence: `phase8_lme50_20260522T151605Z`, `47 pass / 3 fail`, no pass-to-fail.
- LoCoMo final evidence: `phase8_locomo50_20260522T151605Z`, `30 pass / 20 fail`, no pass-to-fail.
- ACK consistency: `.hermes-loop/work/phase-8/phase-8_status.md` shows `ack_gate: ok`.

## Disabled Artifacts

- `work/phase-8/reviews/codex-review.md` is stale legacy review evidence for the old defer/default-deprecation task.
- `phase8_lme50_hb_20260522T160637Z` and `phase8_locomo50_hb_20260522T160637Z` ended with status `143` and partial projected/no-judge artifacts. Do not use them as promotion evidence.
- Shard retry artifacts are diagnostic/resume evidence only; the complete 15:16 final reports are the promotion-gate evidence.

## Blueprint Sections Active

- `.hermes-loop/blueprint.md`: "Phase 8 - Promotion Gate And Next Blueprint Decision".
- `.hermes-loop/blueprint.md`: "Dynamic Blueprint Amendment Protocol".
- `.hermes-loop/work/phase-8/blueprint_amendment.md`: targeted LoCoMo reliability loop recommendation.
