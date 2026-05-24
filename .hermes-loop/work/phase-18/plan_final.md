# phase: phase-18

# Phase 18 Final Plan

Context bundle: `work/phase-18/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Approved Execution Route

EXECUTE must make a governance-only `continue_targeted` decision from accepted current evidence. This route is resolved and must not be reopened inside EXECUTE.

Accepted evidence basis:

- Phase 8 LongMemEval 50 full-chain LLM judge baseline: `47/50`, report `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`.
- Phase 8 LoCoMo 50 full-chain LLM judge baseline: `30/50`, report `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.
- Phase 17 r3 LoCoMo 10 baseline and opt-in kernel repair smoke: both `8 pass / 2 fail`, `judge_done=10/10`.
- Phase 17 r3 movement: `fail_to_pass=[]`, `pass_to_fail=[]`, `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`.
- Phase 17 r3 classes: `retrieval_miss=["conv-26_qa_008"]`, `evidence_hit_answer_fail=["conv-26_qa_006"]`, `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`.
- Phase 17 r3 source metric movement: no improvements and no regressions.
- Phase 17 r3 `full_chain_gate_status="not_satisfied"`.

Same-slice repair smoke is diagnostic only and must not be used as promotion evidence.

## Execute Constraints

EXECUTE must not run fresh Phase 18 evals, tests, `uv`, `pytest`, `ruff`, public evals, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` mutation, or `blueprint.md` mutation.

Fresh LongMemEval 50 and LoCoMo 50 full-chain evals are intentionally skipped because this route is a control-plane/non-behavioral governance decision from accepted valid evidence. EXECUTE is not attempting `expand_eval` or `promote_blueprint`.

EXECUTE must produce:

- `.hermes-loop/work/phase-18/result.md`
- `.hermes-loop/work/phase-18/execute_review.md`

Both files must cite `work/phase-18/context_bundle.md` and the active goal. `execute_review.md` must include `review_eval_decision` explaining the fresh-eval skip under Review Eval Autonomy and must treat the promotion gate as not applicable or not satisfied.

If later controller steps create `review_verdict.json` or `ack.json`, those artifacts must cite the same context bundle and active goal, preserve `decision=continue_targeted`, and avoid promotion language.

## Required Context Coverage

EXECUTE and REVIEW must consume the context bundle read-first set or record narrow evidence-bound omissions. The minimum governance-only set is:

- active goal plus `.hermes-loop/state.json`, `.hermes-loop/config.json`, and `.hermes-loop/work/current_goal.md` consistency;
- `.hermes-loop/blueprint.md` Review Eval Autonomy, Phase 18 gates, leakage rules, kernel boundary rules, and anti-demo criteria;
- `.hermes-loop/work/phase-17/ack.json`, `result.md`, `execute_review.md`, `review_verdict.json`, `reflect_phase-17.md`, and `stale_index.md`;
- accepted Phase 8 LongMemEval and LoCoMo 50 reports;
- accepted Phase 17 r3 LoCoMo baseline, opt-in kernel repair-smoke report, and repair-smoke summary;
- leakage and kernel-boundary evidence from the files named in `work/phase-18/context_bundle.md` when needed for the review claim.

Any omission must explain why the skipped file is not needed for this governance-only `continue_targeted` decision and why the remaining evidence is still valid.

## Result Requirements

`result.md` must include:

- `decision=continue_targeted`;
- explicit route statement: governance-only, no fresh evals/tests/product changes;
- Review Eval Autonomy rationale for skipping fresh LongMemEval/LoCoMo 50 evals;
- separate LongMemEval and LoCoMo evidence summaries;
- case-level evidence matrix from accepted Phase 8 and Phase 17 evidence;
- invalid artifact quarantine section;
- kernel-off/default-v3 status and `MEMORYOS_AGENT_KERNEL=v1` opt-in boundary;
- statement that same-slice repair smoke is diagnostic-only and not promotion evidence.

The case-level matrix must include these fields: `benchmark`, `case_id`, `baseline_report`, `candidate_report`, `artifact_validity`, `judge_done`, `prior_judged_status`, `current_judged_status`, `fail_to_pass`, `pass_to_fail`, `unchanged_fail`, `retrieval_miss`, `evidence_hit_answer_fail`, `context_missing_evidence`, `unsupported_answer`, `judge_questionable`, `source_miss_judge_pass`, `source_metrics`, and `notes`.

Known LoCoMo watch cases must remain visible in phase-local diagnostics: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_006`, and `conv-26_qa_008`. These ids must not be used in product behavior.

## Review Requirements

`execute_review.md` must verify:

- `result.md` is a result artifact, not plan-shaped prose;
- `review_eval_decision` justifies skipped fresh evals under control-plane/non-behavioral Review Eval Autonomy;
- no fresh evals, tests, `uv`, `pytest`, `ruff`, public evals, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` mutation, or `blueprint.md` mutation occurred;
- context bundle coverage was satisfied or omissions were narrow and evidence-bound;
- LongMemEval and LoCoMo are reported separately;
- case-level matrix fields are present, including pass-to-fail, fail-to-pass, retrieval/source metrics, and source-miss judge-pass;
- invalid artifacts are quarantined with reasons;
- benchmark gold fields, expected answers, expected source ids, judge labels, source-target fields, and case-id rules did not enter model-visible memory, context inputs, tools, archive artifacts, repair proposals, or answer generation;
- v3 remains the default path, `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback, and `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off;
- no promotion claim is made from governance-only evidence.

## Anti-Demo Gate

The phase may not advance from plan-only, demo-only, partial, smoke-only, aggregate-only, or same-slice repair-smoke-only output. Any usable ACK must be evidence-bound to `decision=continue_targeted`, cite the active goal and `work/phase-18/context_bundle.md`, and preserve case-level regression visibility.

## Optional Future Eval Templates

The following templates are not EXECUTE steps for this approved route. They are retained only for a future explicit `expand_eval`, `promote_blueprint`, or structural-smoke route.

Optional structural smokes must isolate `DATA_DIR` per benchmark and may run in parallel:

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

Structural smoke report paths to record if such a future route runs them:

- `.memoryos/phase18_optional_lme5_<timestamp>/evals/phase18_lme5_structural_<timestamp>_longmemeval.json`
- `.memoryos/phase18_optional_locomo5_<timestamp>/evals/phase18_locomo5_structural_<timestamp>_locomo.json`

Optional full-chain milestone evals for a future `expand_eval` or `promote_blueprint` route must run LongMemEval 50 and LoCoMo 50 in parallel, use isolated `DATA_DIR` values, include explicit `--llm-answer` and `--llm-judge`, record run ids and report paths, include Phase 8 comparison reports, and keep kernel-off/default-v3 status explicit:

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

Milestone report paths to record if such a future route runs them:

- `.memoryos/phase18_optional_lme50_<timestamp>/evals/phase18_lme50_<timestamp>_longmemeval.json`
- `.memoryos/phase18_optional_locomo50_<timestamp>/evals/phase18_locomo50_<timestamp>_locomo.json`

Any future milestone route must also write a comparison report under `.hermes-loop/work/phase-18/`, listing run ids, `DATA_DIR` values, report paths, kernel-off/default-v3 status, same-case movement, source metrics, invalid-artifact quarantine, and separate LongMemEval/LoCoMo conclusions.
