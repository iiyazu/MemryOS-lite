# Plan Final: benchmark-layer-organization

feature_id: benchmark-layer-organization
updated_at: 2026-05-25T06:43:25Z

## Goal

Repair one in-scope diagnostics gap left by the previous partial ACK: regular
public comparison summaries reported verdict movement and current failure
boundaries, but did not report source-metric movement independently.

## Files

Product:

- `src/memoryos_lite/public_case_movement.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`

Tests:

- `tests/test_public_benchmarks.py`

Artifacts:

- `xmuse/work/features/benchmark-layer-organization/*`

## TDD Steps

1. RED: extend the public benchmark movement-summary test to expect
   `source_metric_movement`.
2. GREEN: preserve baseline source metrics from comparison reports in
   per-case diagnostics and summarize improved/regressed/unchanged source
   metrics.
3. REFACTOR: keep the summary append-only and leave verdict movement unchanged.
4. Post-review hardening: document omitted missing metric values and verify
   unchanged hit/miss buckets.

## Gates

- Focused public benchmark movement tests.
- Focused recall, composer, and public diagnostics tests.
- Targeted mypy for touched source modules.
- Full pytest.
- Ruff.
- Full mypy and hard eval recorded as gate evidence, even if pre-existing
  blockers remain.

## Non-Goals

- No benchmark score optimization.
- No public LLM full-chain claim without provider credentials.
- No default change for `MEMORYOS_RECALL_PIPELINE`, `MEMORYOS_MEMORY_ARCH`, or
  `MEMORYOS_AGENT_KERNEL`.
- No archive-rag work.
