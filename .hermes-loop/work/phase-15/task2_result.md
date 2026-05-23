# phase: phase-15

# Task 2 Result

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Status: completed for the Task 2 contract/boundary slice. The focused kernel suite still has expected runner integration failures for Task 3 because `SimpleAgentStepRunner` has not been wired to `ToolSelectionBoundary`.

Files changed:

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/agent_tool_selection.py`
- `.hermes-loop/work/phase-15/task2_result.md`

Implemented:

- Added `ToolSelectionOrigin = Literal["deterministic", "llm", "fallback"]`.
- Added `ToolCandidate` and `ToolSelectionChoice`.
- Extended `ToolExecutionRequest` with `tool_call_id`, `selection_origin`, and `candidate_reason`.
- Added a small deterministic `ToolSelectionBoundary` that:
  - generates `archive_write` candidates only;
  - keeps candidate constraints and candidate reasons;
  - validates selector output;
  - denies non-candidate, duplicate, malformed, timeout, and missing-provenance selections without creating an executable request;
  - preserves `session_id`, `approval_id`, `tool_call_id`, `selection_origin`, and `candidate_reason` on selected executable requests.

Verification:

```text
uv run pytest tests/test_agent_kernel.py -q
14 failed, 5 passed in 21.07s
```

Failure summary:

- Most failures are `TypeError: SimpleAgentStepRunner.__init__() got an unexpected keyword argument 'tool_selection_boundary'`.
- One existing runner-path failure shows the old trace order still emits `tool_policy_decision` before `tool_candidates_generated` / `tool_selected`.

These remaining failures are expected Task 3 runner integration failures under the Task 2 instruction not to wire `SimpleAgentStepRunner` yet.

Additional syntax/lint check:

```text
uv run ruff check src/memoryos_lite/v3_contracts.py src/memoryos_lite/agent_tool_selection.py
All checks passed!
```
