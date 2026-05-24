# phase: phase-18

# Phase 18 Plan Review

Verdict: PASS.

Active goal reviewed: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle reviewed: `work/phase-18/context_bundle.md`.

## PASS Rationale

The repaired `spec.md` and `plan.md` fix the prior blockers and now satisfy the phase-18 planning contract.

1. The execution route is explicitly resolved.

   EXECUTE is governance-only `continue_targeted` from accepted current evidence: Phase 8 LongMemEval/LoCoMo 50 full-chain baselines plus Phase 17 r3 LoCoMo diagnostic evidence. The plan no longer leaves route selection to EXECUTE, and it explicitly states that fresh Phase 18 evals, tests, `uv`, `pytest`, `ruff`, code changes, docs changes, benchmark data changes, eval-report mutation, `state.json` changes, and `blueprint.md` changes are not planned.

2. Review Eval Autonomy is satisfied for this route.

   Fresh LongMemEval 50 and LoCoMo 50 full-chain evals are skipped only because this is a control-plane/non-behavioral governance decision and is not attempting `expand_eval` or `promote_blueprint`. The plan requires `review_eval_decision` in `execute_review.md` to record that skip rationale, with `promotion_gate` not applicable or not satisfied rather than promoted.

3. Anti-demo and usable ACK standards are preserved.

   The plan requires real phase-local governance outputs, specifically `result.md` and `execute_review.md`, and forbids plan-only, demo-only, partial, smoke-only, aggregate-only, or same-slice repair-smoke-only advancement. It requires any verdict/ACK to cite the active goal and context bundle, keep the decision evidence-bound, and avoid promotion language.

4. v1 fallback, v3 default, and kernel opt-in/default-off boundaries are preserved.

   The repaired plan preserves `MEMORYOS_MEMORY_ARCH=v3` as the default public benchmark path, keeps `MEMORYOS_MEMORY_ARCH=v1` as an explicit fallback, and keeps `MEMORYOS_AGENT_KERNEL=v1` opt-in only. It also rejects kernel trace presence and same-slice repair smoke as promotion evidence.

5. Benchmark leakage and case-id overfitting rules are covered.

   The plan keeps benchmark gold fields, expected answers, expected source ids, judge labels, source-target fields, and case-id rules out of model-visible memory, context composer inputs, archive artifacts, tools, repair proposals, and answer generation. Watch case ids are allowed only in phase-local diagnostics and reports.

6. Case-level regression visibility is required.

   The case-level matrix must expose LongMemEval and LoCoMo separately and include fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence-hit-answer-fail, context-missing-evidence, unsupported answer, judge-questionable, source-miss judge-pass, and source metrics. The Phase 17 watch cases remain visible instead of being hidden behind aggregate pass counts.

7. Optional future eval templates are compliant.

   The optional structural and milestone templates are clearly marked as future-only, not EXECUTE steps. They use isolated per-benchmark `DATA_DIR` values, parallel execution, explicit `--llm-answer` and `--llm-judge` for full-chain gates, comparison reports, report paths, run ids, and explicit kernel-off/default-v3 status. This resolves the earlier command-shape blocker.

8. Context bundle coverage is operationalized.

   EXECUTE and REVIEW must cite `work/phase-18/context_bundle.md` and either consume the context bundle `read_first` set or record narrow evidence-bound omissions. The minimum governance-only evidence set covers active goal/state/config/current goal consistency, blueprint Review Eval Autonomy and Phase 18 gates, Phase 17 ACK/result/review/verdict/reflection/stale index, accepted Phase 8 reports, Phase 17 r3 reports, and leakage/kernel-boundary rules.

## Approved Route

Proceed with governance-only `continue_targeted`.

EXECUTE must not run fresh evals, tests, `uv`, `pytest`, `ruff`, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` mutation, or `blueprint.md` mutation. EXECUTE must produce `.hermes-loop/work/phase-18/result.md` and `.hermes-loop/work/phase-18/execute_review.md` from the accepted current evidence and must not claim promotion.

No `plan_review` blockers remain.
