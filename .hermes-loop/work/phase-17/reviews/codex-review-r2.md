# phase: phase-17

Verdict: PASS

Blocking findings: none.

Prior FAIL blockers rechecked:

- Judge-pass/source-miss rows are no longer hidden under generic retrieval miss. `src/memoryos_lite/public_repair_smoke.py:466` normalizes judged-pass rows with missing source metrics into `source_miss_judge_pass`, before generic failure-class bucketing. The r3 summary reports `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]` and leaves `retrieval_miss` to the remaining judged fail `conv-26_qa_008`.
- Same-slice row mismatch is now visible and gate-blocking. `src/memoryos_lite/public_repair_smoke.py:302` sets `full_chain_gate_status="blocked_baseline_mismatch"` when coverage is invalid, and `src/memoryos_lite/public_repair_smoke.py:396` reports missing, extra, duplicate baseline, and duplicate repair case ids. Tests at `tests/test_public_benchmarks.py:4406` and `tests/test_public_benchmarks.py:4478` cover this.
- Context-selection/rendering diagnostic classes are no longer dropped. `src/memoryos_lite/public_repair_smoke.py:20` declares the aliases and `src/memoryos_lite/public_repair_smoke.py:473` maps them into `context_missing_evidence`; test coverage is at `tests/test_public_benchmarks.py:4530`.

Real-path and default-behavior notes:

- The repair is wired into the real public MemoryOS path: `_run_baseline` invokes the pre-context hook after paging and before `build_context()` at `src/memoryos_lite/evals.py:591`, and `run_public_benchmark` passes that hook only for matching repair-smoke rows at `src/memoryos_lite/public_benchmarks.py:273`.
- Repair writes execute through the opt-in kernel path, not direct fixtures: `src/memoryos_lite/public_benchmarks.py:505` calls `service.agent_kernel.run_step()`, and approval replay is handled at `src/memoryos_lite/public_benchmarks.py:515`.
- Repair smoke remains explicit LoCoMo/v3/kernel-v1 only. The request validator at `src/memoryos_lite/public_benchmarks.py:418` rejects kernel-off, non-LoCoMo, non-v3, and non-`memoryos_lite` repair-smoke runs.
- v3 default, v1 fallback, and kernel default-off are preserved; config still defaults to `memoryos_memory_arch="v3"` and `memoryos_agent_kernel="off"` in `src/memoryos_lite/config.py:29`.

Eval routing and ACK eligibility:

- LoCoMo routing is defensible: r3 baseline and repair smoke used `--llm-answer --llm-judge`, both reported `8 pass / 2 fail`, and the repair summary separately reports `fail_to_pass`, `pass_to_fail`, unchanged cases, failure classes, source metric movement, and baseline coverage.
- Same-slice repair smoke is correctly labeled diagnostic/non-promotion: the r3 summary has `full_chain_gate_status="not_satisfied"`, `promotion_gate_satisfied=false`, and `quality_gate_satisfied=false`.
- LongMemEval was not rerun. That is acceptable under the plan because the implementation is behind explicit LoCoMo repair-smoke routing and does not change default v3 retrieval/context/answer behavior.
- ACK is behaviorally eligible as a diagnostic repair-measurement phase, not as benchmark-quality promotion.

Residual non-blocking notes:

- `src/memoryos_lite/public_repair_smoke.py` is still untracked in `git status --short`; it must be added before any commit or the tracked diff will not reproduce the implementation.
- `.hermes-loop/active_job.json` is untracked and still names `phase-16`; that looks stale orchestration state and should be cleaned or reconciled by the controller before final integration.
- I reran the repaired blocker-focused tests: `uv run pytest tests/test_public_benchmarks.py -q -k 'repair_smoke_summary_buckets_judge_pass_source_miss_separately or repair_smoke_summary_blocks_missing_extra_and_duplicate_baseline_rows or public_repair_smoke_summary_preserves_duplicate_baseline_rows or repair_smoke_summary_maps_context_diagnostic_classes'` -> `6 passed, 71 deselected`.
