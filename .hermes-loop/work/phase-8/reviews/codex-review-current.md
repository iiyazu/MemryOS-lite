# phase: phase-8

Verdict: PASS

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context cited: `work/phase-8/context_bundle.md` (`.hermes-loop/work/phase-8/context_bundle.md` in this checkout). The bundle requires a promotion-gate decision from fresh LongMemEval and LoCoMo evidence, with explicit pass-to-fail handling, source-grounding separation, no LoCoMo hiding, no benchmark hacks, v1 fallback preserved, v3 default preserved, and kernel default unchanged.

## Review

- Active goal alignment: PASS. `promotion_decision.md` selects `continue_targeted`, not `expand_eval` or `promote_blueprint`, because LongMemEval is strong but LoCoMo remains weak. This matches the active goal's "benchmark-usable" and "do not hide regressions" constraints.
- Stale artifacts: PASS with caution. `work/phase-8/reviews/codex-review.md` is still stale and says the old `defer` decision was acceptable, but current plan/result/decision artifacts cite `work/phase-8/context_bundle.md`, and this file supersedes the stale review.
- Source grounding: PASS. The decision separates answer pass rate from `source_hit`, retrieval miss, `evidence_hit_answer_fail`, `source_not_indexed`, unsupported/source-support mismatch, and new-case/no-baseline groups.
- LoCoMo failure visibility: PASS. LoCoMo is not hidden behind LongMemEval: artifacts report `30/50` pass, `20/50` fail, `12` retrieval-miss failures, `8` evidence-hit-answer-fail cases, and `conv-26_qa_038` source-not-indexed.
- Benchmark overfitting: PASS. I found no case-id hacks or expected-answer leak in the reviewed diff; milestone eval logs use normal public eval commands with comparison reports only for movement accounting.
- v1 fallback preservation: PASS. No tracked `src` diff changes the fallback path; `src/memoryos_lite/config.py` still allows `MEMORYOS_MEMORY_ARCH=v1`.
- v3 default preservation: PASS. `src/memoryos_lite/config.py` still defaults `memoryos_memory_arch` to `v3`.
- Kernel default unchanged: PASS. Final eval logs set `MEMORYOS_MEMORY_ARCH=v3` and do not set `MEMORYOS_AGENT_KERNEL=v1`; both final reports have `kernel_trace_events=[]` across all 50 rows.

## Evidence Checked

- `work/phase-8/context_bundle.md`: active goal, Phase 8 gate, fresh evidence requirements, stale artifact warning, and default/fallback constraints.
- `work/phase-8/god_dispatch.json`: cites the context bundle and carries the active goal.
- `work/phase-8/plan_final.md`: requires unique 50-case eval run ids, no kernel opt-in for promotion evals, separate LongMemEval/LoCoMo analysis, and explicit pass-to-fail/source-grounding checks.
- `work/phase-8/promotion_decision.md`: decision is `continue_targeted`; LongMemEval `47/50`, LoCoMo `30/50`; pass-to-fail is explicit as `0`.
- `work/phase-8/result.md` and `work/phase-8/execute_review.md`: record verification, final run ids, no promotion claim, and LoCoMo as the controlling bottleneck.
- `.hermes-loop/state.json`: phase 8 remains `in_progress`; no new state ACK is recorded.
- Git diff/status: no tracked `src` diff; active control/docs are dirty; stale `ack.json` and `reflect_phase-8.md` are deleted; `review_verdict.json`, `ack.json`, and `adjustment.md` are currently absent.

## Caution

This PASS is for the current promotion-gate decision (`continue_targeted`), not for closing Phase 8 as an ACK. If the controller expects a complete ACK package, the missing `work/phase-8/review_verdict.json` plus absent `ack.json`/`adjustment.md` must be resolved before any phase-advance claim.
