# feature_id: archive-rag

## Boundary

- Feature: `archive-rag` (`Archive RAG Boundary`)
- Branch: `feat/archive-rag`
- Worktree: `/home/iiyatu/projects/python/memoryOS-archive-rag`
- Target branch: `feat/phase-2.5-3-retrieval-agent`
- Feature-local artifacts: `/home/iiyatu/projects/python/memoryOS/xmuse/work/features/archive-rag/`
- Allowed writes: code/tests/docs in the assigned worktree, plus feature-local artifacts only.
- Forbidden writes: Master state/status, Master review artifacts, approval artifacts, target branch, other worktrees.

## Inputs Read

- `xmuse/prompts/slave_god_prompt.md`
- `xmuse/contracts/slave_dispatch_template.json`
- `xmuse/work/features/archive-rag/slave_state.json`
- `xmuse/work/features/archive-rag/blueprint.md`
- Dispatch registry entry in the user prompt.

## Worktree State

- Worktree root: `/home/iiyatu/projects/python/memoryOS-archive-rag`
- Current branch: `feat/archive-rag`
- Starting head: `d1d36d55bd2564f177f946f1ec5da209b448dd22`
- Worktree is a linked git worktree (`.git/worktrees/memoryOS-archive-rag`).
- Initial status for this run is not clean: `tests/test_context_composer.py` has pre-existing RED diagnostic tests. These are preserved and incorporated.

## Live Architecture Observed

- `Settings.memoryos_memory_arch` defaults to `v3`.
- `Settings.memoryos_agent_kernel` defaults to `off`; `v1` remains opt-in.
- `Settings.memoryos_recall_pipeline` defaults to `v1`; v2 remains opt-in.
- `MemoryOSService.build_context()` routes through `V3ContextComposer` only when `resolved_memory_arch == "v3"`.
- v1 fallback does not include v3 diagnostics or archival eligibility metadata.
- SQLite store is authoritative for archival documents, chunks, passages, memories, attachments, history, scope eligibility, and final context evidence.

## Relevant Existing Code

- `src/memoryos_lite/v3_contracts.py`
  - Defines `ArchivalDocument`, `ArchivalChunk`, `ArchivalPassage`, `ArchivalMemory`, `ArchiveAttachment`, `ArchiveEligibilityScope`, and `ArchiveEligibilityResult`.
  - `ArchiveEligibilityResult` already includes source-backed `scope_excluded_passages`.
- `src/memoryos_lite/store.py`
  - Stores archival passage state in SQLite.
  - Requires source refs for archival writes.
  - Resolves eligible archives from session/user/agent/run/project/source attachments before retrieval.
  - Deletes/upserts memory-derived archival passages on memory delete/update.
- `src/memoryos_lite/retrieval/archival_searcher.py`
  - Currently BM25 lexical with vector/hybrid placeholder fallbacks.
  - Emits passage-level hits with source refs and metadata.
- `src/memoryos_lite/context_composer.py`
  - Uses SQLite scope eligibility before `ArchivalPassageSearcher`.
  - Renders only `ArchivalPassage` items in the archival layer.
  - Emits selected, eligible-no-match, scope-excluded, no-attached-archive, and budget diagnostics.
- `src/memoryos_lite/retrieval/providers/qdrant.py`
  - Existing page-vector provider; must stay page-specific and not be reused with page payload semantics for archive passages.

## Implementation Gap

The missing feature is the actual passage-centered archival vector boundary:

- No archival-specific Qdrant provider exists.
- No archival vector orchestration indexes `ArchivalPassage` points.
- `ArchivalPassageSearcher` does not perform Qdrant search or SQLite rehydration.
- `V3ContextComposer` cannot emit vector-unavailable, lexical-fallback, stale-vector-hit, or vector-source diagnostics beyond text search metadata.
- `MemoryOSService` does not wire archival Qdrant/index configuration.

## Design Decisions

- Add an archival-specific Qdrant provider with a separate deterministic UUID namespace, collection name, and payload namespace.
- Add a small archival vector orchestration layer that:
  - embeds and upserts eligible `ArchivalPassage` records;
  - queries Qdrant with an eligible-passage-id filter and embedding config hash;
  - returns only passage ids and scores from Qdrant;
  - leaves final evidence rehydration to SQLite.
- Extend `ArchivalPassageSearcher` with optional vector dependencies while preserving direct lexical behavior.
- Keep vector-primary behavior behind `Settings.memoryos_archival_vector_enabled` and use lexical fallback whenever vector dependencies are absent or fail.
- Use query-time upsert for eligible passages in this prototype lane so direct store-created passages are searchable without a new ingestion API.
- Record stale Qdrant hits and vector fallback diagnostics, but never render payload text or source refs from Qdrant.

## Tests To Add

- `tests/test_archival_vector.py`
  - archival Qdrant payload namespace/config/passage id isolation;
  - eligible-id filtering;
  - dimension/config validation behavior.
- `tests/test_archival_searcher.py`
  - vector-primary search returns semantic passage even when lexical text would prefer another passage;
  - Qdrant/embedding failure falls back to lexical and records diagnostics;
  - stale Qdrant ids are ignored and diagnosed after SQLite rehydration.
- `tests/test_archival_store.py`
  - batch archival passage lookup by id rehydrates SQLite records and omits missing ids.
- `tests/test_context_composer.py`
  - composer includes vector-selected metadata/source refs and fallback diagnostics;
  - unattached passage is not selected even if vector store returns it;
  - existing pre-run scope-exclusion source-ref tests are preserved.
- `tests/test_engine.py`
  - service wires archival Qdrant separately from page Qdrant and v1 fallback remains free of archival vector diagnostics.

## Non-Goals

- No production-ready MemoryOS claim.
- No Letta dependency.
- No new public ingestion API/CLI.
- No remote Qdrant, OpenAI key, or network requirement for tests.
- No benchmark improvement claim.
- No merge or approval artifact writes.
