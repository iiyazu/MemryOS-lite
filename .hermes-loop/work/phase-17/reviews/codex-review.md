# phase: phase-17

Verdict: FAIL

Blocking findings:

1. LoCoMo judge-pass/source-miss cases are not reported in the required `source_miss_judge_pass` bucket. In the generated repair smoke eval, `conv-26_qa_005` is `verdict=pass` while `source_hit=False`, `planned_evidence_source_hit_at_5=False`, and `episode_source_hit_at_10=False`; however the summary reports `source_miss_judge_pass=[]` and puts that case under `retrieval_miss`. The root cause is that `src/memoryos_lite/public_case_diagnostics.py:257-260` returns `retrieval_miss` before considering `verdict == "pass"`, and `src/memoryos_lite/public_repair_smoke.py:323-325` blindly buckets that report-level class. Exact repair: add a failing LoCoMo repair-summary test for a judge-pass/source-miss row, classify it as `source_miss_judge_pass` before generic retrieval miss, and keep source metric movement separate from judged answer pass/fail.

2. Same-slice comparison can hide current-run cases when the baseline report is incomplete or mismatched. `src/memoryos_lite/public_benchmarks.py:270-274` simply omits the repair hook when a current case has no matching baseline row, and `src/memoryos_lite/public_repair_smoke.py:317-319` skips that row entirely in movement calculation. That means a current pass-to-fail/source regression can disappear from `fail_to_pass`, `pass_to_fail`, `unchanged_*`, and source movement counts instead of blocking the gate. Exact repair: validate that the repair baseline report has exactly one row for every `(benchmark, baseline, case_id)` in the current fixed slice, fail or mark `full_chain_gate_status` blocked on missing/extra/duplicate rows, and add a RED test proving missing baseline rows cannot be silently skipped.

3. Failure-class summary drops diagnostic classes that the real diagnostics can emit. `src/memoryos_lite/public_case_diagnostics.py:266-271` can return `evidence_retrieved_not_selected`, `evidence_selected_not_rendered`, and `evidence_rendered_not_answer_evidence`, but `src/memoryos_lite/public_repair_smoke.py:12-19` only declares the phase-facing buckets and `src/memoryos_lite/public_repair_smoke.py:323-325` ignores non-listed values. This can hide context-selection/rendering failures that Phase 17 explicitly needed visible as LoCoMo failure modes. Exact repair: normalize these diagnostics into the required phase buckets, especially `context_missing_evidence`, or include explicit separate buckets with tests for each emitted class.

Notes:

- The real public v3 path is wired behind explicit LoCoMo repair-smoke routing, and repair execution requires `MEMORYOS_AGENT_KERNEL=v1`; I did not find evidence that the v3 kernel was enabled by default.
- The recorded eval commands used `--llm-answer --llm-judge` for both LoCoMo baseline and repair smoke, and the summary correctly marks same-slice repair smoke as non-promotion evidence.
- Residual issue before merge: `src/memoryos_lite/public_repair_smoke.py` is currently untracked in `git status`, so the tracked diff alone is not reproducible.
