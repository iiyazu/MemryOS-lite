# phase: phase-16

# Task 7 Policy And Public Guard Result

Context bundle path used: `.hermes-loop/work/phase-16/context_bundle.md`

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope

Finished Phase 16 Task 7 policy/public guard work:

- Added service-level guard coverage proving opt-in `MemoryOSService` requires approval for every opened Phase 16 mutating tool: `archive_write`, `archive_attach`, and `core_promotion_request`.
- Changed real `MemoryOSService` kernel construction to build approval policy rules from the explicit Phase 16 registry for tools marked `requires_approval_by_default`.
- Kept public benchmark default-off behavior covered by existing public tests and reran the opt-in structural public test.

No kernel default was changed. No read-only search, Level 3 core edit, destructive, or unknown tools were opened.

## RED

Focused RED command after temporarily restoring the previous single-tool service policy:

```bash
uv run pytest tests/test_agent_kernel.py::test_memoryos_service_opt_in_kernel_requires_approval_for_all_phase16_mutating_tools -q
```

Observed failure summary:

- The guard failed on newly opened tools because the real service policy no longer produced `approval_pending`.
- The failure showed `tool_denied` where the test expected `approval_pending`, confirming `MemoryOSService` still only required approval for `archive_write`.

This was a policy integration failure, not a syntax/import failure.

## GREEN

Focused command:

```bash
uv run pytest tests/test_agent_kernel.py::test_memoryos_service_opt_in_kernel_requires_approval_for_all_phase16_mutating_tools -q
```

Observed summary: `1 passed`.

Public guard command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Observed summary: `2 passed`.

Changed-file lint command:

```bash
uv run ruff check src/memoryos_lite/engine.py tests/test_agent_kernel.py
```

Observed summary: `All checks passed!`.

## Files Changed

- `src/memoryos_lite/engine.py`
- `tests/test_agent_kernel.py`
- `.hermes-loop/work/phase-16/subagents/task4_policy_public_result.md`

## Concerns Or Blockers

- The execute-lane codex subagent invocation timed out at the tool boundary after applying the intended code/test diff and before writing this result artifact. God independently reran RED/GREEN verification and wrote this phase-bound result from observed command evidence.
- No benchmark score target was used. The public checks are structural guard evidence only.

Status: DONE_WITH_CONCERNS
