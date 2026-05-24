# archive-rag execute review

feature_id: `archive-rag`
reviewer: `Hermes Slave God`
final head: `ace77bdf7fa7f8f3ac596e93b12c07e45bd61b02`
verdict: `FAIL`

## Scope Review

Allowed writes were respected:

- Code/tests changed only inside `/home/iiyatu/projects/python/memoryOS-archive-rag`.
- Slave artifacts written only under `/home/iiyatu/projects/python/memoryOS/xmuse/work/features/archive-rag/`.
- No Master state/status, Master review, integrated-test, approval, target branch, merge, or other worktree writes were performed.

## Implementation Review

Passage-centered archive RAG boundary is present:

- `ArchivalPassage` is the vector and final archival context unit.
- `QdrantArchivalPassageStore` uses an archive-specific collection and payload namespace.
- Qdrant payload carries lookup/index metadata and excludes final text/source refs.
- `ArchivalVectorIndex` embeds/upserts eligible passages and queries Qdrant with eligible passage ids.
- `ArchivalPassageSearcher` performs vector-primary retrieval, SQLite batch rehydration, stale-hit filtering, and lexical fallback diagnostics.
- `V3ContextComposer` resolves SQLite scope before retrieval and renders source-backed archival context items.
- `MemoryOSService` wires archival Qdrant separately from page Qdrant.

## Invariant Review

PASS:

- Default memory architecture remains `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` fallback remains available.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in; default is still `off`.
- SQLite remains authoritative for final archival evidence.
- Qdrant is index-only for archival passages.
- Vector hits are eligible-id filtered and SQLite rehydrated.
- Stale vector hits cannot enter final context in focused tests.
- Tests use in-memory Qdrant/deterministic embeddings.
- No benchmark improvement claim was made.

FAIL:

- Full `mypy` gate fails.
- Hard eval gate reports `0.56/0.56`, below the stated baseline.

## Verification Evidence

PASS:

- `uv run pytest tests/test_archival_vector.py -q` -> `4 passed`
- `uv run pytest tests/test_archival_searcher.py -q` -> `6 passed`
- `uv run pytest tests/test_archival_store.py -q` -> `5 passed`
- `uv run pytest tests/test_context_composer.py -q` -> `18 passed`
- `uv run pytest tests/test_engine.py -q` -> `40 passed`
- `uv run pytest -q` -> `611 passed, 1 warning`
- `uv run ruff check .` -> `All checks passed!`

FAIL:

- `uv run mypy src` -> `82 errors in 11 files`
- `uv run memoryos eval run --case-set hard --baseline memoryos_lite` -> `accuracy=0.56`, `source_hit=0.56`

## Review Decision

Do not advance this feature to Master review as usable. The implementation may
be functionally covered by focused tests, but required full verification is not
clean.
