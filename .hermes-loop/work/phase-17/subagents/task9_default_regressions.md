# phase: phase-17

Task 9: Default Behavior Regression Tests.

Verification:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q`
- Result: `4 passed in 4.50s`.

Self-review:
- Default public benchmark reports keep kernel traces off.
- The explicit v3 kernel opt-in path still runs a kernel step.
- Explicit `MEMORYOS_MEMORY_ARCH=v1` fallback remains separate from v3 context.
- Settings still default to the v3 composer with the agent kernel off.
- No repair-smoke behavior is active without both an explicit baseline report and `MEMORYOS_AGENT_KERNEL=v1`.
