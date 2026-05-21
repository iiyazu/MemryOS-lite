# phase: phase-5

# Result: Phase 5 - Memory Lifecycle + Promotion Policy

## Modified files
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/memory_lifecycle.py`
- `tests/test_memory_lifecycle.py`

## Test results
- Focused:
  - `uv run pytest tests/test_memory_lifecycle.py tests/test_v3_contracts.py -q` -> `19 passed`
- Regression:
  - `uv run pytest -q` -> `346 passed, 1 warning`

## Change summary
- Added `PromotionCandidate`, write-source, and lifecycle status contracts.
- Added a lifecycle service that creates source-backed candidates.
- Added recall-to-archival and archival-to-core promotion helpers.
- Core promotion is approval-gated; archival promotion records history through the archival store.

