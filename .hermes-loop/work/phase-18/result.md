# phase: phase-18

# Phase 18 Result

Context bundle cited: `work/phase-18/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

`decision=continue_targeted`

## Route

Governance-only route. No fresh Phase 18 evals, tests, product changes, docs changes, benchmark-data changes, eval-report mutation, or `blueprint.md` mutation were performed. The only `state.json` change in this controller pass was the bootstrap transition from `GOD_DISPATCH` to `EXECUTE`, recorded in `work/phase-18/phase_status.md` because `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` already existed.

This result aligns with `work/phase-18/execute_goal.md`: Phase 18 made a control-plane promotion decision from accepted evidence only. It is not an `expand_eval` attempt and not a `promote_blueprint` attempt.

## Review Eval Autonomy

Fresh LongMemEval and LoCoMo evals were skipped under Review Eval Autonomy because this EXECUTE route is control-plane/non-behavioral governance. It changed no retrieval, context composition, answer projection, storage, benchmark runner behavior, kernel behavior, or eval data. The accepted Phase 8 and Phase 17 reports are sufficient for the required governance decision, but insufficient for promotion.

Promotion gate: `not_applicable` for this governance-only route, and not satisfied for any promotion claim.

## LongMemEval Evidence

Accepted Phase 8 milestone report: `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`.

- Valid full-chain LLM answer/judge report.
- `memory_arch=v3`.
- Kernel trace events were absent in the report rows, consistent with default kernel-off behavior.
- Judged result: `47 pass / 3 fail`, `judge_done=50/50`.
- Failing cases: `51a45a95`, `b86304ba`, `ccb36322`.
- Source metrics in the accepted report: `source_hit=48/50`, `planned_evidence_source_hit_at_5=43/50`, `episode_source_hit_at_10=44/50`.

No Phase 18 LongMemEval candidate was run because this route did not change behavior and did not seek promotion or evaluation expansion.

## LoCoMo Evidence

Accepted Phase 8 milestone report: `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

- Valid full-chain LLM answer/judge report.
- `memory_arch=v3`.
- Kernel trace events were absent in the report rows, consistent with default kernel-off behavior.
- Judged result: `30 pass / 20 fail`, `judge_done=50/50`.
- Source metrics in the accepted report: `source_hit=31 true / 17 false / 2 none`, `planned_evidence_source_hit_at_5=26 true / 22 false / 2 none`, `episode_source_hit_at_10=29 true / 19 false / 2 none`.

Accepted Phase 17 r3 repair-smoke evidence:

- Baseline report: `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json`.
- Opt-in repair-smoke report: `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json`.
- Repair-smoke summary: `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo_repair_smoke_summary.json`.
- Baseline and repair smoke both: `8 pass / 2 fail`, `judge_done=10/10`.
- `fail_to_pass=[]`, `pass_to_fail=[]`.
- `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`.
- `retrieval_miss=["conv-26_qa_008"]`.
- `evidence_hit_answer_fail=["conv-26_qa_006"]`.
- `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`.
- Source metric movement: no improvements and no regressions for `source_hit`, `planned_evidence_source_hit_at_5`, or `episode_source_hit_at_10`.
- `full_chain_gate_status="not_satisfied"`.

Same-slice repair smoke is diagnostic-only and not promotion evidence.

## Case-Level Evidence Matrix

Fields required by `work/phase-18/plan_final.md` are present in each row: `benchmark`, `case_id`, `baseline_report`, `candidate_report`, `artifact_validity`, `judge_done`, `prior_judged_status`, `current_judged_status`, `fail_to_pass`, `pass_to_fail`, `unchanged_fail`, `retrieval_miss`, `evidence_hit_answer_fail`, `context_missing_evidence`, `unsupported_answer`, `judge_questionable`, `source_miss_judge_pass`, `source_metrics`, and `notes`.

| benchmark | case_id | baseline_report | candidate_report | artifact_validity | judge_done | prior_judged_status | current_judged_status | fail_to_pass | pass_to_fail | unchanged_fail | retrieval_miss | evidence_hit_answer_fail | context_missing_evidence | unsupported_answer | judge_questionable | source_miss_judge_pass | source_metrics | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LongMemEval | 51a45a95 | `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json` | none | valid accepted Phase 8; no Phase 18 candidate | yes, Phase 8 | fail | unchanged evidence basis | false | false | not evaluated in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | false | Phase 8 aggregate: source_hit 48/50; planned 43/50; episode 44/50 | One of three accepted Phase 8 LME failures; no new movement claim. |
| LongMemEval | b86304ba | `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json` | none | valid accepted Phase 8; no Phase 18 candidate | yes, Phase 8 | fail | unchanged evidence basis | false | false | not evaluated in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | false | Phase 8 aggregate: source_hit 48/50; planned 43/50; episode 44/50 | One of three accepted Phase 8 LME failures; no new movement claim. |
| LongMemEval | ccb36322 | `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json` | none | valid accepted Phase 8; no Phase 18 candidate | yes, Phase 8 | fail | unchanged evidence basis | false | false | not evaluated in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | not classified in Phase 18 | false | Phase 8 aggregate: source_hit 48/50; planned 43/50; episode 44/50 | One of three accepted Phase 8 LME failures; no new movement claim. |
| LoCoMo | conv-26_qa_003 | `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`; `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json` | `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json` | valid accepted Phase 8 and Phase 17; Phase 17 is diagnostic-only | yes, Phase 8 and Phase 17 | Phase 8 fail; Phase 17 r3 baseline pass | Phase 17 repair pass | false | false | false | false in summary class | false | false | false | false | true | Phase 17 source movement none; row source/planned/episode miss | Watch row: judged pass with source localization miss in Phase 17 summary. |
| LoCoMo | conv-26_qa_004 | `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`; `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json` | `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json` | valid accepted Phase 8 and Phase 17; Phase 17 is diagnostic-only | yes, Phase 8 and Phase 17 | Phase 8 fail; Phase 17 r3 baseline pass | Phase 17 repair pass | false | false | false | false in summary class | false | false | false | false | true | Phase 17 source movement none; row source/planned/episode miss | Watch row: judged pass with source localization miss in Phase 17 summary. |
| LoCoMo | conv-26_qa_005 | `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`; `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json` | `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json` | valid accepted Phase 8 and Phase 17; Phase 17 is diagnostic-only | yes, Phase 17 | Phase 17 r3 baseline pass | Phase 17 repair pass | false | false | false | false in summary class | false | false | false | false | true | Phase 17 source movement none; row source/planned/episode miss | Watch row: judged pass with source localization miss in Phase 17 summary. |
| LoCoMo | conv-26_qa_002 | `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json` | `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json` | valid accepted Phase 17; diagnostic-only | yes, Phase 17 | Phase 17 r3 baseline pass | Phase 17 repair pass | false | false | false | false | false | false | false | false | true | Phase 17 source movement none; planned/episode miss | Watch row: judged pass with source localization miss in Phase 17 summary. |
| LoCoMo | conv-26_qa_006 | `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`; `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json` | `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json` | valid accepted Phase 8 and Phase 17; Phase 17 is diagnostic-only | yes, Phase 8 and Phase 17 | fail | fail | false | false | true | false | true | false | false | false | false | Phase 17 source movement none; source/planned/episode hit true | Unchanged failure; answer/evidence projection remains targeted bottleneck. |
| LoCoMo | conv-26_qa_008 | `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`; `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json` | `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json` | valid accepted Phase 8 and Phase 17; Phase 17 is diagnostic-only | yes, Phase 8 and Phase 17 | fail | fail | false | false | true | true | false | false | true in row support status; summary unsupported_answer empty | false | false | Phase 17 source movement none; source/planned/episode miss | Unchanged failure; retrieval/query/source ranking remains targeted bottleneck. |
| LoCoMo | Phase 8 remaining failures | `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json` | none | valid accepted Phase 8; no Phase 18 candidate | yes, Phase 8 | fail | unchanged evidence basis | false | false | not evaluated in Phase 18 | not reclassified in Phase 18 | not reclassified in Phase 18 | not reclassified in Phase 18 | not reclassified in Phase 18 | not reclassified in Phase 18 | not evaluated in Phase 18 | Phase 8 aggregate: source_hit 31 true / 17 false / 2 none; planned 26 true / 22 false / 2 none; episode 29 true / 19 false / 2 none | Cases: `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_027`, `conv-26_qa_033`, `conv-26_qa_035`, `conv-26_qa_036`, `conv-26_qa_039`, `conv-26_qa_041`, `conv-26_qa_044`, `conv-26_qa_048`, `conv-26_qa_050`. |

## Invalid Artifact Quarantine

Quarantined artifacts and run ids are not promotion evidence:

- `phase8_lme50_hb_20260522T160637Z`: invalid heartbeat retry; killed/partial/projected/no-judge per `work/phase-18/context_bundle.md`.
- `phase8_locomo50_hb_20260522T160637Z`: invalid heartbeat retry; killed/partial/projected/no-judge per `work/phase-18/context_bundle.md`.
- Phase 17 same-slice repair smoke reports are valid diagnostic evidence, but quarantined from promotion evidence because `same_slice_repair_smoke_only=true` and `full_chain_gate_status="not_satisfied"`.
- Untracked runtime logs or orchestration state named by the context bundle are not used as promotion evidence.

## Kernel And Default Boundary

- Default memory architecture remains v3: `memoryos_memory_arch="v3"`.
- Explicit v1 fallback remains available through `MEMORYOS_MEMORY_ARCH=v1`.
- Agent kernel remains default-off: `memoryos_agent_kernel="off"`.
- `MEMORYOS_AGENT_KERNEL=v1` remains an opt-in boundary. Phase 17 repair smoke required that opt-in and did not become default benchmark behavior.
- Default Phase 8 public benchmark reports had no kernel trace events; Phase 17 repair-smoke candidate had kernel traces only in the explicit opt-in repair-smoke run.

## Governance Conclusion

MemoryOS Lite v3 remains benchmark-usable as a diagnosed prototype, not promotion-ready. LongMemEval is comparatively strong, but LoCoMo still exposes source-grounding and failure-class bottlenecks. The next route should continue targeted work on:

- source-miss judged-pass visibility and repair;
- `conv-26_qa_006` answer/evidence projection failure;
- `conv-26_qa_008` retrieval/query/source-ranking failure;
- clean-store or held-out validation before any improvement or promotion claim.
