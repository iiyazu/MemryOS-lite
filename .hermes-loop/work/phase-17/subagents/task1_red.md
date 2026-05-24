# phase: phase-17

# Task 1 RED Report

## Scope

Added RED-only tests in `tests/test_public_benchmarks.py` for:

- `test_repair_smoke_denies_gold_fields_in_executable_tool_request`
- `test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids`

No production source was created or edited.

## Command

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_denies_gold_fields_in_executable_tool_request tests/test_public_benchmarks.py::test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids -q
```

## RED Result

Result: expected failure, `2 failed`.

Both tests fail while importing the planned repair-smoke API:

```text
ModuleNotFoundError: No module named 'memoryos_lite.public_repair_smoke'
```

This confirms RED because `src/memoryos_lite/public_repair_smoke.py` has not
been implemented yet.
