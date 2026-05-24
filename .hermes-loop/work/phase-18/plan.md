# phase: phase-18

# Phase 18 TDD-Oriented Plan

## Source And Goal

Context bundle: `.hermes-loop/work/phase-18/context_bundle.md` (`work/phase-18/context_bundle.md` in controller-relative references).

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Resolved route: EXECUTE will make a governance-only `continue_targeted` decision from current valid evidence. This plan does not leave route selection to the execute lane.

No fresh Phase 18 evals, tests, `uv`, `pytest`, `ruff`, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` change, or `blueprint.md` change are planned for EXECUTE. Fresh LongMemEval 50 and LoCoMo 50 evals are not run because no `expand_eval` or `promote_blueprint` decision is being attempted.

## RED: Current Valid Evidence

Treat accepted case-level public benchmark evidence as RED evidence because this is a governance-only phase.

EXECUTE must start by citing `.hermes-loop/work/phase-18/context_bundle.md` / `work/phase-18/context_bundle.md` and consuming the context bundle `read_first` / read-first set, or state narrow evidence-bound omissions. The minimum set is:

- active goal plus `.hermes-loop/state.json`, `.hermes-loop/config.json`, and `.hermes-loop/work/current_goal.md` consistency;
- `.hermes-loop/blueprint.md` Review Eval Autonomy, Phase 18 gates, leakage rules, kernel boundary rules, and anti-demo criteria;
- `.hermes-loop/work/phase-17/ack.json`, `result.md`, `execute_review.md`, `review_verdict.json`, `reflect_phase-17.md`, and `stale_index.md`;
- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`;
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`;
- `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json`;
- `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json`;
- `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo_repair_smoke_summary.json`;
- leakage and kernel-boundary evidence from the files named in the context bundle when needed for the review claim.

Capture these RED facts without rerunning anything:

- Phase 8 LongMemEval 50 full-chain LLM judge: `47/50`.
- Phase 8 LoCoMo 50 full-chain LLM judge: `30/50`.
- Phase 17 r3 LoCoMo 10 baseline and opt-in kernel repair smoke: both `8 pass / 2 fail`, `judge_done=10/10`.
- Phase 17 r3 movement: `fail_to_pass=[]`, `pass_to_fail=[]`.
- Phase 17 r3 classes: `retrieval_miss=["conv-26_qa_008"]`, `evidence_hit_answer_fail=["conv-26_qa_006"]`, `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`.
- Phase 17 r3 source metric movement: no improvements and no regressions.
- Phase 17 r3 `full_chain_gate_status="not_satisfied"`.

Do not invent unit tests for this governance gap. If a later phase proposes code changes, it must first add RED coverage for the exact behavior being changed.

## GREEN: Execute Governance Decision

Produce `.hermes-loop/work/phase-18/result.md` with:

- citation to `.hermes-loop/work/phase-18/context_bundle.md` / `work/phase-18/context_bundle.md` and the active goal;
- `decision=continue_targeted`;
- explicit route statement: governance-only, no fresh Phase 18 evals/tests/product changes;
- Review Eval Autonomy rationale for skipping fresh LongMemEval/LoCoMo 50 evals: the phase is making a control-plane/non-behavioral decision from accepted valid evidence and is not attempting `expand_eval` or `promote_blueprint`;
- separate LongMemEval and LoCoMo evidence summaries;
- case-level evidence matrix from accepted Phase 8 and Phase 17 evidence;
- invalid artifact quarantine section;
- kernel-off/default-v3 status and `MEMORYOS_AGENT_KERNEL=v1` opt-in boundary;
- statement that same-slice repair smoke is diagnostic-only and not promotion evidence.

The case-level matrix must include these fields or columns:

- `benchmark`
- `case_id`
- `baseline_report`
- `candidate_report` (`not_run` for this route)
- `artifact_validity`
- `judge_done`
- `prior_judged_status`
- `current_judged_status` (`not_run` for this route)
- `fail_to_pass`
- `pass_to_fail`
- `unchanged_fail`
- `retrieval_miss`
- `evidence_hit_answer_fail`
- `context_missing_evidence`
- `unsupported_answer`
- `judge_questionable`
- `source_miss_judge_pass`
- `source_metrics`
- `notes`

Known LoCoMo watch cases must remain visible in phase-local diagnostics: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_006`, and `conv-26_qa_008`. These ids must not be used in product behavior.

## REFACTOR: Review Artifact

Produce `.hermes-loop/work/phase-18/execute_review.md` with:

- citation to `.hermes-loop/work/phase-18/context_bundle.md` / `work/phase-18/context_bundle.md` and the active goal;
- confirmation that `result.md` is a result artifact, not plan-shaped prose;
- `review_eval_decision` explaining why fresh evals were skipped under control-plane/non-behavioral Review Eval Autonomy;
- verification that no fresh Phase 18 evals, tests, `uv`, `pytest`, `ruff`, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` change, or `blueprint.md` change occurred;
- verification that the context bundle `read_first` / read-first set was consumed or that any omission is narrow and evidence-bound;
- anti-demo verification: no plan-only, smoke-only, aggregate-only, same-slice repair-smoke-only, partial, or demo-only completion advances the phase as promotion;
- validation of separate LongMemEval/LoCoMo evidence, case-level matrix fields, invalid artifact quarantine, leakage boundary, and kernel-off/default-v3 status;
- conclusion that the only supported decision for this route is `continue_targeted`.

If the controller creates `review_verdict.json` or `ack.json`, those artifacts must preserve the same decision, cite the context bundle, and avoid promotion language.

## Optional Future Eval Templates

The commands below are not EXECUTE steps for this route. They are templates only for a future route that explicitly attempts `expand_eval`, `promote_blueprint`, or structural smoke.

Optional structural smokes must isolate `DATA_DIR` per benchmark:

```bash
TS=<timestamp>
(
  DATA_DIR=".memoryos/phase18_optional_lme5_${TS}" \
  MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=off \
  uv run memoryos eval public \
    --benchmark longmemeval \
    --data-path benchmarks/longmemeval/longmemeval.json \
    --baseline memoryos_lite \
    --limit 5 \
    --run-id "phase18_lme5_structural_${TS}" \
    --no-llm-answer \
    --no-llm-judge
) &
(
  DATA_DIR=".memoryos/phase18_optional_locomo5_${TS}" \
  MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=off \
  uv run memoryos eval public \
    --benchmark locomo \
    --data-path benchmarks/locomo/locomo10.json \
    --baseline memoryos_lite \
    --limit 5 \
    --run-id "phase18_locomo5_structural_${TS}" \
    --no-llm-answer \
    --no-llm-judge
) &
wait
```

Record these structural smoke report paths if the future route runs them:

- `.memoryos/phase18_optional_lme5_<timestamp>/evals/phase18_lme5_structural_<timestamp>_longmemeval.json`
- `.memoryos/phase18_optional_locomo5_<timestamp>/evals/phase18_locomo5_structural_<timestamp>_locomo.json`

Optional full-chain milestone governance evals are required for a future `expand_eval` or any `promote_blueprint` attempt. They must run in parallel, use isolated `DATA_DIR` values, include explicit `--llm-answer` and `--llm-judge`, record run ids and report paths, include Phase 8 comparison reports, and keep kernel-off/default-v3 status explicit:

```bash
TS=<timestamp>
(
  DATA_DIR=".memoryos/phase18_optional_lme50_${TS}" \
  MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=off \
  uv run memoryos eval public \
    --benchmark longmemeval \
    --data-path benchmarks/longmemeval/longmemeval.json \
    --baseline memoryos_lite \
    --limit 50 \
    --run-id "phase18_lme50_${TS}" \
    --llm-answer \
    --llm-judge \
    --comparison-report .memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json
) &
(
  DATA_DIR=".memoryos/phase18_optional_locomo50_${TS}" \
  MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=off \
  uv run memoryos eval public \
    --benchmark locomo \
    --data-path benchmarks/locomo/locomo10.json \
    --baseline memoryos_lite \
    --limit 50 \
    --run-id "phase18_locomo50_${TS}" \
    --llm-answer \
    --llm-judge \
    --comparison-report .memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json
) &
wait
```

Record these milestone report paths if the future route runs them:

- `.memoryos/phase18_optional_lme50_<timestamp>/evals/phase18_lme50_<timestamp>_longmemeval.json`
- `.memoryos/phase18_optional_locomo50_<timestamp>/evals/phase18_locomo50_<timestamp>_locomo.json`

Any future milestone route must also write a comparison report such as `.hermes-loop/work/phase-18/phase18_<timestamp>_comparison.md` with run ids, `DATA_DIR` values, report paths, kernel-off/default-v3 status, same-case movement, pass-to-fail and fail-to-pass lists, source metrics, invalid-artifact quarantine, and separate LongMemEval/LoCoMo conclusions.

For every future long eval, write and refresh `work/phase-18/eval_heartbeat*.json` at least every two minutes. Heartbeats and partial monitor files are not milestone evidence. Final judge completion must be verified from report rows before any result is considered valid.

## Invalid Artifact Quarantine

Quarantine and exclude from promotion evidence any artifact that is heartbeat-only, partial, killed, projected, no-LLM, no-judge, stale, mismatched by run id/data path/limit/baseline/benchmark, missing final rows, missing complete `judge_done`, or produced with `MEMORYOS_AGENT_KERNEL=v1` as if it were default v3 evidence.

Also quarantine any artifact or run if expected answers, expected source ids, benchmark gold fields, judge labels, case-id rules, or source-target fields become model-visible or influence memory, retrieval, context composition, archive writes, repair proposals, or answer generation.

Do not delete or mutate original benchmark reports.

## Hard Stops

Stop with `hold` if any of these occur during artifact production or review:

- evidence needed for the governance-only decision cannot be read or is invalid;
- unexplained same-case `pass_to_fail` is discovered in accepted evidence;
- aggregate judged pass improves while source metrics or `source_miss_judge_pass` regress;
- LongMemEval 50 materially regresses from Phase 8 without explanation;
- LoCoMo is missing from milestone evidence;
- same-slice repair smoke is used as promotion evidence;
- kernel default enablement is proposed or required;
- expected-answer/source leakage or case-id product hacks are found.

## Review And ACK

Review must align to the active goal and anti-demo gate. It must confirm:

- `result.md`, `execute_review.md`, and any verdict/ACK cite `.hermes-loop/work/phase-18/context_bundle.md` / `work/phase-18/context_bundle.md` and the active goal;
- decision is `continue_targeted`;
- fresh evals were skipped for the required control-plane/non-behavioral reason and this is captured in `review_eval_decision`;
- no product code, docs, tests, benchmark data, eval reports, `state.json`, or `blueprint.md` were modified;
- no tests, `uv`, `pytest`, `ruff`, or public evals were run;
- case-level evidence matrix exposes `fail_to_pass`, `pass_to_fail`, `retrieval_miss`, `evidence_hit_answer_fail`, `context_missing_evidence`, `unsupported_answer`, `judge_questionable`, and `source_miss_judge_pass`;
- invalid artifacts are quarantined with reasons;
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and is not used as default promotion evidence;
- ACK level is `usable` only for governance completion; plan-only, demo-only, partial, smoke-only, aggregate-only, and same-slice repair-smoke outcomes cannot advance the phase as promotion.
