# phase: phase-8

# Result: Legacy Adapter + Deprecation Decision

## Decision

- `defer`

## Evidence

- `uv run pytest -q` -> `352 passed, 1 warning`
- Hard eval remains `1.00/1.00`
- v3 public smoke reports expose `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics`
- Legacy v1/v2 paths remain documented as the default and opt-in compatibility surfaces

## Docs Updated

- `README.md`
- `docs/source-guide.md`
- `docs/store-interface.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/memory-v3-architecture.md`
- `.hermes-loop/blueprint.md`
