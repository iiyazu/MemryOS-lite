# phase: phase-17

# Execute Self-Review

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle used: `work/phase-17/context_bundle.md`.

## Real Chain Changed

- The public LoCoMo benchmark path can now run an explicit repair-smoke mode from a baseline public report.
- Repair-smoke proposals are sanitized from model-visible planner artifacts, source ids are rewritten to repair-store aliases, and expected answers/source ids/case ids/judge labels/failure labels are blocked from executable tool payloads.
- Approved repair proposals execute through the opt-in v3 kernel and Phase 16 tool services, not direct store writes.
- Repair archive artifacts are reported only after tool verification and are checked for session attachment and v3 archive eligibility.
- Repair comparison summaries list case-level movement, failure classes, source-metric movement, baseline coverage, full-chain gate status, and provider-blocked status.
- Review FAIL blockers were fixed: judge-pass/source misses are visible, mismatched baseline rows block the gate, and context-selection/rendering diagnostic classes map to `context_missing_evidence`.

## Demo-Only Or Partial Risk

- Not demo-only: tests and LoCoMo r3 eval exercised the real public v3 path and opt-in kernel path.
- Remaining limitation: the fixed LoCoMo 10 same-slice repair smoke did not improve source metrics or judged pass/fail. It executed `archive_write` for 4 rows and remained `8 pass / 2 fail` on the r3 same-slice comparison.
- Same-slice movement is explicitly diagnostic and does not satisfy a promotion gate.

## Tests Proving Behavior

- RED summary tests failed before repair: `5 failed, 71 deselected`.
- RED public-runner duplicate-baseline test failed before repair: `1 failed, 76 deselected`.
- Focused repair tests: `6 passed, 71 deselected`.
- Public benchmark module: `77 passed in 66.59s`.
- Agent kernel module: `48 passed in 56.75s`.
- Context composer and lifecycle: `22 passed in 12.23s`.
- Full suite: `536 passed, 1 warning in 682.50s`.
- Ruff: `All checks passed!`.
- New module mypy: `uv run mypy src/memoryos_lite/public_repair_smoke.py` -> success.
- Full project mypy remains blocked by unrelated pre-existing type errors outside the phase scope.

## Benchmark Cases

- Baseline `phase17_locomo10_baseline_r3`: `8 pass / 2 fail`, LLM answer/judge enabled.
- Repair `phase17_locomo10_kernel_repair_smoke_r3`: `8 pass / 2 fail`, LLM answer/judge enabled and explicit `MEMORYOS_AGENT_KERNEL=v1`.
- `fail_to_pass=[]`
- `pass_to_fail=[]`
- `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`
- `unchanged_pass=["conv-26_qa_001","conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005","conv-26_qa_007","conv-26_qa_009","conv-26_qa_010"]`
- `retrieval_miss=["conv-26_qa_008"]`
- `evidence_hit_answer_fail=["conv-26_qa_006"]`
- `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`
- Source metric regressions: none.
- Baseline coverage: valid, no missing/extra/duplicate rows.
- Executed repair tools: 4 `archive_write`; verified session-attached archive artifacts: 4.

## Constraints Check

- v1 fallback preserved: covered by full suite, including explicit v1 fallback tests.
- v3 default preserved: covered by settings/default composer tests.
- Kernel default unchanged: covered by public benchmark kernel-default-off tests; repair smoke requires explicit `MEMORYOS_AGENT_KERNEL=v1`.
- No benchmark quality claim is made from same-slice repair smoke.
- No LongMemEval regression guard was run because default v3 retrieval/context/answer behavior is unchanged outside explicit repair-smoke mode.
