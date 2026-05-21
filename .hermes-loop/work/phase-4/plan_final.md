# phase: phase-4

# Plan: Archival Memory Store

## TDD Order

1. Add contract tests for `ArchivalChunk`, `ArchiveAttachment`,
   `ArchivalMemoryHistory`, and optional entity links.
2. Add store tests for document, chunk, passage, attachment, archival memory,
   update, delete, and history round trips.
3. Add passage search tests for archive/source/file/tag/date/text filters,
   vector mode, hybrid mode, and passage-level result metadata.
4. Implement contracts in `v3_contracts.py`.
5. Implement SQLite models and `MemoryStore` archival methods.
6. Add Alembic migration for archival tables and update fresh-store stamping.
7. Implement a standalone archival passage searcher.
8. Run focused tests, then `uv run pytest -q`.

## Proposed Files

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `alembic/versions/0006_add_archival_memory.py`
- `tests/test_v3_contracts.py`
- `tests/test_archival_store.py`
- `tests/test_archival_searcher.py`

## Implementation Steps

### 1. Contracts

Extend v3 contracts with archival chunks, attachments, memory history aliases or
wrappers, entity links, search filters, and passage search result models.
Promote passage `scope`, `source_id`, `file_id`, `created_at`, and `updated_at`
to first-class fields instead of burying them in generic metadata.

### 2. Store schema

Add tables for archival documents, chunks, passages, memories, memory history,
archive attachments, and entity links. Store source refs, tags, metadata,
identity scope, citation, timestamps, producer/write-source, source IDs, file
IDs, and deletion state explicitly enough for filtering and acceptance tests.

### 3. Store API

Expose explicit methods for:

- create/list/get/update/delete archival documents
- create/list/search archival chunks and passages
- create/list/delete archive attachments
- add/search/update/delete archival memories
- append/list archival memory history
- create archival documents/passages/memories from message, sleep, and retrieval
  consolidation producers

All writes must validate source refs or approved manual provenance before
persistence.

### 4. Search

Implement lexical-first passage search over SQLite rows. Accept `text`,
`vector`, and `hybrid` modes explicitly. Without an ANN backend, vector mode
must return a deterministic diagnostic or vector-ready fallback rather than
silently behaving like plain text. Hybrid mode must expose how lexical and vector
signals were combined or why vector scoring was unavailable.

`ArchivalChunk` is an ingestion/chunking unit and may be referenced by passages;
search must return passages, not chunks or documents.

### 5. Legacy Boundary

Keep `MemoryPage` / `MemoryItem` conversion helpers as migration inputs only.
Do not wire archival search into `ContextBuilder`, `RecallPipeline`, CLI
benchmarks, or default API responses.

### 6. Verification

Run:

```bash
uv run pytest tests/test_v3_contracts.py tests/test_archival_store.py tests/test_archival_searcher.py -q
uv run pytest -q
```

## Review Checklist

- Required archival entities are present.
- Source-backed write enforcement is tested.
- Search returns passages, not whole documents.
- Filter support covers archive, source, file, tag, date, text, vector, and
  hybrid modes.
- Passage metadata includes first-class scope, source/file IDs, timestamps,
  citation, score, reason, and source refs.
- Message, sleep, and retrieval consolidation producer paths are tested.
- Default v1/v2 behavior is untouched.
