# phase: phase-16

# Task 1/2 Registry And Selection Boundary Result

Context bundle path used: `.hermes-loop/work/phase-16/context_bundle.md`

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope

Implemented only Phase 16 TDD Task 1 and Task 2:

- RED tests for registry, `ToolSelectionBoundary` `archive_attach`/`core_promotion_request` candidates, non-session attach denial, and fail-closed unopened tools.
- GREEN registry and selection boundary implementation.

No archive attach execution, core promotion persistence, migrations, public eval changes, or result/ACK artifacts were implemented.

## RED

Command:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_tool_registry_exposes_only_phase16_level1_tools tests/test_agent_kernel.py::test_tool_selection_boundary_generates_archive_attach_candidate_without_broad_scope tests/test_agent_kernel.py::test_tool_selection_boundary_rejects_archive_attach_non_session_scope tests/test_agent_kernel.py::test_tool_selection_boundary_generates_core_promotion_request_candidate tests/test_agent_kernel.py::test_kernel_denies_unopened_phase16_tools_before_policy_or_execution -q
```

Observed failure summary:

- `test_kernel_tool_registry_exposes_only_phase16_level1_tools` failed with `ModuleNotFoundError: No module named 'memoryos_lite.agent_tool_registry'`.
- `archive_attach` and `core_promotion_request` candidate tests failed because the boundary still rejected them as `unsupported tool for K2 selection`.
- Unopened-tool fail-closed parametrized cases passed before implementation, confirming the existing closed behavior remained intact.
- Failure was missing behavior, not syntax or import mistakes in the tests.

## GREEN

Commands:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_tool_registry_exposes_only_phase16_level1_tools tests/test_agent_kernel.py::test_tool_selection_boundary_generates_archive_attach_candidate_without_broad_scope tests/test_agent_kernel.py::test_tool_selection_boundary_rejects_archive_attach_non_session_scope tests/test_agent_kernel.py::test_tool_selection_boundary_generates_core_promotion_request_candidate tests/test_agent_kernel.py::test_kernel_denies_unopened_phase16_tools_before_policy_or_execution -q
```

Observed summary: `12 passed`.

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Observed summary: `40 passed`.

Additional changed-file lint:

```bash
uv run ruff check src/memoryos_lite/agent_tool_registry.py src/memoryos_lite/agent_tool_selection.py tests/test_agent_kernel.py
```

Observed summary: `All checks passed!`.

## Files Changed

- `src/memoryos_lite/agent_tool_registry.py`
- `src/memoryos_lite/agent_tool_selection.py`
- `tests/test_agent_kernel.py`
- `.hermes-loop/work/phase-16/subagents/task1_registry_result.md`

## Concerns Or Blockers

- No blockers for this scoped task.
- `archive_attach` and `core_promotion_request` are selectable candidates only in this task. Execution remains unsupported/fail-closed until later Phase 16 tasks add policy/service/persistence behavior.
- Existing `.hermes-loop/state.json` and phase-local untracked artifacts were present before this subtask and were not modified intentionally.

Benchmark scores were not used as targets.

Status: DONE
