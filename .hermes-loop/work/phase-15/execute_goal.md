# phase: phase-15

/goal Implement the Phase 15 K2 hybrid tool-selection boundary in the real opt-in MemoryOS v3 kernel path, then add diagnostic-only public maintenance planner sidecar artifacts only if the K2 focused gate is green.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Real MemoryOS path this phase may change:

- `src/memoryos_lite/v3_contracts.py`: add minimal tool candidate, selection choice, and selected request provenance contracts.
- `src/memoryos_lite/agent_tool_selection.py`: add a small deterministic router/selector boundary for `archive_write` candidates only.
- `src/memoryos_lite/agent_kernel.py`: invoke the K2 boundary from `SimpleAgentStepRunner.run_step()` before policy, approval, execution, verification, and trace persistence.
- `src/memoryos_lite/evals.py`: preserve the opt-in public benchmark kernel probe by carrying the selected `tool_call_id` across approval resume.
- Conditional only after K2 tests pass: `src/memoryos_lite/public_maintenance_planner.py` and additive public benchmark report fields for proposal-only planner artifacts with eval-only sidecars.

Required artifacts:

- `.hermes-loop/work/phase-15/result.md`
- focused RED/GREEN tests before production changes
- `.hermes-loop/work/phase-15/execute_review.md`
- review lane artifacts and ACK only after usable evidence

Explicit non-goals and prohibitions:

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change the `MEMORYOS_MEMORY_ARCH=v3` default or `MEMORYOS_MEMORY_ARCH=v1` fallback.
- Do not add Letta as a runtime dependency.
- Do not open Phase 16 tools such as `core_memory_append`, `core_memory_replace`, `archive_attach`, `core_promotion_request`, retrieval repair execution, or broad tool registry behavior.
- Do not execute planner proposals in Phase 15.
- Do not put expected answers, expected source ids, judge labels, gold-derived failure targets, movement labels, or case-specific repair ids into executable payloads, source refs, candidate ids, archive ids, passage links, memory contents, or selected tool arguments.
- Do not treat a helper-only implementation, CLI/demo path, or report-only artifact as usable unless it is wired into the real `SimpleAgentStepRunner.run_step()` and public opt-in path where applicable.

Max repair cycles: 2.

Benchmark scores are diagnostic evidence only, not goal constraints. If a benchmark or smoke regresses, classify the failure and choose `repair`, `repeat_phase`, `god_adjust`, or `hold`; do not loop on score improvement.
