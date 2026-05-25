# Archive RAG Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a passage-centered archival Qdrant RAG boundary where SQLite remains authoritative and v3 composer diagnostics explain vector, fallback, scope, stale-hit, and budget behavior.

**Architecture:** Add an archival-specific Qdrant provider and vector orchestration layer, inject it into `ArchivalPassageSearcher`, and keep `V3ContextComposer` responsible for scope-first retrieval and diagnostics. Qdrant stores only vectors plus lookup metadata; every vector hit is filtered by eligible passage ids and rehydrated from SQLite before rendering.

**Tech Stack:** Python 3.11+, Pydantic, SQLAlchemy SQLite store, qdrant-client in-memory mode, deterministic test embeddings, pytest, ruff, mypy.

---

## Files

- Create: `src/memoryos_lite/retrieval/archival_vector.py`
  - `ArchivalEmbeddingConfig`, vector hit/diagnostic dataclasses, and `ArchivalVectorIndex`.
- Create: `src/memoryos_lite/retrieval/providers/qdrant_archival.py`
  - Archival-passage-only Qdrant provider with separate collection/payload namespace.
- Create: `tests/test_archival_vector.py`
  - In-memory Qdrant provider and vector index tests.
- Modify: `src/memoryos_lite/config.py`
  - Add archival vector settings without changing memory arch, recall pipeline, or kernel defaults.
- Modify: `src/memoryos_lite/store.py`
  - Add batch archival passage lookup by id for SQLite rehydration.
- Modify: `src/memoryos_lite/retrieval/archival_searcher.py`
  - Add optional vector-primary path with lexical fallback and diagnostics.
- Modify: `src/memoryos_lite/context_composer.py`
  - Use archival vector mode by default when enabled and convert search diagnostics into v3 diagnostics/accounting.
- Modify: `src/memoryos_lite/engine.py`
  - Wire archival Qdrant/index/searcher separately from page Qdrant.
- Modify: `src/memoryos_lite/retrieval/providers/__init__.py`
  - Export/import archival Qdrant provider with optional dependency handling.
- Modify: focused tests in `tests/test_archival_searcher.py`, `tests/test_archival_store.py`, `tests/test_context_composer.py`, and `tests/test_engine.py`.

## Tasks

### Task 1: RED tests for store rehydration and archival Qdrant isolation

- [ ] Add `test_archival_store_batch_lookup_rehydrates_passages_by_id` in `tests/test_archival_store.py`.
- [ ] Create `tests/test_archival_vector.py` with tests for archival payload namespace, eligible-id filtering, config hash payload, and dimension mismatch.
- [ ] Run:
  - `uv run pytest tests/test_archival_store.py::test_archival_store_batch_lookup_rehydrates_passages_by_id tests/test_archival_vector.py -q`
  - Expected RED: import or attribute failures because the new provider/vector index and store helper do not exist.

### Task 2: GREEN store helper and archival vector provider

- [ ] Add `MemoryStore.get_archival_passages_by_ids(passage_ids: list[str]) -> dict[str, ArchivalPassage]`.
- [ ] Implement `QdrantArchivalPassageStore` with:
  - collection default separate from pages;
  - deterministic UUID5 point ids derived from passage ids;
  - payload key `namespace == "memoryos_archival_passage"`;
  - payload keys for `passage_id`, archive/source/file ids, tags, updated timestamp, and embedding config hash;
  - eligible-id filtering in `query()`;
  - dimension validation on upsert/query.
- [ ] Run the Task 1 command and confirm GREEN.

### Task 3: RED tests for vector-primary search and fallback diagnostics

- [ ] Add tests in `tests/test_archival_searcher.py` proving:
  - vector-primary search can select the semantically indexed passage;
  - embedding/Qdrant failure falls back to lexical;
  - stale Qdrant hit ids are ignored and diagnosed after SQLite rehydration.
- [ ] Run:
  - `uv run pytest tests/test_archival_searcher.py -q`
  - Expected RED before searcher changes: vector path remains placeholder-only and cannot rehydrate/diagnose stale hits.

### Task 4: GREEN archival vector orchestration and searcher

- [ ] Implement `ArchivalEmbeddingConfig` and `ArchivalVectorIndex`.
- [ ] Extend `ArchivalPassageSearcher` to accept optional `vector_index` and `passage_loader`.
- [ ] Keep `mode="text"` behavior stable for existing callers.
- [ ] For vector mode:
  - filter candidates after SQLite eligibility;
  - upsert eligible passage vectors;
  - embed query and query Qdrant with eligible ids;
  - batch rehydrate hit ids from SQLite;
  - ignore stale/missing hits and record diagnostics;
  - fall back to lexical if vector dependencies fail or return no usable hits.
- [ ] Run `uv run pytest tests/test_archival_searcher.py tests/test_archival_vector.py -q`.

### Task 5: RED tests for v3 composer and engine wiring

- [ ] Add composer tests proving:
  - vector-selected archival item includes source refs and vector metadata;
  - vector-unavailable/lexical-fallback diagnostics enter component accounting;
  - unattached vector hits cannot be selected.
- [ ] Add engine tests proving:
  - archival Qdrant collection is distinct from page Qdrant collection;
  - v1 fallback exposes no archival vector diagnostics.
- [ ] Run:
  - `uv run pytest tests/test_context_composer.py::test_v3_composer_uses_archival_vector_search_with_source_refs tests/test_context_composer.py::test_v3_composer_records_archival_vector_fallback_diagnostics tests/test_engine.py::test_service_wires_archival_qdrant_separately_from_page_qdrant -q`
  - Expected RED before composer/engine wiring: settings/providers/searcher wiring are missing.

### Task 6: GREEN composer and engine wiring

- [ ] Add archival vector settings:
  - `memoryos_archival_vector_enabled: bool = True`
  - `memoryos_archival_qdrant_url: str | None = None`
  - `memoryos_archival_qdrant_collection: str = "memoryos_archival_passages"`
- [ ] Pass vector-capable `ArchivalPassageSearcher` into `V3ContextComposer` from `MemoryOSService`.
- [ ] Use vector mode in `_archival_items()` only when archival vector is enabled; otherwise keep text mode.
- [ ] Convert search diagnostics into `DiagnosticEvent` entries without marking budget-dropped passages selected.
- [ ] Run the Task 5 command and focused composer/engine tests.

### Task 7: Focused verification

- [ ] Run:
  - `uv run pytest tests/test_archival_vector.py -q`
  - `uv run pytest tests/test_archival_searcher.py -q`
  - `uv run pytest tests/test_archival_store.py -q`
  - `uv run pytest tests/test_context_composer.py -q`
  - `uv run pytest tests/test_engine.py -q`
- [ ] Confirm v3 default, v1 fallback, v2 opt-in, kernel opt-in, SQLite authority, source refs, scope gate, stale-hit handling, lexical fallback, and budget diagnostics remain covered.

### Task 8: Full verification and review artifacts

- [ ] Run:
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `uv run mypy src`
  - `uv run memoryos eval run --case-set hard --baseline memoryos_lite`
- [ ] Treat benchmark output as diagnostic only.
- [ ] Write `result.md`, `execute_review.md`, `review_verdict.json`, `ack.json`, and update `slave_state.json`.
- [ ] Commit focused feature changes and artifact updates if verification passes and the worktree can be made clean.
