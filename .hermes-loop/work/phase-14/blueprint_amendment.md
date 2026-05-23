# phase: phase-14

# Blueprint Amendment: Kernel Maintenance Sequence After Phase 13

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style
agent memory system for LongMemEval and LoCoMo, without demo-only phase
completion, without hiding case-level regressions, and without enabling the
v3 kernel by default.

## Triggering Evidence

- Phase 13 completed with usable ACK after core-memory lifecycle hardening.
- Manual true full-chain 5-case LLM judge smoke after phase 13:
  - LongMemEval: `5/5`, `answer_mode=llm`, `judge_status=judge_pass`,
    `source_hit=5/5`;
  - LoCoMo: `4/5`, `answer_mode=llm`, `judge_status=judge_pass/judge_fail`,
    `source_hit=2/5`.
- The kernel default remained off in all public benchmark runs.

## Original Hypothesis

The remaining kernel work should be expanded into a broad Letta-style agent
loop with additional tools and more autonomous behavior.

## New Hypothesis

The safest next kernel step is a narrow, auditable memory-action verifier first,
followed by a diagnostic maintenance planner, then a small maintenance tool
surface, and only after that a LoCoMo repair evaluation and benchmark-governed
promotion gate.

## Affected Phases

- Phase 14 remains a narrow opt-in kernel verification phase.
- Phase 15 becomes a diagnostic maintenance planner for kernel memory actions.
- Phase 16 becomes the maintenance tool-surface phase.
- Phase 17 becomes the LoCoMo maintenance repair evaluation phase.
- Phase 18 becomes benchmark governance and promotion.

## Changed Ordering and Scope

1. Keep Phase 14 focused on `archive_write` verification and replay safety.
2. Insert a diagnostic planner phase before broadening the kernel tool surface.
3. Delay benchmark governance until maintenance artifacts have been tested
   through the real v3 context path.

## Next Minimum Verification Command

When Phase 14 executes, begin with the focused kernel tests and public trace
smoke already specified in `work/phase-14/plan_final.md`:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

## Notes

- This amendment does not enable the kernel by default.
- This amendment does not claim benchmark improvement.
- This amendment preserves the explicit `v1` fallback and `v3` default.
