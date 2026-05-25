# feature: benchmark-layer-organization

/goal Repair the default v3 hard-eval mismatch, refresh verification evidence,
and update feature-local handoff artifacts without changing feature defaults or
claiming public benchmark improvement.

feature_id: benchmark-layer-organization
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization
updated_at: 2026-05-25T07:52:36Z

## Real Paths

- `src/memoryos_lite/evals.py`
- `tests/test_evals.py`
- `xmuse/work/features/benchmark-layer-organization/context_bundle.md`
- `xmuse/work/features/benchmark-layer-organization/plan_final.md`
- `xmuse/work/features/benchmark-layer-organization/execute_goal.md`
- `xmuse/work/features/benchmark-layer-organization/result.md`
- `xmuse/work/features/benchmark-layer-organization/execute_review.md`
- `xmuse/work/features/benchmark-layer-organization/review_verdict.json`
- `xmuse/work/features/benchmark-layer-organization/ack.json`
- `xmuse/work/features/benchmark-layer-organization/slave_state.json`
- `xmuse/work/features/benchmark-layer-organization/feature_amendment_proposal.json`

## Required Artifacts

- `context_bundle.md`
- `plan_final.md`
- `execute_goal.md`
- `result.md`
- `execute_review.md`
- `review_verdict.json`
- `ack.json`
- `slave_state.json`
- `feature_amendment_proposal.json`

## Constraints

- Demo-only or stub-only completion is forbidden.
- Benchmark scores are diagnostic evidence only, not goal constraints.
- Same-slice no-LLM public diagnostics are not promotion evidence.
- Preserve v3 default, v1 fallback, v2 opt-in, kernel opt-in, SQLite authority,
  and source attribution.
- Do not touch archive-rag scope, Master-owned artifacts, approval artifacts, or
  another feature worktree.

Max repair cycles: 1
