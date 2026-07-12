# Archive RAG Boundary

MemoryOS owns archive memory semantics. External parser, splitter, embedder,
vector-index, and reranker components may be plugged in, but they do not become
the source of truth for archive text, source refs, scope eligibility, updates,
or deletes.

## Ingestion Boundary

`memoryos_lite.archive_rag.MemoryOSArchiveRAG` accepts three adapter types:

- `ArchiveDocumentParser`: converts request content into text plus parser
  metadata.
- `ArchiveTextSplitter`: returns exact text spans over the parsed document.
- `ArchivePassageIndexer`: indexes MemoryOS-owned `ArchivalPassage` objects
  after SQLite writes.

The service validates source refs and splitter spans before writing. It then
creates `ArchivalDocument`, `ArchivalChunk`, and `ArchivalPassage` records in
SQLite. The optional indexer receives the stored passage objects; it does not
decide passage IDs, source refs, or scope.

Default adapters are intentionally small:

- `PlainTextArchiveParser` decodes text or UTF-8 bytes.
- `FixedWindowArchiveSplitter` creates deterministic text spans.

## Retrieval Boundary

`ArchivalPassageSearcher` still searches only passages supplied by MemoryOS
scope eligibility. Optional vector search rehydrates vector hits from SQLite
before returning them. Optional rerankers may reorder existing MemoryOS hits,
but injected external hit IDs are dropped and recorded with
`archival_reranker_dropped_external_hit`.

## Vector Boundary

`ArchivalVectorIndex.index_passages()` exposes explicit indexing for archival
passages. Qdrant stores passage IDs and lookup metadata only. SQLite remains
authoritative for text, source refs, and eligibility.

## Service/API Boundary

`MemoryOSService` is the application entry point for archive RAG ingestion.
FastAPI and CLI commands call service methods instead of manipulating the store
directly.

Minimal service-backed surfaces:

- `POST /archives/ingest`
- `POST /archives/attachments`
- `GET /archives/passages`
- `memoryos archive ingest`
- `memoryos archive attach`
- `memoryos archive passages`

These surfaces do not bypass v3 archive eligibility. Retrieved archive passages
enter normal context through `build_context()`.

`GET /archives/passages` uses the current SQLite store listing path and applies
pagination in memory. This is O(n) for the first service/API slice; SQL-level
pagination is a later scale-up task, not part of this prototype integration.

## Non-Claims

This feature does not change default v3 routing, v1 fallback, kernel opt-in
behavior, or benchmark scores. Public benchmark movement must be evaluated by a
separate held-out or milestone process.
