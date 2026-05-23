# phase: phase-15

PASS

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Corrected Baseline

This rerun applies the required correction from `task1_spec_review_decision.md`:

- `.hermes-loop/state.json` was changed by God before Task 1 under the bootstrap rule and is not Task 1 scope drift.
- `.hermes-loop/active_job.json` was a preexisting untracked runtime/control artifact and is not Task 1 scope drift.
- Task 1 is judged by the actual implementer changes: `tests/test_agent_kernel.py` and `.hermes-loop/work/phase-15/task1_red.md`.

## Blocking Findings

None.

## Review Findings

- Task 1 is test-only plus a phase-bound RED artifact. No `src/`, docs, benchmark data, state, or runtime-control files are accepted as Task 1 implementation output.
- `.hermes-loop/work/phase-15/task1_red.md` starts with `# phase: phase-15`, records the active goal, records the focused command, and reports the expected RED result: collection failure on missing `memoryos_lite.agent_tool_selection`.
- The RED signal is acceptable because Task 1 intentionally references the planned K2 helper/contracts before production implementation.
- `tests/test_agent_kernel.py` adds candidate trace coverage before policy: `kernel_step_started`, `tool_candidates_generated`, `tool_selected`, then `tool_policy_decision`, with `selection_origin`, `candidate_reason`, and generated `tool_call_id` assertions.
- Non-candidate selector output is covered before policy, execution, and mutation: the test expects `tool_selection_denied`, excludes `tool_policy_decision` and `tool_executed`, and asserts no archival write.
- Selector failure fallback is covered as no-op/no mutation: the timeout selector expects fallback denial, no policy event, and no archival write.
- Selected provenance through approval replay is covered by carrying the pending `tool_call_id` into replay and asserting selected trace provenance plus `approval_granted`.
- Tampered `tool_call_id` replay denial is covered by expecting `approval_replay_denied`, no approval grant, no execution, no verification, no archival write, and no tool message.
- No benchmark score targets were added.
- No default kernel behavior is changed, and `MEMORYOS_AGENT_KERNEL=v1` remains opt-in because Task 1 does not modify production configuration or benchmark routing.

## Required Fixes

None.
