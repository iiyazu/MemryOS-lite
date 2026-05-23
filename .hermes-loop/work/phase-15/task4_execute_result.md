# phase: phase-15

# Task 4 Execute Result

Context bundle: `.hermes-loop/work/phase-15/context_bundle.md` was read before phase-local plan artifacts.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Task 4 scope checked:

- Preserves public benchmark default-off kernel behavior.
- Verifies opt-in `MEMORYOS_AGENT_KERNEL=v1` public kernel probe trace includes `tool_candidates_generated` and `tool_selected` in both the initial and resumed kernel steps.
- Verifies resumed public probe carries pending approval `metadata.tool_call_id` into `tool_request.model_copy(update={...})`, allowing approval replay to grant and execute.
- No planner work implemented for this task.
- No default kernel enablement, state mutation, public answer, judge, scoring, or case aggregation behavior changes were made for this task.

Files changed for Task 4:

- `src/memoryos_lite/evals.py`: resumed public opt-in kernel probe now extracts the `approval_pending` event, keeps its `approval_id`, and copies `payload["metadata"]["tool_call_id"]` into the resumed `ToolExecutionRequest`.
- `tests/test_public_benchmarks.py`: opt-in public kernel probe test now expects `tool_candidates_generated` and `tool_selected` in both initial and resumed traces, and checks selected `tool_call_id` continuity from approval metadata through resume.

RED evidence observed from god controller:

- After updating the public opt-in test first, `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q` failed because the resumed opt-in trace showed `approval_replay_denied`.
- After updating `src/memoryos_lite/evals.py` to resume with both `approval_id` and `tool_call_id`, the same command passed with `2 passed in 3.08s`.

Fresh verification:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Result:

```text
..                                                                       [100%]
2 passed in 3.15s
```

Concerns:

- The wider worktree contains non-Task-4 phase-15 changes in `src/memoryos_lite/agent_kernel.py`, `src/memoryos_lite/v3_contracts.py`, `tests/test_agent_kernel.py`, and `.hermes-loop/state.json`, plus new phase-local artifacts. I did not modify or revert those. Task 4 review was limited to the public benchmark boundary diff in `src/memoryos_lite/evals.py` and `tests/test_public_benchmarks.py`.
- `.hermes-loop/state.json` is modified in the worktree; Task 4 instructions say not to touch it, and this execute pass did not edit it.
