# phase: phase-4

# Spec: Archival Memory Store

## Goal

Add a source-backed archival memory store that is independent from legacy
`MemoryPage` / `MemoryItem` semantics and can shadow-write archival documents,
chunks, passages, memories, history, and archive attachments.

## Compatibility State

`shadow-write`

## Scope

This phase introduces durable archival contracts, SQLite persistence, and a
standalone passage-level search boundary. It does not route default v1/v2
context building through archival search.

## Functional Requirements

1. The archival model accounts for:
   - `ArchivalDocument`
   - `ArchivalChunk`
   - `ArchivalPassage`
   - `ArchivalMemory`
   - `ArchivalMemoryHistory`
   - `ArchiveAttachment`
   - optional `ArchivalEntityLink`

2. Explicit documents can enter an archive with source refs, tags, identity
   scope, created/updated metadata, and document-backed citation ranges.

3. Message, sleep, and retrieval consolidation jobs can create archival
   documents, passages, or archival memories through explicit store/service
   APIs.

4. Archival memory supports add, search, update, delete, and history.

5. Archive attachments bind archives to identity scopes such as user, agent,
   project, source, session, or run.

6. `ArchivalChunk` is an ingestion/chunking unit derived from an archival
   document. It is not the primary retrieval return type. Chunks carry document
   spans and chunking metadata; passages may point at chunks and remain the
   evidence unit returned by search.

7. `ArchivalPassage` and passage search results expose first-class metadata for:
   - `archive_id`
   - `document_id`
   - `chunk_id`
   - `source_id`
   - `file_id`
   - `identity_scope`
   - `tags`
   - `created_at`
   - `updated_at`
   - `source_refs`
   - `citation`

8. Passage-level retrieval supports:
   - `archive_id`
   - `source_id`
   - `file_id`
   - `tags`
   - date range
   - text search
   - vector mode as an explicit request mode with vector-ready metadata and a
     deterministic no-ANN fallback/diagnostic
   - hybrid mode as an explicit request mode that combines lexical score with
     vector diagnostics without requiring Qdrant

9. Search results are passage-level evidence and include score, reason, source
   refs, citation, scope, created/updated metadata, and owning document IDs.

10. Message, sleep, and retrieval consolidation producer APIs are represented
    explicitly, at minimum by a `producer` / `write_source` field and tests that
    create archival documents, passages, and memories from those sources.

## Non-Goals

- Do not change default v1/v2 recall or context behavior.
- Do not make `MemoryPage` / `MemoryItem` the new archival target model.
- Do not require Qdrant or embeddings for phase-4 acceptance.
- Do not implement phase-5 promotion policy, phase-6 composer, or benchmark
  reporting changes.

## Source-Backed Rule

Archival writes require source refs or approved manual provenance. Legacy
Page/Item conversion must preserve source message/page/item provenance as
source refs.

## Persistence Boundary

SQLite remains authoritative. File mirrors, if any, are debug-only. Alembic head
must advance after adding archival tables, and `MemoryStore.init_db()` must stamp
the current archival migration for fresh local stores.

## Acceptance Criteria

- All required archival entities are represented in contracts and persistence.
- Page/Item are treated only as migration input or adapter.
- Passage search returns passage-level evidence with first-class scope,
  source/file IDs, timestamps, metadata, and source refs.
- Text, vector, and hybrid query modes are accepted and diagnostic-tested.
- Archival memory add/search/update/delete/history is covered by tests.
- Message, sleep, and retrieval consolidation producers are covered by tests.
- Legacy tests remain green.
