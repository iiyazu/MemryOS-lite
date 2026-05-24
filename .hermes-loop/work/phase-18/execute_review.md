# phase: phase-18

# Execute Review

Context bundle cited: `work/phase-18/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## What Real Chain Changed Or Was Verified?

No product chain changed in Phase 18. This EXECUTE route verified governance over the real v3 public benchmark evidence already accepted by prior phases:

- accepted Phase 8 LongMemEval 50 and LoCoMo 50 full-chain LLM judge reports;
- accepted Phase 17 LoCoMo 10 baseline and opt-in kernel repair-smoke reports;
- case-level movement, source-metric movement, and invalid-artifact quarantine;
- v3 default, explicit v1 fallback, and `MEMORYOS_AGENT_KERNEL=v1` opt-in boundary.

The real chain component affected by this phase is `public_eval` governance, not runtime behavior.

## What Is Still Demo-Only Or Partial?

No new demo-only implementation was added. Remaining partial limitations are evidence limitations:

- Phase 17 repair smoke is measurable and safe, but not effective on the fixed LoCoMo 10 r3 slice.
- Same-slice repair smoke is diagnostic-only and cannot promote the blueprint.
- LoCoMo source-miss judged-pass rows remain unresolved.
- `conv-26_qa_006` remains an evidence-hit-answer-fail case.
- `conv-26_qa_008` remains a retrieval-miss case.
- No Phase 18 clean-store, held-out, or full 50-case candidate run exists.

## What Tests Or Evidence Proved Behavior?

No fresh Phase 18 tests, evals, `uv`, `pytest`, `ruff`, public evals, or network commands were run. Evidence came from read-only inspection of accepted artifacts named by `work/phase-18/context_bundle.md`.

The only `state.json` mutation in this controller pass was the required bootstrap transition from `GOD_DISPATCH` to `EXECUTE`, recorded in `work/phase-18/phase_status.md` before EXECUTE artifacts were produced. EXECUTE itself did not mutate state, source, tests, docs, benchmark data, eval reports, or `blueprint.md`.

Accepted evidence:

- Phase 8 LongMemEval 50: `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`, `47 pass / 3 fail`, `judge_done=50/50`.
- Phase 8 LoCoMo 50: `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`, `30 pass / 20 fail`, `judge_done=50/50`.
- Phase 17 LoCoMo r3 baseline: `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json`, `8 pass / 2 fail`, `judge_done=10/10`.
- Phase 17 LoCoMo r3 opt-in repair smoke: `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json`, `8 pass / 2 fail`, `judge_done=10/10`.
- Phase 17 repair-smoke summary: `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo_repair_smoke_summary.json`, `fail_to_pass=[]`, `pass_to_fail=[]`, `full_chain_gate_status="not_satisfied"`.

The result artifact is a result, not plan-shaped prose: it records `decision=continue_targeted`, route, eval-skip rationale, separate benchmark summaries, a case matrix, invalid artifact quarantine, and kernel/default boundary.

## Which Benchmark Cases Moved Or Regressed?

Phase 18 ran no candidate, so it records accepted movement only.

LongMemEval:

- Accepted Phase 8 failures: `51a45a95`, `b86304ba`, `ccb36322`.
- No Phase 18 movement or regression was measured.

LoCoMo:

- Phase 17 r3 `fail_to_pass=[]`.
- Phase 17 r3 `pass_to_fail=[]`.
- Phase 17 r3 `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`.
- Phase 17 r3 `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`.
- Phase 17 source metric regressions: none.
- Phase 17 source metric improvements: none.

Phase 8 LoCoMo remaining failures stayed visible in the result matrix rather than being hidden by aggregate pass rate.

## Did v1 Fallback, v3 Default, And Kernel Opt-In Remain Intact?

Yes, based on accepted artifact evidence and read-only code/test inspection:

- `Settings` defaults `memoryos_memory_arch` to `v3`.
- `Settings` permits `MEMORYOS_MEMORY_ARCH=v1` as explicit fallback.
- `Settings` defaults `memoryos_agent_kernel` to `off`.
- Repair smoke validation requires explicit `MEMORYOS_AGENT_KERNEL=v1` and `MEMORYOS_MEMORY_ARCH=v3`.
- Phase 8 reports show default kernel-off behavior with no kernel trace events.
- Phase 17 repair-smoke traces occur only in the explicit opt-in kernel run.

No Phase 18 write touched those files or settings.

## Leakage And Quarantine Check

The Phase 18 artifacts do not use benchmark gold fields, expected answers, expected source ids, judge labels, or case-id rules as product behavior. Case ids appear only in phase-local diagnostic reporting.

Invalid or non-promotion artifacts are quarantined:

- `phase8_lme50_hb_20260522T160637Z` is invalid heartbeat retry evidence.
- `phase8_locomo50_hb_20260522T160637Z` is invalid heartbeat retry evidence.
- Phase 17 same-slice repair smoke is valid diagnostic evidence but not promotion evidence.

## review_eval_decision

```yaml
review_eval_decision:
  scope: not_applicable
  reason: >
    Phase 18 EXECUTE is governance-only and non-behavioral. It changed no source,
    tests, docs, benchmark data, eval reports, runtime flags, retrieval, context
    composition, answer projection, or kernel behavior. Accepted Phase 8 and
    Phase 17 evidence is sufficient for a continue_targeted governance decision,
    but not for expand_eval or promote_blueprint.
  longmemeval:
    run: false
    limit: 0
    reason: "No product behavior changed and this route is not a promotion or eval-expansion attempt."
  locomo:
    run: false
    limit: 0
    reason: "No product behavior changed and this route is not a promotion or eval-expansion attempt."
  llm_answer: false
  llm_judge: false
  promotion_gate: not_applicable
```

Promotion gate is also explicitly not satisfied for promotion language: no fresh clean-store or held-out validation was produced, and same-slice repair smoke remains diagnostic-only.

## Review Outcome

The execution satisfies `work/phase-18/execute_goal.md` for the approved governance-only route. The correct decision is `continue_targeted`, with no promotion claim and no hidden case-level regressions.
