# phase: phase-18

# Phase 18 Governance Spec

## Source And Goal

Context bundle: `.hermes-loop/work/phase-18/context_bundle.md` (`work/phase-18/context_bundle.md` in controller-relative references).

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Phase 18 is a benchmark governance phase. It does not implement product behavior, mutate benchmark evidence, or use demo/smoke output as completion. The resolved execution route for this draft is governance-only `continue_targeted` from current valid evidence.

## Resolved Execute Route

EXECUTE must make a governance-only `continue_targeted` decision from accepted Phase 8 milestone evidence and accepted Phase 17 r3 diagnostic evidence.

No fresh Phase 18 evals, tests, `uv`, `pytest`, `ruff`, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` change, or `blueprint.md` change are planned for EXECUTE.

Fresh LongMemEval 50 and LoCoMo 50 full-chain evals are skipped because Phase 18 EXECUTE is not attempting `expand_eval` or `promote_blueprint`. `review_eval_decision` in `execute_review.md` must justify this skip under Review Eval Autonomy as a control-plane/non-behavioral governance decision that consumes existing valid evidence and does not alter benchmark behavior.

EXECUTE must produce phase-local governance artifacts, not planning prose only:

- `.hermes-loop/work/phase-18/result.md`
- `.hermes-loop/work/phase-18/execute_review.md`

If the controller also requires `review_verdict.json` or `ack.json`, those artifacts must follow this spec, cite the context bundle, and preserve the same governance-only decision basis.

## Chain Component Status

| Component | Phase 18 status | Governance meaning |
|---|---:|---|
| `ingest` | verified | Covered only through already accepted public benchmark evidence. No code change planned. |
| `store` | verified | SQLite remains authoritative; benchmark reports and phase files are evidence artifacts only. |
| `retrieval` | verified | Existing failures must be classified, including `retrieval_miss`; no case-id behavior changes are allowed. |
| `context_composer` | verified | Evidence availability and context inclusion must be separated, including `context_missing_evidence`. |
| `answer_projection` | verified | Evidence-hit answer failures and unsupported answers must remain visible. |
| `public_eval` | changed | Governance artifacts define valid evidence, quarantine rules, decision outputs, and review gates. |
| `source_grounding_diagnostics` | changed | Case-level matrix fields are mandatory for Phase 18 decision evidence. |
| `kernel_loop` | verified | Only the opt-in boundary is verified. `MEMORYOS_AGENT_KERNEL=v1` must not become default or promotion evidence for kernel-off v3. |
| Letta runtime dependency | not_applicable | Phase 18 must not port Letta internals or add Letta as a dependency. |
| product source code | not_applicable | No changes to `src/`, `tests/`, benchmark data, docs, eval reports, `state.json`, or `blueprint.md` are planned. |

## Context Bundle Coverage

`result.md`, `execute_review.md`, and any verdict/ACK artifact must cite `.hermes-loop/work/phase-18/context_bundle.md` / `work/phase-18/context_bundle.md` and the active goal.

EXECUTE and REVIEW must consume the context bundle `read_first` / read-first set or state a narrow, evidence-bound omission for any skipped file. The minimum governance-only evidence set is:

- active goal, `.hermes-loop/state.json`, `.hermes-loop/config.json`, and `.hermes-loop/work/current_goal.md` consistency;
- `.hermes-loop/blueprint.md` Review Eval Autonomy, Phase 18 gates, leakage rules, kernel boundary rules, and anti-demo criteria;
- Phase 17 ACK, result, execute review, review verdict, reflection, and stale index;
- accepted Phase 8 LongMemEval and LoCoMo 50 reports;
- accepted Phase 17 r3 LoCoMo baseline, opt-in kernel repair-smoke report, and repair-smoke summary;
- relevant benchmark diagnostic code/docs only as evidence-bound references, without editing them.

Any omission must explain why the skipped file is not needed for a governance-only `continue_targeted` decision and why the remaining evidence is still valid.

## Governance Decision Outputs

`continue_targeted`: Required EXECUTE decision for this route. It means current valid evidence rejects promotion and points to targeted follow-up work: LoCoMo source localization, retrieval miss handling, and evidence-hit answer failure handling.

`expand_eval`: Future-only route. It requires fresh parallel LongMemEval 50 and LoCoMo 50 full-chain LLM answer/judge evidence, same-case comparison, report-path recording, and review before any promotion claim.

`hold`: Future route if evidence is invalid, incomplete, regressed, leaked, stale, or otherwise not reviewable.

`promote_blueprint`: Future route only when Phase 18 blueprint gates are satisfied by valid full-chain LongMemEval 50 and LoCoMo 50 evidence, with no hidden case-level regressions, no source-grounding regression, invalid artifacts quarantined, kernel default still off, and review ACK accepted.

## Case-Level Evidence Matrix

`result.md` must include or cite a case-level evidence matrix built from accepted Phase 8 and Phase 17 evidence. LongMemEval and LoCoMo must remain separate.

Required fields:

| Field | Required meaning |
|---|---|
| `benchmark` | `longmemeval` or `locomo`; never merge the two into one aggregate. |
| `case_id` | Public benchmark case id used only for reporting and diagnostics. |
| `baseline_report` | Accepted comparison artifact, usually Phase 8 50-case baseline or Phase 17 r3 diagnostic slice. |
| `candidate_report` | `not_run` for this governance-only route; future fresh evidence only for other routes. |
| `artifact_validity` | `valid`, `quarantined`, or `not_used`, with reason. |
| `judge_done` | Whether final LLM judge rows are complete for the accepted evidence. |
| `prior_judged_status` | Prior pass/fail status from accepted valid evidence. |
| `current_judged_status` | `not_run` for this governance-only route. |
| `fail_to_pass` | `false` for this route unless citing accepted prior movement. |
| `pass_to_fail` | `false` for this route unless citing accepted prior movement. |
| `unchanged_fail` | Case failed in accepted diagnostic evidence and still lacks repair evidence. |
| `retrieval_miss` | Required evidence was not retrieved. |
| `evidence_hit_answer_fail` | Evidence was retrieved but answer quality failed. |
| `context_missing_evidence` | Retrieval or storage had evidence, but composed context omitted it. |
| `unsupported_answer` | Answer asserts unsupported content or overconfidently answers without evidence. |
| `judge_questionable` | Judge result appears inconsistent with answer/evidence and needs review treatment. |
| `source_miss_judge_pass` | Judge passed but source localization/source-hit evidence missed. |
| `source_metrics` | Separate source-hit or planned-evidence metrics, not collapsed into judged pass rate. |
| `notes` | Short evidence-bound explanation. |

Known Phase 17 watch cases must remain visible in diagnostics: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005` as `source_miss_judge_pass`; `conv-26_qa_006` as `evidence_hit_answer_fail`; `conv-26_qa_008` as `retrieval_miss`. These ids may be used only in phase-local reports and analysis, never in product behavior.

## Accepted Evidence Basis

Accepted Phase 8 milestone baseline:

- LongMemEval 50 full-chain LLM judge: `47/50`.
- LoCoMo 50 full-chain LLM judge: `30/50`.
- Valid reports:
  - `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
  - `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`

Accepted Phase 17 r3 diagnostic evidence:

- Baseline LoCoMo 10 full-chain: `8 pass / 2 fail`, `judge_done=10/10`.
- Opt-in kernel repair-smoke LoCoMo 10 full-chain: `8 pass / 2 fail`, `judge_done=10/10`.
- `fail_to_pass=[]`
- `pass_to_fail=[]`
- `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`
- `retrieval_miss=["conv-26_qa_008"]`
- `evidence_hit_answer_fail=["conv-26_qa_006"]`
- `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`
- source metric movement: no improvements and no regressions.
- `full_chain_gate_status="not_satisfied"`.

Same-slice repair smoke is diagnostic only and cannot satisfy promotion.

## Invalid Artifact Quarantine

An artifact is invalid for milestone promotion and must be quarantined when any of the following is true:

- heartbeat-only, partial, killed, projected, no-LLM, or no-judge output;
- missing final rows, incomplete `judge_done`, or row count mismatch;
- stale artifact from another phase, timestamp, run id, benchmark, baseline, data path, or limit;
- `MEMORYOS_AGENT_KERNEL=v1` used for default v3 promotion evidence;
- benchmark gold fields, expected answers, expected source ids, judge labels, or case-id rules entered model-visible memory, context inputs, tools, archive artifacts, repair proposals, or scoring candidates;
- LongMemEval and LoCoMo were not reported separately;
- same-slice repair smoke is presented as promotion evidence;
- aggregate pass rate hides `pass_to_fail`, `retrieval_miss`, `source_miss_judge_pass`, or source metric regression.

Quarantine means: keep the artifact if it already exists, label it invalid in phase-local evidence, exclude it from promotion claims, and state the exact reason. Do not delete or mutate original benchmark reports.

## Optional Future Command Templates

These commands are not planned for Phase 18 EXECUTE. They are compliant templates for a future `expand_eval`, `promote_blueprint`, or structural-smoke route only.

Optional structural smokes must isolate `DATA_DIR` per benchmark even when run in parallel:

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

Structural smoke report paths to record:

- `.memoryos/phase18_optional_lme5_<timestamp>/evals/phase18_lme5_structural_<timestamp>_longmemeval.json`
- `.memoryos/phase18_optional_locomo5_<timestamp>/evals/phase18_locomo5_structural_<timestamp>_locomo.json`

Optional full-chain milestone governance evals must run LongMemEval 50 and LoCoMo 50 in parallel, keep the kernel off/default-v3 status explicit, include `--llm-answer` and `--llm-judge`, and compare against accepted Phase 8 reports:

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

Milestone report paths to record:

- `.memoryos/phase18_optional_lme50_<timestamp>/evals/phase18_lme50_<timestamp>_longmemeval.json`
- `.memoryos/phase18_optional_locomo50_<timestamp>/evals/phase18_locomo50_<timestamp>_locomo.json`

Any future milestone route must also write a comparison report under `.hermes-loop/work/phase-18/`, for example `.hermes-loop/work/phase-18/phase18_<timestamp>_comparison.md`, listing run ids, `DATA_DIR` values, report paths, kernel-off/default-v3 status, same-case movement, source metrics, invalid-artifact quarantine, and separate LongMemEval/LoCoMo conclusions.

## Hard Prohibitions

- Do not enable the v3 kernel by default.
- Do not make public benchmark quality depend on `MEMORYOS_AGENT_KERNEL=v1`.
- Do not add case-id hacks or benchmark-specific product behavior.
- Do not leak expected answers, expected source ids, judge labels, benchmark gold fields, or source-target fields into model-visible memory, context composer inputs, archive artifacts, tools, or answer generation.
- Do not promote from same-slice repair smoke.
- Do not promote from LongMemEval alone, LoCoMo alone, kernel trace presence, or aggregate pass rate alone.
- Do not hide `pass_to_fail`, source metric regressions, `source_miss_judge_pass`, `retrieval_miss`, or answer failures behind summary counts.

## ACK And Review Criteria

Phase 18 ACK can be `usable` only when result, review, verdict, and ACK artifacts cite `.hermes-loop/work/phase-18/context_bundle.md` / `work/phase-18/context_bundle.md` and the active goal, and when the decision is one of `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`.

For this route, review must verify:

- EXECUTE produced `result.md` and `execute_review.md`, not planning prose only;
- `decision=continue_targeted`;
- no fresh Phase 18 evals, tests, `uv`, `pytest`, `ruff`, product-code changes, docs changes, benchmark-data changes, eval-report mutation, `state.json` change, or `blueprint.md` change occurred;
- `review_eval_decision` justifies skipping fresh LongMemEval/LoCoMo 50 evals under control-plane/non-behavioral Review Eval Autonomy;
- result/review artifacts cite and consume the context bundle `read_first` / read-first evidence set or state narrow evidence-bound omissions;
- anti-demo gate: no plan-only, demo-only, partial, smoke-only, aggregate-only, or same-slice repair-smoke completion advances the phase as promotion;
- LongMemEval and LoCoMo are separate in all milestone evidence;
- case-level matrix includes `fail_to_pass`, `pass_to_fail`, `retrieval_miss`, `evidence_hit_answer_fail`, `context_missing_evidence`, `unsupported_answer`, `judge_questionable`, and `source_miss_judge_pass`;
- invalid artifacts are quarantined with reasons;
- default v3 behavior remains kernel-off and `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback;
- no promotion claim is made from the governance-only route.
