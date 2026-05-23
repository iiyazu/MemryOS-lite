# phase: phase-15

# Task 2 Repair Result

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle used:
`.hermes-loop/work/phase-15/context_bundle.md`

Repair basis:
`.hermes-loop/work/phase-15/task2_code_review.md`

Blocking findings addressed:
- Added direct helper tests in `tests/test_agent_kernel.py` so Task 2 behavior is exercised before runner wiring.
- Replaced the helper result shape with `ToolSelectionResolution`, including `rejected_inputs`, `selection_payload`, selected request, and denied state.
- Added `ToolSelectionBoundary.resolve()` and kept `select()` as a compatibility wrapper.
- Preserved approval-bound candidates with empty `source_refs`; selection is not treated as an execution grant, and source/approval provenance remains enforced by the existing approval/execution path.
- Added unsupported-input, selector fail-closed, explicit no-op, duplicate-id, and approval-bound direct boundary coverage.

Verification:

```text
uv run pytest tests/test_agent_kernel.py::test_tool_selection_boundary_reports_unsupported_input_without_runner tests/test_agent_kernel.py::test_tool_selection_boundary_preserves_approval_bound_candidate_without_source_refs tests/test_agent_kernel.py::test_tool_selection_boundary_fail_closed_selector_outputs_without_runner tests/test_agent_kernel.py::test_tool_selection_boundary_denies_duplicate_candidate_ids_without_runner -q
8 passed in 0.17s
```

```text
uv run ruff check src/memoryos_lite/agent_tool_selection.py tests/test_agent_kernel.py
All checks passed!
```

Remaining expected failures:
The full `tests/test_agent_kernel.py` suite still requires Task 3 runner wiring before K2 trace ordering and replay binding can pass.
