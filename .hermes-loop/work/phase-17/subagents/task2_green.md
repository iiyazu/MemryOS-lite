# phase: phase-17

# Task 2 GREEN Report

## Scope

Created `src/memoryos_lite/public_repair_smoke.py` with:

- `ExecutableRepairProposal`
- `build_executable_repair_proposal(row, source_id_aliases)`

The implementation keeps executable repair requests bounded to existing
registry-opened kernel tools, denies gold-derived executable payloads, requires
model-visible source refs, rewrites source refs through repair-store aliases
before `ToolExecutionRequest` construction, and scans the final executable
request for forbidden benchmark/gold values.

No public benchmark runner, evals, CLI, state, blueprint, ACK, eval report, or
benchmark fixture files were edited.

## Command

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_denies_gold_fields_in_executable_tool_request tests/test_public_benchmarks.py::test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids -q
```

## GREEN Result

Result: `2 passed in 0.06s`.

The command also emitted the existing environment warning:

```text
warning: `VIRTUAL_ENV=/home/iiyatu/.hermes/hermes-agent/venv` does not match the project environment path `.venv` and will be ignored; use `--active` to target the active environment instead
```

## Self-Review

- Gold leakage: raw tool arguments are checked against `eval_gold_sidecar` and
  row case id values only for denial, and the final `ToolExecutionRequest`
  serialization is checked again after alias rewriting.
- Source grounding: source refs must be present in `model_visible_planner_input`
  and must have a `source_id_aliases` mapping before they can become executable
  `SourceRef` values.
- Registry boundary: unknown or unopened tool names are denied via
  `executable_kernel_tool_names()`.
- Scope: production edits were limited to `src/memoryos_lite/public_repair_smoke.py`;
  the existing Task 1 tests in `tests/test_public_benchmarks.py` were not
  modified by this GREEN task.
