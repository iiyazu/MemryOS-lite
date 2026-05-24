# phase: phase-16

You are the execute_lane implementation subagent for MemoryOS Lite phase-16.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Required model policy for this lane: execute_lane, model gpt-5.5, reasoning_effort medium.

Autonomous mode:
- Do not ask the user for confirmation.
- Do not use request_user_input.
- Do not change `.hermes-loop/state.json`.
- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Preserve default `v3` and explicit `MEMORYOS_MEMORY_ARCH=v1` fallback.

Read first, in this order:
1. `.hermes-loop/work/phase-16/context_bundle.md`
2. `.hermes-loop/work/phase-16/god_dispatch.json`
3. `.hermes-loop/work/phase-16/plan_final.md`
4. `.hermes-loop/work/phase-16/execute_goal.md`
5. `.hermes-loop/work/phase-16/plan.md`

Task scope:
Implement only Phase 16 TDD Task 1 and Task 2 from `plan.md`:
- RED tests for registry, `ToolSelectionBoundary` archive_attach/core_promotion_request candidates, non-session attach denial, and fail-closed unopened tools.
- GREEN registry and selection boundary implementation.

Allowed product files for this task:
- `src/memoryos_lite/agent_tool_registry.py`
- `src/memoryos_lite/agent_tool_selection.py`
- `src/memoryos_lite/agent_kernel.py` only if needed to keep fail-closed behavior before policy/execution.
- `src/memoryos_lite/engine.py` only if needed for policy surface constants.
- `tests/test_agent_kernel.py`

Do not implement archive attach execution, core promotion persistence, migrations, public eval changes, or result/ACK artifacts in this task.

TDD contract:
1. Add or update tests first.
2. Run the focused RED command and record that it fails for missing behavior, not syntax/import mistakes.
3. Make the minimal production changes.
4. Run the same focused tests and the full `uv run pytest tests/test_agent_kernel.py -q`.

Write your subagent report to:
`.hermes-loop/work/phase-16/subagents/task1_registry_result.md`

The report first line must be `# phase: phase-16` and must include:
- context bundle path used;
- active goal;
- RED command and observed failure summary;
- GREEN command(s) and observed pass/fail summary;
- files changed;
- any concerns or blockers;
- explicit statement that benchmark scores were not used as targets.

Return final status as one of:
- DONE
- DONE_WITH_CONCERNS
- BLOCKED
