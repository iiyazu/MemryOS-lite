# phase: phase-17

# Task 4: Public Runner And CLI Opt-In

## RED

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report -q
```

Result:

```text
FAILED tests/test_public_benchmarks.py::test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report
KeyError: 'enabled'
1 failed in 3.27s
```

The failure showed normal public benchmark runs returned an empty `repair_smoke` report instead of an explicit disabled/not-executed report.

## GREEN

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report -q
```

Result:

```text
1 passed in 6.02s
```

## Files Changed

- `tests/test_public_benchmarks.py`
  - Added `test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report`.
  - Covers disabled report metadata when no baseline report path is provided.
  - Covers `ValueError` when a repair-smoke baseline report is provided without `MEMORYOS_AGENT_KERNEL=v1`.
  - Covers `ValueError` for non-`memoryos_lite` expanded baseline repair-smoke requests.
  - Covers enabled execution when benchmark is LoCoMo, baseline is `memoryos_lite`, memory arch is `v3`, kernel is `v1`, and a baseline report path is provided.
- `src/memoryos_lite/public_benchmarks.py`
  - Added upfront repair-smoke request validation.
  - Reuses expanded baselines for validation and execution.
  - Emits an explicit disabled `repair_smoke` object when repair smoke is not requested.
- `src/memoryos_lite/cli.py`
  - Added `--repair-smoke-baseline-report`.
  - Passes `Path(...)` to `run_public_benchmark` only when the option is provided.

## Self-Review

- Repair smoke remains opt-in through an explicit baseline report path and explicit `MEMORYOS_AGENT_KERNEL=v1`.
- Default kernel behavior remains unchanged: normal public benchmark runs do not execute repair smoke and report `enabled: false`.
- Guarded repair smoke to LoCoMo, `MEMORYOS_MEMORY_ARCH=v3`, and expanded baseline `memoryos_lite`.
- Did not implement comparison summaries, isolation tests, no-LLM gate summaries, milestone evals, ACK edits, state edits, blueprint edits, fixture edits, eval output edits, or unrelated docs.
- Executable tool arguments in the new test use only model-visible content and aliased source refs through the existing Task 3 path.
