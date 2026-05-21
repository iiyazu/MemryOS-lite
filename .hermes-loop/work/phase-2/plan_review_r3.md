# phase: phase-2

# Phase 2 Plan Self-Review R3

Verdict: PASS

Reviewed artifacts:

- `.hermes-loop/work/phase-2/context_bundle.md`
- `.hermes-loop/work/phase-2/god_dispatch.json`
- `.hermes-loop/work/phase-2/plan_review.md`
- `.hermes-loop/work/phase-2/plan_review_r2.md`
- `.hermes-loop/work/phase-2/brainstorm.md`
- `.hermes-loop/work/phase-2/spec.md`
- `.hermes-loop/work/phase-2/plan.md`
- executable path checks in `src/memoryos_lite/cli.py`, `src/memoryos_lite/public_benchmarks.py`, `src/memoryos_lite/engine.py`, `src/memoryos_lite/evals.py`, `src/memoryos_lite/diagnostic_report.py`, `src/memoryos_lite/agent_answer_eval.py`, and current public benchmark tests

## Prior Blocker Recheck

### PASS - Movement status has executable baseline input and real wiring

The plan creates `public_case_movement.py`, loads previous public JSON reports keyed by `(benchmark, baseline, case_id)`, wires `comparison_report_paths` through `run_public_benchmark`, adds a CLI `--comparison-report` option, and requires RED tests for `pass_to_fail`, `fail_to_pass`, `unchanged_pass`, `unchanged_fail`, public-run wiring, and missing-baseline handling.

The milestone commands name real existing comparison report paths:

- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`

Missing comparison rows are explicitly `new_case_no_baseline` and cannot satisfy anti-demo movement evidence.

Relevant lines:

- `spec.md` lines 60-74, 171, 179
- `plan.md` lines 17-20, 163-245, 487-515, 626-652, 695-705, 721-733

### PASS - RED tests force `evidence_hit_answer_fail` vs `retrieval_miss`, with `unsupported_answer` separate

Task 1 now requires a public benchmark fixture whose evidence-hit case retrieves, selects, and renders expected evidence, has a failed projected verdict, and must assert `failure_class == "evidence_hit_answer_fail"`. The paired missing-evidence case must assert `failure_class == "retrieval_miss"`, and the test rejects collapse into generic failure, `supported_cited_answer`, or `unsupported_answer`. A separate builder-level test covers `unsupported_answer`.

Relevant lines:

- `spec.md` lines 75-83, 169-170
- `plan.md` lines 47-157, 422-460, 721-725

### PASS - Partial and final JSON report schema parity is explicitly tested

Task 2 adds a RED test that runs `run_public_benchmark`, reads both the `.partial.json` and final `.json`, and asserts `case_diagnostics` plus mirror fields are present and schema-aligned in both. The existing code writes both partial and final reports through `result.to_report()`, so this is testing the real report path.

Relevant lines:

- `spec.md` lines 136-143, 172-173
- `plan.md` lines 274-291, 519-523
- `public_benchmarks.py` lines 175-179, 269-271

### PASS - Full-chain milestone commands and fallback gates are fixed

R2's blocker is fixed. Task 11 primary LongMemEval and LoCoMo milestone commands now include `--llm-answer --llm-judge`. Fallback commands remain explicitly `--no-llm-answer --no-llm-judge`. The plan requires rejecting primary milestone evidence unless every primary row has `case_diagnostics.answer_mode == "llm"` and `case_diagnostics.judge_status != "not_run"`, unless an exact provider/data blocker is recorded.

This matches the current executable CLI shape: `--llm-answer/--no-llm-answer` and `--llm-judge/--no-llm-judge` both default to `False`, so explicit positive flags are required for full-chain runs.

Relevant lines:

- `spec.md` lines 142-143, 177-179
- `plan.md` lines 626-680, 701-705, 731-733
- `cli.py` lines 355-365
- `public_benchmarks.py` lines 145-146, 194-223, 236-250

## Scope And Constraint Checks

- PASS: All reviewed phase-local markdown starts with `# phase: phase-2`.
- PASS: The brainstorm, spec, and plan cite and consume `context_bundle.md`.
- PASS: The plan remains diagnostic-only: no retrieval optimization, answer prompt tuning, archive/scope work, kernel tool expansion, Letta runtime dependency, or benchmark case-id hacks.
- PASS: It preserves v3 default, explicit v1 fallback, v2 recall opt-in compatibility, and kernel opt-in. The plan includes a targeted engine fix because current `_should_route_to_v3_context()` still requires `memoryos_memory_arch` in `model_fields_set` even though settings default to v3.
- PASS: It preserves `source_hit` as final projection/source overlap and adds separate retrieved, selected, rendered, and cited evidence IDs.
- PASS: LongMemEval and LoCoMo milestone runs and case-level analyses remain separate.
- PASS: TDD sequencing is explicit: RED tests first, GREEN implementation, REFACTOR, focused regression, full smoke, milestone eval, and review gates.
- PASS: Diagnostics are wired to the real `memoryos eval public -> run_public_benchmark -> _to_public_result -> to_report()` path, not a markdown-only artifact.

## Execute Lane Readiness

Executable by execute_lane: YES.

The R1 and R2 blockers are addressed. No GOD_ADJUST is required from this review.
