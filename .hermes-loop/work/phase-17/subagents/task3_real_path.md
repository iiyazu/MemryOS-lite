# phase: phase-17

# Task 3: Real Public Path Insertion Point

## RED

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context -q
```

Result:

```text
FAILED tests/test_public_benchmarks.py::test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context
TypeError: run_public_benchmark() got an unexpected keyword argument 'repair_smoke_baseline_report_path'
1 failed in 0.37s
```

## GREEN

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context -q
```

Result:

```text
1 passed in 3.31s
```

## Files Changed

- `tests/test_public_benchmarks.py`
  - Added `test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context`.
- `src/memoryos_lite/evals.py`
  - Added private optional `PreContextHook` support to `_run_baseline`.
  - Invokes the hook only on the real `memoryos_lite` baseline path after `service.page(source_session.id)` and before `service.build_context(...)`.
  - Carries hook metadata through `BaselineOutput.repair_smoke`.
- `src/memoryos_lite/public_benchmarks.py`
  - Added optional `repair_smoke_baseline_report_path: Path | None = None`.
  - Loads matching repair-smoke baseline rows and passes a private pre-context hook into `_run_baseline`.
  - Executes sanitized `ToolExecutionRequest` proposals through `SimpleAgentStepRunner.run_step()` approval/replay flow when the opt-in kernel is enabled.
  - Emits minimal `repair_smoke` row metadata without serializing gold/case source ids into executable tool arguments.
- `.hermes-loop/work/phase-17/subagents/task3_real_path.md`
  - Added this Task 3 execution report.

## Self-Review

- Kept `MEMORYOS_AGENT_KERNEL` default off; repair execution occurs only when the existing service has `agent_kernel` enabled.
- Preserved explicit `MEMORYOS_MEMORY_ARCH=v1` fallback behavior; the hook is only reachable inside the existing `memoryos_lite` baseline branch and does not change v1 selection.
- Repair writes occur before v3 context build through `SimpleAgentStepRunner.run_step()` and the existing `archive_write` approval/replay flow.
- Repair artifacts are consumed by the real v3 context path through archival attachment eligibility; no direct context injection was added.
- The positive fixture uses model-visible non-gold content for executable arguments.
- The repair-smoke report metadata contains aliased source ids such as `repair_msg_001` and the kernel trace, and the targeted test asserts it does not serialize the expected answer or original benchmark source id.
- Did not implement CLI, comparison summaries, broad gating, milestone evals, ACK, or state changes for this task.
