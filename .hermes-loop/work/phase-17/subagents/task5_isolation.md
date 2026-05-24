# phase: phase-17

# Task 5: Isolation And No Direct Fixture Writes

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `work/phase-17/context_bundle.md`.

## RED

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run -q
```

Result:

```text
FAILED tests/test_public_benchmarks.py::test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run
KeyError: 'data_dir'
1 failed in 14.70s
```

The failure showed the repair-smoke report did not yet expose the isolated eval run data directory, so the test could not prove that the explicit repair run used only its run-local store.

## GREEN

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run -q
```

Result:

```text
1 passed in 4.43s
```

## Files Changed

- `tests/test_public_benchmarks.py`
  - Added `test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run`.
  - The test runs default-off, explicit opt-in repair smoke, then default-off again with a fresh run id.
  - It checks disabled default reports, repair tool execution, unchanged benchmark input file, and absence of repair artifacts from the second default run/report/store.
- `src/memoryos_lite/public_benchmarks.py`
  - Added repair-smoke `data_dir` metadata from `service.settings.data_dir` to expose the isolated public eval run store used by the repair hook.

## Self-Review

- Repair smoke remains explicit opt-in through both `MEMORYOS_AGENT_KERNEL=v1` and `repair_smoke_baseline_report_path`.
- Default public v3 runs still report disabled repair smoke and empty kernel traces.
- The benchmark fixture JSON remains read-only during the test.
- The repair artifact is checked inside the explicit repair run store and checked absent from the fresh default run store.
- No state, blueprint, ACK, benchmark fixture, or eval output files were intentionally edited.
