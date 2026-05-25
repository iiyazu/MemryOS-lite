# feature: benchmark-layer-organization

/goal Repair the regular public benchmark comparison summary so source-metric
movement is reported independently from verdict movement, then refresh
feature-local verification and handoff artifacts.

feature_id: benchmark-layer-organization
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization
updated_at: 2026-05-25T06:43:25Z

## Real Paths

- `src/memoryos_lite/public_case_movement.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`
- `tests/test_public_benchmarks.py`
- `xmuse/work/features/benchmark-layer-organization/result.md`
- `xmuse/work/features/benchmark-layer-organization/ack.json`
- `xmuse/work/features/benchmark-layer-organization/review_verdict.json`

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

Max repair cycles: 1
