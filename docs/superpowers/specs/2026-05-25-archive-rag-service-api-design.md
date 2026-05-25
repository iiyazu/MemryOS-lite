# Archive RAG Service/API Integration Design

## Goal

Make the existing `MemoryOSArchiveRAG` library boundary usable through the
project's normal service, API, and CLI surfaces without creating a second RAG
system.

The first production-integration slice must support this real workflow:

```text
document content
  -> MemoryOSService.ingest_archive_document()
  -> SQLite archival document/chunk/passage records
  -> MemoryOSService.attach_archive()
  -> v3 ContextComposer archive eligibility
  -> selected archival context item with source refs, span, and quote
```

This is still MemoryOS Lite prototype work. The feature should not claim
production auth, tenancy, file-upload management, or production vector
lifecycle guarantees.

## Current Context

The branch already adds:

- `memoryos_lite.archive_rag.MemoryOSArchiveRAG`
- archival parser/splitter/indexer adapter protocols
- SQLite-backed `ArchivalDocument`, `ArchivalChunk`, and `ArchivalPassage`
  ingestion
- atomic archive ingest writes through `MemoryStore.create_archival_ingest_records`
- source-ref span and quote propagation for passage-level grounding
- archival text/vector/hybrid search with SQLite rehydration for vector hits
- optional archival Qdrant store separate from page Qdrant
- v3 composer archival layer consumption through archive eligibility

The missing production-integration piece is a formal service/API/CLI entry.
Callers currently need to instantiate `MemoryOSArchiveRAG` directly.

## Recommended Approach

Use a narrow Service/API integration slice.

`MemoryOSArchiveRAG` remains the low-level ingestion boundary. `MemoryOSService`
becomes the public orchestration boundary for application code. FastAPI and CLI
call `MemoryOSService` only; they do not directly manipulate store internals.

This keeps ownership aligned:

- SQLite remains authoritative for archive records.
- `MemoryOSArchiveRAG` owns parsing/splitting/write conversion.
- `MemoryStore` owns persistence and scope eligibility.
- `V3ContextComposer` owns context assembly.
- API/CLI are thin transport layers.

## Service Methods

Add four service-level methods.

### `ingest_archive_document`

Inputs:

- `document_id`
- `title`
- `content`
- `source_refs`
- one identity route:
  - `archive_id`, or
  - `source_id`, or
  - `file_id`
- optional `tags`
- optional `metadata`
- optional `producer`

Behavior:

- Construct `ArchiveRAGIngestRequest`.
- Call `MemoryOSArchiveRAG.ingest()`.
- Return document, chunk, passage IDs and diagnostics.
- Preserve source refs and passage-level span/quote.
- Do not require Qdrant.
- If optional vector/indexer work fails, keep SQLite records and expose
  diagnostics.

### `attach_archive`

Inputs:

- `archive_id`
- `scope_type`
- `scope_id`
- `source_refs`
- optional metadata

Behavior:

- Create an `ArchiveAttachment`.
- Return attachment metadata.
- First slice may allow attaching an archive before passages exist, but it must
  surface enough data for callers to diagnose empty archives.

### `list_archive_passages`

Inputs:

- optional `archive_id`
- optional `source_id`
- optional `file_id`

Behavior:

- Return SQLite-authoritative passages.
- Include source refs, citation, IDs, tags, and metadata.
- Used by API/CLI smoke checks after ingest.

### Existing `build_context`

Do not add a separate archive answer API. Callers should use the existing v3
context path. Archive RAG becomes visible when an attached archive passage is
selected into the archival layer.

## FastAPI Surface

Add minimal endpoints:

- `POST /archives/documents`
- `POST /archives/attachments`
- `GET /archives/passages`

These endpoints should be transport-only wrappers over `MemoryOSService`.

Response bodies should expose:

- document/chunk/passage IDs
- source refs
- citations
- diagnostics
- attachment scope

No endpoint should bypass v3 scope eligibility to perform answer generation.

## CLI Surface

Add minimal commands:

- `memoryos archive ingest`
- `memoryos archive attach`
- `memoryos archive passages`

The CLI is for local smoke and operational verification. It should not grow a
full document-management interface in this slice.

## Error Handling

Required source refs:

- Ingest without `source_refs` is rejected.
- Attach without `source_refs` is rejected.

Identity rules:

- `archive_id` passages do not also set `source_id` or `file_id`.
- non-archive passages require `source_id` or `file_id`.

Write consistency:

- parser/splitter validation failures happen before SQLite writes.
- document/chunk/passage writes are atomic.

Optional vector/indexer failures:

- do not roll back SQLite records.
- return diagnostics.
- never make Qdrant authoritative for text, source refs, or eligibility.

## Diagnostics

The integration should keep the existing diagnostics vocabulary:

- `archival_selected`
- `archival_eligible_no_match`
- `archival_scope_excluded`
- `archival_no_attached_archive`
- `archival_vector_unavailable`
- `archival_lexical_fallback`
- `archival_stale_vector_hit`
- `archival_scope_excluded_vector_hit`

API/CLI responses should include ingestion/indexer diagnostics and let the
context composer continue to emit retrieval diagnostics.

## Tests

Required tests for this slice:

- service end-to-end:
  - ingest document
  - attach archive to session
  - build context
  - selected archival item preserves source ref span and quote
- service file-only ingest:
  - `file_id`-only document writes passages and can be listed
- API smoke:
  - `POST /archives/documents`
  - `POST /archives/attachments`
  - `GET /archives/passages`
- CLI smoke:
  - ingest, attach, list passages through service
- no-Qdrant fallback:
  - context selection works through lexical fallback
  - vector diagnostics are preserved
- existing protection:
  - v1 fallback does not emit v3 archive diagnostics
  - hard eval remains `1.00/1.00`

Full pytest remains a final merge gate, but the implementation plan may use
focused tests during development.

## Explicit Non-Goals

This slice does not implement:

- delete
- reindex
- versioning
- multipart file upload
- auth
- rate limiting
- multi-tenant ownership
- UI
- answer generation API
- production Qdrant cleanup or stale delete lifecycle

## Acceptance Criteria

The slice is ready for merge review when:

- `MemoryOSService` is the normal application entry for archive document ingest.
- FastAPI and CLI expose the minimal archive workflow.
- The workflow `ingest -> attach -> build_context` is covered by tests.
- Source refs, citation span, and quote survive from ingest into selected v3
  context items.
- Qdrant remains optional and SQLite remains authoritative.
- Focused archive/context/API/CLI tests pass.
- hard eval remains `1.00/1.00`.
