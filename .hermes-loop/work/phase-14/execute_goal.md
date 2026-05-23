# phase: phase-14

# Phase 14 Execute Goal

/goal Improve the opt-in MemoryOS v3 kernel memory-action audit path so an approved `archive_write` action is durably executed, store/context verified, and traceable through real MemoryOS v3/public path wiring and the real public-kernel smoke path, while preserving v3 default behavior, v1 fallback, and kernel opt-in status.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Real Path Allowed To Change

- `src/memoryos_lite/agent_kernel.py`: opt-in `SimpleAgentStepRunner` and `SimpleToolExecutionManager` approval, execution, replay, verification, and trace behavior.
- `src/memoryos_lite/v3_contracts.py`: structured result payload needed to carry post-action verification.
- `tests/test_agent_kernel.py`: RED/GREEN coverage for approval replay, unsupported tools, durable positive verification, durable negative verification, and same-session v3 archival visibility.
- `tests/test_public_benchmarks.py`: public benchmark smoke expectations for default-off kernel traces and opt-in kernel trace shape.

## Required Artifacts

- `work/phase-14/result.md`;
- `work/phase-14/red_result.md`;
- `work/phase-14/execute_review.md`;
- focused tests for the changed kernel/public-smoke behavior.

## Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change public benchmark scoring, answer projection, judge behavior, or retrieval ranking.
- Do not implement core-memory mutation tools in this phase.
- Do not add Letta as a runtime dependency.
- Do not use benchmark expected answers, expected sources, or case IDs as executable tool arguments.
- Do not claim LongMemEval or LoCoMo improvement from structural kernel trace evidence.

Max repair cycles: 2.

Benchmark scores are diagnostic evidence only, not goal constraints. If benchmark or smoke evidence regresses, classify the failure and choose `repair`, `repeat_phase`, `god_adjust`, or `hold`; do not optimize toward a score target.
