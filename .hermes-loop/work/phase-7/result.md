# phase: phase-7

# Result: Benchmark + Evaluation Compatibility

## Changes

- Added v3 context diagnostics to `BaselineOutput` and public benchmark reports:
  - `memory_arch`
  - `v3_context`
  - `v3_layer_counts`
  - `v3_budget_decisions`
  - `v3_diagnostics`
- Added a public benchmark regression test proving v3 reports expose those fields while legacy metric keys remain present.

## Verification

- RED: `uv run pytest -q tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics`
  - Failed with `KeyError: 'memory_arch'`
- GREEN: same command
  - `1 passed`
- Focused regression:
  - `uv run pytest -q tests/test_public_benchmarks.py tests/test_public_benchmarks_items.py tests/test_evals.py tests/test_context_composer.py`
  - `62 passed`
- Full suite:
  - `uv run pytest -q`
  - `352 passed, 1 warning`
- Hard eval:
  - `uv run memoryos eval run --case-set hard --baseline memoryos_lite`
  - `accuracy=1.00`, `source_accuracy=1.00`, `cases=16`
- v3 public smoke:
  - `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id v3_lme_phase7_smoke`
  - report: `.memoryos/evals/v3_lme_phase7_smoke_longmemeval.json`
  - `memory_arch=v3`, `v3_layer_counts` present, `v3_budget_decisions` present, `v3_diagnostics` present
  - `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id v3_locomo_phase7_smoke`
  - report: `.memoryos/evals/v3_locomo_phase7_smoke_locomo.json`
  - `memory_arch=v3`, `v3_layer_counts` present, `v3_budget_decisions` present, `v3_diagnostics` present
