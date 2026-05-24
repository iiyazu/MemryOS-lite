# phase: phase-17

/goal Implement the phase-17 LoCoMo repair-smoke harness as a real MemoryOS v3/public benchmark path, using only opt-in `MEMORYOS_AGENT_KERNEL=v1` kernel maintenance tools, with tests and case-level evidence aligned to the active goal.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `work/phase-17/context_bundle.md`.
Plan: `work/phase-17/plan_final.md`.

## Allowed Real Path

This phase may change only the real public MemoryOS v3 repair-smoke path:

- `src/memoryos_lite/public_repair_smoke.py` for sanitized repair proposals, execution traces, and comparison summaries.
- `src/memoryos_lite/evals.py` for a private pre-context repair hook in the existing `memoryos_lite` public baseline path.
- `src/memoryos_lite/public_benchmarks.py` for explicit repair-smoke routing/report fields and summary writing.
- `src/memoryos_lite/cli.py` for an explicit `--repair-smoke-baseline-report` option.
- Focused tests in `tests/test_public_benchmarks.py`, with `tests/test_agent_kernel.py`, `tests/test_context_composer.py`, or `tests/test_memory_lifecycle.py` only if needed for real kernel/v3 visibility coverage.

## Required Artifacts

- `work/phase-17/result.md`
- focused RED/GREEN tests before production changes
- `work/phase-17/execute_review.md`
- case-level LoCoMo repair-smoke evidence or a documented provider blocker

## Non-Goals And Prohibitions

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change default `v3` architecture or remove explicit `MEMORYOS_MEMORY_ARCH=v1`.
- Do not add Letta as a runtime dependency.
- Do not write benchmark fixtures or direct-store repair artifacts as success evidence.
- Do not let expected answers, expected source ids, judge labels, failure classes, movement labels, or benchmark case ids enter executable tool arguments.
- Do not claim same-slice or no-LLM evidence as full-chain quality evidence.
- Do not use benchmark case-id hacks or expected-answer leaks.

Max repair cycles: 2.

Benchmark results are diagnostic evidence only, not goal constraints. If eval evidence regresses or provider access is unavailable, classify the failure and choose `repair`, `repeat_phase`, `god_adjust`, or `hold`; do not loop on score improvement.
