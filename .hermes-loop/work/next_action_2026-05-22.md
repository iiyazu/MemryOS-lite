# phase: phase-5

# Controller Next Action - Phase 5 GOD_DISPATCH

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Current State

- `.hermes-loop/state.json` has `current_state = "GOD_DISPATCH"`.
- `execute_lane.phase = "phase-5"` and `execute_lane.state = "GOD_DISPATCH"`.
- `plan_lane.phase = "phase-6"` and `plan_lane.state = "PLAN_STORM"`.
- `research_lane.phases = ["phase-7"]`.
- Phase 4 has usable ACK evidence at `work/phase-4/ack.json`.
- Phase 4 review PASS is at `work/phase-4/reviews/codex-review.md` and `work/phase-4/review_verdict.json`.
- Phase 4 reflection recommends no blueprint amendment and a narrowed Phase 5 dispatch.

## Phase 5 Dispatch Direction

Start Phase 5 by generating or refreshing:

```text
work/phase-5/context_bundle.md
work/phase-5/god_dispatch.json
```

The dispatch should focus Phase 5 on LoCoMo temporal/session context accounting and query-to-evidence-to-final-context traceability, not broad composer rewrites.

Carry forward these phase-4 facts:

- LongMemEval 30 full-chain v3: 17 pass / 13 fail.
- LoCoMo 30 full-chain v3: 0 pass / 30 fail.
- LoCoMo failures: retrieval_miss=11, context_missing_evidence=10, evidence_hit_answer_fail=9.
- Public benchmark cases did not seed attached archives, so phase-4 archival totals were zero and must not be claimed as archive-quality improvement.
- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` fallback remains explicit.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.

## Minimum Guard Before Phase 5 Planning

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Then add a Phase 5 RED test for LoCoMo temporal/session evidence preserving enough neighboring context before changing composer behavior.
