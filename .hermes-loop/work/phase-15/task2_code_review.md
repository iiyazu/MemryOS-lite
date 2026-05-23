# phase: phase-15

# Task 2 Code Review

Verdict: FAIL.

Basis: reviewed `.hermes-loop/work/phase-15/context_bundle.md`, `.hermes-loop/work/phase-15/plan_final.md`, `.hermes-loop/work/phase-15/task2_result.md`, `src/memoryos_lite/v3_contracts.py`, `src/memoryos_lite/agent_tool_selection.py`, and `tests/test_agent_kernel.py` for the active phase-15 goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Blocking Findings

1. `ToolSelectionBoundary` does not expose the resolution contract the next runner wiring slice is planned to consume.

   - File/lines: `src/memoryos_lite/agent_tool_selection.py:25-35`, `src/memoryos_lite/agent_tool_selection.py:41-45`, `src/memoryos_lite/agent_tool_selection.py:55-64`, `src/memoryos_lite/agent_tool_selection.py:80-85`.
   - Problem: the accepted plan requires a boundary resolution with generated candidates, rejected-input diagnostics, selected request, trace-ready selection payload, and denied/no-op state. The implementation exposes `select()`, not the planned `resolve()`, and `ToolSelectionResult` has no `rejected_inputs` or trace-ready selection payload. Unsupported tool inputs become an empty candidate list with `selected_request=None` and `denied=False`, so the runner cannot reliably persist the required `tool_selection_denied` event with rejected input details without reconstructing semantics outside the boundary.
   - Risk: Task 3 can accidentally wire a partial boundary that fails closed by omission but loses durable evidence for invalid input, non-candidate routing, and no-op selection. That weakens the phase requirement that unknown/non-candidate tools stop before policy and leave auditable traces.

2. Approval-bound provenance is not modeled consistently.

   - File/lines: `src/memoryos_lite/agent_tool_selection.py:101-107`, `src/memoryos_lite/agent_tool_selection.py:139-144`; related existing executor behavior is `src/memoryos_lite/agent_kernel.py:100-119`.
   - Problem: selected candidates are denied whenever `source_refs` is empty, even if the candidate carries an `approval_id`. The existing executor accepts approval-bound writes by deriving a manual approval `SourceRef` when there are no source refs but an approval id is present. The Task 2 constraints also state only `requires_source_refs=True`, not the required `source_refs-or-bound-approval` rule from the phase plan.
   - Risk: the next runner slice may reject legitimate approval-resume requests before replay validation, or force callers to invent source refs just to pass selection. That is a source/provenance handling bug at the K2 boundary and can break public/kernel probe resume wiring if the resume relies on the persisted approval binding.

3. The current focused tests do not isolate Task 2 helper correctness.

   - File/lines: `tests/test_agent_kernel.py:64-80`, `tests/test_agent_kernel.py:132-261`.
   - Problem: the new fail-closed tests instantiate `SimpleAgentStepRunner` with `tool_selection_boundary`, but Task 2 intentionally has not wired that constructor argument. As a result, the suite fails at construction before exercising `ToolSelectionBoundary` behavior for non-candidate ids, malformed selector output, timeout fallback, missing selector provenance, duplicate ids, no-op, or unsupported input.
   - Risk: helper-level regressions in fail-closed semantics, selection provenance, and invalid fallback mutation would not be caught until Task 3 wiring work. A direct boundary test layer is needed, or the runner integration task must be treated as the first point where Task 2 behavior is actually verified.

## Non-Blocking Notes

- `ToolExecutionRequest` now carries `tool_call_id`, `selection_origin`, and `candidate_reason` in `src/memoryos_lite/v3_contracts.py:657-665`; the shape is compatible with preserving selected-call identity once the runner is wired.
- Candidate generation preserves `session_id`, `approval_id`, supplied `tool_call_id`, arguments, and source refs on selected requests in `src/memoryos_lite/agent_tool_selection.py:130-145` and `src/memoryos_lite/agent_tool_selection.py:171-180`.
- The current runner still contains the pre-Task-3 replay bug at `src/memoryos_lite/agent_kernel.py:502-504`: when pending metadata contains a `tool_call_id`, replay is denied unconditionally instead of comparing it to `request.tool_call_id`. This is already in Task 3 scope, but it is a blocking item for runner wiring if left unchanged.

## Verification

Ran:

```text
uv run pytest tests/test_agent_kernel.py -q
```

Result:

```text
14 failed, 5 passed
```

The failure pattern matches the Task 2 result: most failures are `SimpleAgentStepRunner.__init__() got an unexpected keyword argument 'tool_selection_boundary'`, plus the old trace-order path still emits `tool_policy_decision` before K2 events.

Ran:

```text
uv run mypy src/memoryos_lite/agent_tool_selection.py src/memoryos_lite/v3_contracts.py
```

Result:

```text
1 existing error in src/memoryos_lite/v3_contracts.py:501 unrelated to the Task 2 additions.
```
