# archive-rag result

feature_id: `archive-rag`
branch: `feat/archive-rag`
worktree: `/home/iiyatu/projects/python/memoryOS-archive-rag`
target branch: `feat/phase-2.5-3-retrieval-agent`
final head: `ace77bdf7fa7f8f3ac596e93b12c07e45bd61b02`
status: `blocked`
ack_level: `blocked`

## Summary

Audited the existing archive-rag implementation at `203a9c2` against the active
blueprint and plan. The implementation contains the passage-centered archival
vector boundary, archive-specific Qdrant provider, SQLite rehydration helper,
vector-primary searcher path, composer diagnostics, engine wiring, and focused
tests.

This run made one follow-up commit:

- `ace77bd fix: enable archival vector default`

The follow-up aligns `Settings.memoryos_archival_vector_enabled` with the
accepted plan default and updates the settings test while preserving default
`v3`, explicit `MEMORYOS_MEMORY_ARCH=v1`, default kernel `off`, and v2 recall
opt-in semantics.

The feature is not usable for Master review yet because required full gates did
not pass: `uv run mypy src` fails, and the hard eval reports `0.56/0.56` rather
than the stated `1.00/1.00` baseline.

No merge was performed. No approval artifacts or Master-owned artifacts were
written.

## Changed Files

Existing implementation commit `203a9c2` changed:

- `src/memoryos_lite/config.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `src/memoryos_lite/retrieval/archival_vector.py`
- `src/memoryos_lite/retrieval/providers/__init__.py`
- `src/memoryos_lite/retrieval/providers/qdrant_archival.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/v3_contracts.py`
- `tests/test_archival_searcher.py`
- `tests/test_archival_store.py`
- `tests/test_archival_vector.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`

This run additionally changed and committed:

- `src/memoryos_lite/config.py`
- `tests/test_context_composer.py`

## Verification Commands And Outcomes

Focused verification before the default correction:

- `uv run pytest tests/test_archival_vector.py -q` -> PASS, `4 passed in 0.04s`
- `uv run pytest tests/test_archival_searcher.py -q` -> PASS, `6 passed in 0.05s`
- `uv run pytest tests/test_archival_store.py -q` -> PASS, `5 passed in 9.07s`
- `uv run pytest tests/test_context_composer.py -q` -> PASS, `18 passed in 43.94s`
- `uv run pytest tests/test_engine.py -q` -> PASS, `40 passed in 83.83s`

TDD check for plan-default correction:

- `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q`
  - RED before code change: failed because `memoryos_archival_vector_enabled` was `False`
  - GREEN after code change: PASS, `1 passed in 0.03s`

Focused verification after the default correction:

- `uv run pytest tests/test_archival_vector.py -q` -> PASS, `4 passed in 0.07s`
- `uv run pytest tests/test_archival_searcher.py -q` -> PASS, `6 passed in 0.06s`
- `uv run pytest tests/test_archival_store.py -q` -> PASS, `5 passed in 12.85s`
- `uv run pytest tests/test_context_composer.py -q` -> PASS, `18 passed in 42.80s`
- `uv run pytest tests/test_engine.py -q` -> PASS, `40 passed in 86.20s`

Full verification:

- `uv run pytest -q` -> PASS, `611 passed, 1 warning in 1153.30s (0:19:13)`
- `uv run ruff check .` -> PASS, `All checks passed!`
- `uv run mypy src` -> FAIL, `Found 82 errors in 11 files (checked 58 source files)`
- `uv run memoryos eval run --case-set hard --baseline memoryos_lite` -> completed, diagnostic result `accuracy=0.56`, `source_hit=0.56`, `cases=16`, report `.memoryos/evals/run_20260524_141245.json`
- `MEMORYOS_ARCHIVAL_VECTOR_ENABLED=false uv run memoryos eval run --case-set hard --baseline memoryos_lite` -> completed, diagnostic result `accuracy=0.56`, `source_hit=0.56`, `cases=16`, report `.memoryos/evals/run_20260524_141310.json`

The second hard-eval run was diagnostic only. It showed the `0.56` score is not
explained by the archive-vector default change.

## Diagnostic Coverage Summary

- Vector selected: covered by archival searcher and composer vector-selection tests.
- Vector unavailable: covered by archival searcher and composer fallback tests.
- Lexical fallback: covered by searcher and composer fallback tests.
- Stale vector hit: covered by `test_archival_search_ignores_stale_vector_hits_missing_from_sqlite`.
- Scope excluded: covered by store/context composer scope-exclusion tests, including source-ref accounting.
- Eligible no match: covered by context composer archival eligibility diagnostics.
- Budget drop: covered by composer tests ensuring budget-dropped archival passages are not reported as selected.

## Invariants Checked

- Default memory architecture remains `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` fallback remains available and v1 build context excludes v3 archival diagnostics.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in; default kernel remains `off`.
- SQLite remains authoritative for archival source refs, scope eligibility, update/delete state, and final evidence rehydration.
- Qdrant payload is index metadata only and does not include final evidence text/source refs.
- Vector hits are scope-filtered by eligible passage ids and rehydrated from SQLite before rendering.
- Stale vector hits missing from SQLite are ignored and diagnosed.
- Focused tests use in-memory Qdrant and deterministic embeddings; no remote Qdrant, OpenAI key, or network is required.
- No benchmark improvement is claimed.

## Blockers

1. `uv run mypy src` fails with 82 errors in 11 files. The errors span
   archive-touched files and unrelated baseline modules.
2. The hard eval gate does not match the stated baseline. It reports
   `accuracy=0.56` and `source_hit=0.56` over 16 cases. Disabling archival
   vector mode gives the same result, so the low score is not isolated to the
   follow-up default correction.

## Known Limitations

- This run does not claim benchmark improvement.
- The feature should not advance to Master review until the mypy and hard-eval
  blockers are resolved or explicitly waived by Master.
- Public smoke diagnostics were not run because required full gates already
  failed.
