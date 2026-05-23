# phase: phase-15

PASS

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle used:
`.hermes-loop/work/phase-15/context_bundle.md`

Reviewed artifacts:
- `.hermes-loop/work/phase-15/plan_final.md`
- `.hermes-loop/work/phase-15/task1_code_review.md`
- `.hermes-loop/work/phase-15/task1_red_repair.md`
- `tests/test_agent_kernel.py`

Spec verdict:
The repaired Task 1 tests match the accepted K2-first scope. They are test-only, phase-bound, and target the real `SimpleAgentStepRunner.run_step()` path through the planned constructor injection point. They do not implement planner behavior, do not enable the kernel by default, and do not introduce benchmark score targets or gold-field leakage.

Evidence:
- Accepted-selection coverage now asserts `tool_candidates_generated` before `tool_selected` before policy.
- Candidate payload coverage asserts `archive_write` only, declared `tool_call_id`, `candidate_reason`, and constraints.
- Selection coverage asserts the selected `tool_call_id` came from generated candidates and carries deterministic provenance.
- Fail-closed coverage includes non-candidate selection, selector timeout, malformed selector output, and missing provenance before policy/execution/mutation.
- Approval replay coverage binds successful and idempotent resume paths to the original pending `tool_call_id`, with separate tampered and missing `tool_call_id` denial cases.

RED verification:
`uv run pytest tests/test_agent_kernel.py -q` exits with status 2 because `memoryos_lite.agent_tool_selection` does not exist yet. That is the expected Task 1 RED failure before production implementation.
