# phase: phase-4

# Result: Phase 4 - Archival Memory Store

## Modified files
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/retrieval/__init__.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `alembic/versions/0006_add_archival_memory.py`
- `tests/test_v3_contracts.py`
- `tests/test_archival_store.py`
- `tests/test_archival_searcher.py`
- `tests/test_core_memory_store.py`

## Test results
- Focused:
  - `uv run pytest tests/test_v3_contracts.py tests/test_archival_store.py tests/test_archival_searcher.py -q` -> `21 passed`
- Regression:
  - `uv run pytest -q` -> `343 passed, 1 warning`

## Change summary
- Added archival contracts for documents, chunks, passages, memories, history, and attachments.
- Added SQLite archival tables and store CRUD/helper methods with source-backed write enforcement.
- Added a standalone archival passage searcher with text, vector, and hybrid modes.
- Added Alembic migration `0006_add_archival_memory` and updated DB head stamping.
- Updated the stale core-memory migration head expectation to the new archival head.

