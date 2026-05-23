# phase: phase-15

FAIL

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Blocking Findings

1. `tests/test_agent_kernel.py:109-159` and `tests/test_agent_kernel.py:181-185` inspect new K2 events only through `result.trace`. Phase 15 requires durable `tool_candidates_generated`, `tool_selected`, and denial traces in the real kernel path. An implementation that adds transient result events without persisting them would pass these tests.

   Required fix: assert the new candidate/selected/denied events and their required payload fields through `store.list_traces("ses_1")` (or `_trace_payloads`) as well as result ordering. Cover both the accepted-selection path and at least one fail-closed denial path.

2. The new replay contract is not applied consistently to existing successful replay coverage. The new test at `tests/test_agent_kernel.py:162-185` carries `tool_call_id`, but existing positive resumes at `tests/test_agent_kernel.py:405-452`, `tests/test_agent_kernel.py:623-627`, and `tests/test_agent_kernel.py:669-673` still replay only `approval_id`. A strict implementation that binds approval to the selected tool call would break those tests; an implementation that permits a missing selected `tool_call_id` could satisfy the old tests while weakening the new safety boundary.

   Required fix: extract the pending selected `tool_call_id` and include it in every successful or already-executed approval replay request created after K2 selection. In mismatch tests intended to isolate session/tool/content tampering, pass the valid original `tool_call_id`; add a separate missing-`tool_call_id` denial case if missing binding must fail closed.

3. `test_kernel_selector_invalid_output_falls_back_to_noop_without_mutation` at `tests/test_agent_kernel.py:147-159` does not exercise invalid selector output. `_InvalidSelector.select()` raises `TimeoutError`, so the test covers selector timeout only. It leaves malformed choices and missing provenance unguarded even though those are explicit fail-closed K2 requirements.

   Required fix: rename the timeout case accurately and add RED tests whose selectors return an invalid/non-schema choice and a candidate choice missing required provenance. Assert denial before policy/execution, no persisted tool result or archival mutation, and a fail-closed trace reason.

4. `test_kernel_generates_candidate_trace_before_selection` at `tests/test_agent_kernel.py:109-128` asserts that a candidate event exists, but never asserts what candidates were declared or that the selected `tool_call_id` is one of them. The tests can pass if the router emits an empty or misleading candidate trace while selection is constructed separately.

   Required fix: assert the generated payload declares only the Phase 15 `archive_write` candidate, includes its `tool_call_id` and `candidate_reason`/constraint provenance, and that `tool_selected.tool_call_id` equals a generated candidate id. The rejection test should likewise demonstrate that the selector-returned id is absent from the declared candidate ids.

5. `tests/test_agent_kernel.py:135` and `tests/test_agent_kernel.py:151` inject behavior by assigning `runner.tool_selection_boundary` after construction. This pins tests to an internal mutable attribute and can bypass any constructor-time boundary initialization or validation.

   Required fix: drive custom selector behavior through an explicit supported runner dependency-injection interface (for example a constructor parameter or a purpose-built test factory using that interface), then use the same interface for the non-candidate and timeout/invalid selector tests.

## Scope Notes

- The missing production imports are expected for Task 1 RED and are not a defect in this review.
- `.hermes-loop/state.json` and `.hermes-loop/active_job.json` are treated as controller/runtime baseline, not Task 1 drift.
- No tests or evals were run during this code-quality review, as instructed.
