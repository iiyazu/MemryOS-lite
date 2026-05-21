# phase: phase-4

# Brainstorm: Archival Memory Store

## Current Read

- `v3_contracts.py` already defines archival domain contracts:
  `ArchivalDocument`, `ArchivalPassage`, `ArchivalMemory`, `SourceRef`,
  `IdentityScope`, and `MemoryHistoryEvent`.
- `store.py` currently persists sessions, messages, episodes, pages, items,
  patches, traces, and core memory, but no archival tables yet.
- Retrieval code still centers on `MemoryPage` / `MemoryItem` / `Episode`.
- Phase-4 should therefore land the archival persistence and retrieval
  boundary, not the composer or kernel.

## Options

### Option A: contract-only

Add or refine the contracts and adapters only.

Tradeoff: low risk, but it does not satisfy shadow-write or evidence search.

### Option B: SQLite archival store with standalone passage search

Add archival tables, store methods, and a dedicated passage searcher. Keep
legacy Page/Item as migration inputs only.

Tradeoff: slightly more code, but it fits the phase-4 acceptance and keeps
default v1/v2 behavior isolated.

### Option C: full v3 routing

Wire archival retrieval into context building and benchmark flow now.

Tradeoff: too broad for phase-4 and would blur the boundary with phase-6/7.

## Recommendation

Use Option B.

## Design Scope

### Schema

Add durable tables for:

- `archival_documents`
- `archival_chunks`
- `archival_passages`
- `archival_memories`
- `archival_memory_history`
- `archive_attachments`
- optional `archival_entity_links`

Keep legacy `memory_pages` / `memory_items` as adapters or migration inputs.

### Store/API boundary

`MemoryStore` should expose explicit archival CRUD helpers, history writes,
attachment management, and passage search helpers. It should not route default
context building through archival retrieval in this phase.

### Retrieval

Add a dedicated archival passage searcher with lexical-first search and an
embedding/hybrid fallback. Filters should cover:

- `archive_id`
- `source_id`
- `file_id`
- `tags`
- date range
- text / vector / hybrid modes

Search results should be passage-level and carry score, reason, source refs,
citation, scope, and timestamps.

### Source-backed rule

Archival writes must require source refs or approved manual provenance. Legacy
Page/Item conversion must preserve source message ids as source refs.

## TDD Risks

1. Store schema drift: archival tables must not disturb current core-memory
   tables or alembic head handling.
2. Legacy regression: `v1` / `v2` context paths must remain untouched.
3. Search shape drift: passage hits, not document hits, must be the primary
   retrieval unit.
4. Provenance drift: source-less archival writes must fail fast.

## Phase-4 Acceptance Mapping

- Explicit docs can enter archive -> document create helper + tests.
- Message / sleep / consolidation outputs can produce archival objects ->
  adapters and store methods.
- Archival memory add/search/update/delete/history -> archive memory CRUD and
  history tests.
- Passage-level evidence with source refs, scope, created/updated metadata,
  score, citation -> search result model and search tests.
