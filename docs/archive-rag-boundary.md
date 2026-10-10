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
passages. The vector store keeps passage IDs and lookup metadata only. SQLite remains
authoritative for text, source refs, and eligibility.

## Service/API Boundary

`MemoryOSService` is the application entry point for archive RAG ingestion:
`ingest_archive_document()` and `attach_archive()`. Since 0.5.0 they have no
HTTP route; the evaluation harness calls them in process.

These methods do not bypass v3 archive eligibility. Retrieved archive passages
enter normal context through `build_context()`.

## Non-Claims

This feature does not change v3 routing, external advisory behavior, or
benchmark scores. Public benchmark movement must be evaluated by a
separate held-out or milestone process.
