# phase: phase-15

PASS

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle used:
`.hermes-loop/work/phase-15/context_bundle.md`

Review basis:
- `.hermes-loop/work/phase-15/task1_code_review.md`
- `.hermes-loop/work/phase-15/task1_red_repair.md`
- `tests/test_agent_kernel.py`

Prior blocking findings:
1. Missing durable trace assertions.
2. Positive approval replays did not carry selected `tool_call_id`.
3. Timeout-only invalid selector coverage.
4. Candidate payload and candidate-id membership not asserted.
5. Selector test behavior injected by mutating a runner attribute after construction.

Resolution:
All five blockers are addressed in the repaired tests. The tests now assert durable candidate, selected, and denial traces through `store.list_traces()`, propagate the original pending `tool_call_id` in successful/already-executed replay paths, split timeout/malformed/missing-provenance selector behavior, validate declared candidate payloads and candidate-id membership, and inject selector behavior through the planned `SimpleAgentStepRunner(..., tool_selection_boundary=...)` constructor dependency.

Remaining expected failure:
Collection fails because `src/memoryos_lite/agent_tool_selection.py` and the new K2 contracts are not implemented. This is acceptable for the RED stage and is the correct next production slice.
