# feature: archive-rag

## Goal / User-Visible Value

Deliver a Letta-inspired, Passage-centered, development-lane Qdrant-enabled
archival vector RAG boundary for MemoryOS Lite.

`ArchivalPassage` is the only unit that enters the archival vector index and the
only archival retrieval unit rendered into final context. SQLite remains
authoritative for source refs, scope eligibility, history, update/delete state,
and final evidence rehydration. Qdrant is an ANN/vector index for archival
passages, not an authoritative memory store.

The user-visible value is that v3 context building can retrieve source-backed,
scope-safe archival passages semantically, while still explaining selection,
fallback, stale-hit, and budget behavior through diagnostics.

## Current Context

Live code already contains:

- SQLite archival tables and models for documents, chunks, passages, memories,
  memory history, and archive attachments.
- `ArchiveEligibilityScope` and `list_archival_passages_for_scope(...)`.
- `ArchivalPassageSearcher` with lexical BM25 and placeholder vector/hybrid
  modes.
- v3 composer archival diagnostics for selected, eligible-no-match,
  scope-excluded, and no-attached-archive states.
- Page-level embedding and Qdrant support for `MemoryPage`, which must not be
  reused in a way that mixes page and archival passage namespaces.

Docs conflict note: some repository docs still mention older Alembic heads
(`0004` or `0006`). Live code and tests use `0008_add_promotion_candidates`.
Blueprint execution must follow live code and `xmuse/master_state.json`
when docs disagree.

## Non-Goals

- Do not describe MemoryOS Lite as production-ready MemoryOS.
- Do not introduce Letta as a dependency.
- Do not implement a complete document ingestion API/CLI in this feature.
- Do not make Qdrant, Redis, A2A, AutoGen, or any external RAG framework an
  authoritative dependency for MemoryOS memory semantics.
- Do not require remote Qdrant service, Qdrant API key, OpenAI API key, or
  external network access for tests.
- Do not change `MEMORYOS_MEMORY_ARCH=v1` fallback behavior.
- Do not change `MEMORYOS_RECALL_PIPELINE=v2` opt-in behavior.
- Do not change `MEMORYOS_AGENT_KERNEL=v1` opt-in behavior.
- Do not claim benchmark improvement from aggregate results alone.
- Do not merge. Merge remains Master-controlled after review, integrated tests,
  explicit merge approval, and post-merge verification.

## Allowed Files / Modules

Primary implementation scope:

- `src/memoryos_lite/v3_contracts.py`
  - Add archival vector diagnostics and embedding/index config contracts only
    if needed.
- `src/memoryos_lite/config.py`
  - Add archival-specific development defaults/configuration if needed, such as
    archival vector enablement, archival Qdrant URL, and archival Qdrant
    collection.
  - Do not reuse the page Qdrant collection in a way that causes namespace or
    payload confusion.
- `src/memoryos_lite/store.py`
  - Add passage-id batch lookup and narrowly scoped update/delete/reindex helper
    methods if needed.
  - Preserve SQLite as authoritative store.
- `src/memoryos_lite/retrieval/archival_searcher.py`
  - Extend from lexical-only/placeholder vector to vector-primary plus lexical
    fallback behavior.
- `src/memoryos_lite/retrieval/archival_vector.py`
  - New passage-centered vector orchestration module.
- `src/memoryos_lite/retrieval/providers/qdrant_archival.py`
  - Preferred new archival-specific Qdrant provider.
  - If the existing Qdrant provider is reused instead, collection names, point
    ids, and payload keys must be explicitly isolated for archival passages.
- `src/memoryos_lite/context_composer.py`
  - Only adjust `_archival_items()` and related diagnostics/accounting.
- `src/memoryos_lite/engine.py`
  - Only wire embedding client and archival Qdrant index if required.

Tests:

- `tests/test_archival_vector.py`
- `tests/test_archival_searcher.py`
- `tests/test_archival_store.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`

Documentation/artifacts:

- `xmuse/work/features/archive-rag/blueprint.md`
- `xmuse/work/features/archive-rag/ack.json`
- `xmuse/work/features/archive-rag/result.md`
- `xmuse/work/features/archive-rag/review_verdict.json`
- Optional current-doc corrections only when needed to remove stale facts touched
  by this feature.

Out of scope unless Master explicitly amends the blueprint:

- Public API or CLI ingestion surface.
- Full benchmark harness rewrites.
- New persistent service requirements.
- Changes to unrelated page/item/episode retrieval semantics.
- Broad refactors of the v3 composer.

## Behavioral Invariants

- Development-lane archival vector retrieval is Qdrant-enabled by default for
  this feature, but that default is limited to the `archive-rag` lane and does
  not make Qdrant authoritative for MemoryOS Lite.
- SQLite scope eligibility must run before Qdrant search.
- Qdrant queries must be restricted to eligible archival passage ids or an
  equivalent eligible-id filter.
- Qdrant payload may contain lookup/index metadata only, such as `passage_id`,
  collection namespace, archive/source/file identifiers, tags, index version,
  and embedding config hash.
- Qdrant payload must never be used as final evidence.
- Every Qdrant hit must be batch rehydrated from SQLite before rendering.
- A Qdrant hit missing from SQLite is a stale hit. It must be ignored and
  recorded in diagnostics.
- Every final archival context item must carry `SourceRef`.
- Archival update, delete, and reindex flows must prevent stale vector evidence
  from entering final context.
- If Qdrant or embedding generation fails, archival retrieval must fall back to
  lexical retrieval and record explicit diagnostics.
- Budget-dropped archival passages must not be reported as selected.
- v1 fallback, v2 recall opt-in, and agent kernel opt-in defaults must remain
  unchanged.

## Expected Architecture

The implementation should follow a Passage-centered archival memory design:

1. `ArchivalDocument` and `ArchivalChunk` remain source/chunking/provenance
   structures.
2. `ArchivalPassage` is the only archival vector index unit and final archival
   context unit.
3. `ArchivalMemory` continues to project into `ArchivalPassage` through the
   existing archival memory passage projection path.
4. `ArchiveAttachment` and `ArchiveEligibilityScope` are the MemoryOS scope gate
   and run before vector search.
5. Qdrant stores archival passage vectors in an archival-specific collection,
   using deterministic point ids derived from passage ids.
6. Query flow:
   - resolve eligible passages in SQLite;
   - embed the query;
   - query Qdrant with eligible passage id filtering;
   - rehydrate hits from SQLite;
   - render source-backed archival context items;
   - emit diagnostics and accounting.
7. Fallback flow:
   - if embedding/Qdrant is unavailable or fails, use lexical retrieval;
   - record vector-unavailable and lexical-fallback diagnostics.

Embedding/index config should be explicit enough to avoid silent mixed-model or
mixed-dimension searches. This can be represented as a contract, passage
metadata, Qdrant payload metadata, or another narrow mechanism chosen by the
implementer. A model/dimension/config mismatch must not silently produce
selected final evidence.

## Phased Execution Plan

This feature must be executed in original loop style: each phase delivers a
bounded layer, records evidence, and gates the next phase. Do not use historical
`xmuse/history/`, `xmuse/legacy/root-loop/`, or deleted phase
directories as active planning input. They are audit background only.

### Phase 0: Baseline And Gate Diagnosis

Goal: establish the target-branch baseline before attributing failures to
`archive-rag`.

Allowed work:

- Inspect live code, blueprint, `context_bundle.md`, and `plan_final.md`.
- Run target/feature comparison diagnostics when needed.
- Classify `mypy` and hard-eval failures as feature-introduced, baseline, or
  environment/config related.

Required evidence:

- Current feature worktree head and target branch head.
- `git status --short` for both main and feature worktrees.
- Fresh results or explicit reuse rationale for:
  - `uv run mypy src`
  - `uv run memoryos eval run --case-set hard --baseline memoryos_lite`

Exit gate:

- A written baseline classification exists in `result.md`.
- If baseline gates are already red on target, do not claim archive-rag caused
  them without case-level or error-level evidence.

### Phase 1: Contracts And Configuration

Goal: define the archival vector boundary without changing default memory
architecture, v1 fallback, v2 recall opt-in, or agent kernel opt-in.

Allowed work:

- Add archival vector settings in `config.py`.
- Add narrow archival vector diagnostics or embedding/index config contracts in
  `v3_contracts.py` if needed.
- Add tests proving the development-lane archival vector default and preserved
  v1/v2/kernel boundaries.

Exit gate:

- Config tests pass.
- No page Qdrant collection or payload namespace is reused for archival
  passages.

### Phase 2: Passage Index Provider

Goal: create the Qdrant-backed archival passage vector index as an index-only
component.

Allowed work:

- Add `retrieval/providers/qdrant_archival.py`.
- Add `retrieval/archival_vector.py`.
- Use deterministic point ids derived from `passage_id`.
- Store only lookup/index metadata in Qdrant payload.
- Support in-memory Qdrant and deterministic embeddings for tests.

Exit gate:

- `uv run pytest tests/test_archival_vector.py -q` passes.
- Tests prove eligible-id filtering, payload namespace isolation, config/hash
  metadata, dimension/config validation, and no final evidence in Qdrant
  payload.

### Phase 3: SQLite Rehydration And Lifecycle Safety

Goal: ensure SQLite remains authoritative for final archival evidence and stale
vector hits cannot render.

Allowed work:

- Add batch archival passage lookup by id.
- Add narrowly scoped update/delete/reindex helpers only if required.
- Preserve existing source-ref validation and archival memory history behavior.

Exit gate:

- `uv run pytest tests/test_archival_store.py -q` passes.
- Tests prove batch rehydration omits missing ids, update/delete/reindex cannot
  leave stale vector evidence selectable, and source refs remain required.

### Phase 4: Vector-Primary Search With Lexical Fallback

Goal: make `ArchivalPassageSearcher` perform real vector retrieval while
preserving lexical behavior and fallback diagnostics.

Allowed work:

- Extend `archival_searcher.py` with optional vector dependencies.
- Keep `mode="text"` behavior stable.
- For vector mode, search only eligible candidates, rehydrate hits from SQLite,
  ignore stale hits, and fall back to lexical when embedding/Qdrant fails.

Exit gate:

- `uv run pytest tests/test_archival_searcher.py -q` passes.
- Tests prove vector-primary selection, lexical fallback, vector-unavailable
  diagnostics, stale-hit diagnostics, and source refs on returned hits.

### Phase 5: V3 Composer And Engine Wiring

Goal: wire archival vector retrieval into the v3 composer without changing
unrelated memory paths.

Allowed work:

- Adjust only `_archival_items()` and diagnostics/accounting in
  `context_composer.py`.
- Wire embedding client and archival Qdrant index in `engine.py` only as needed.
- Ensure SQLite scope eligibility happens before vector search.

Exit gate:

- `uv run pytest tests/test_context_composer.py -q` passes.
- `uv run pytest tests/test_engine.py -q` passes.
- Tests prove source-backed final archival context, scope-before-vector,
  unattached passage exclusion, stale-hit exclusion, budget behavior, and v1
  fallback isolation.

### Phase 6: Integrated Verification And Handoff

Goal: produce a bounded Slave handoff for Master without merging.

Required verification:

```bash
uv run pytest tests/test_archival_vector.py -q
uv run pytest tests/test_archival_searcher.py -q
uv run pytest tests/test_archival_store.py -q
uv run pytest tests/test_context_composer.py -q
uv run pytest tests/test_engine.py -q
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Exit gate:

- `result.md` includes a phase-by-phase completion matrix.
- `ack.json` records `usable`, `blocked`, or `failed` with concrete blockers.
- `review_verdict.json` records PASS/FAIL and whether the feature may advance
  to Master review.
- No merge, Master-owned artifact, approval artifact, or target-branch write is
  performed by the Slave.

## Required Tests / Evals

Focused tests are required before broad evals:

```bash
uv run pytest tests/test_archival_vector.py -q
uv run pytest tests/test_archival_searcher.py -q
uv run pytest tests/test_archival_store.py -q
uv run pytest tests/test_context_composer.py -q
uv run pytest tests/test_engine.py -q
```

Required coverage:

- In-memory Qdrant path works with `QdrantClient(":memory:")` or equivalent
  local mode.
- Tests use fake/deterministic embeddings or equivalent local deterministic
  embedding; no remote Qdrant service or OpenAI key is required.
- Archival Qdrant points use archival passage ids and archival-specific payload
  namespace/metadata.
- Vector search is primary when archival Qdrant and embedding client are
  healthy.
- Lexical fallback is used when embedding or Qdrant is unavailable or fails.
- Fallback diagnostics explicitly identify vector unavailability and lexical
  fallback.
- SQLite scope eligibility happens before vector search.
- An unattached passage cannot be selected even if it is the best semantic
  match.
- Qdrant hits are batch rehydrated from SQLite.
- Stale Qdrant hits missing from SQLite are ignored and diagnosed.
- Update/delete/reindex prevents old vector evidence from entering final
  context.
- Every rendered archival context item includes source refs.
- Budget diagnostics do not mark budget-dropped archival passages as selected.
- v1 fallback does not expose archival vector diagnostics or archival vector
  context.

Full verification before Master approval:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Optional public smoke diagnostics may be run, but no improvement claim is
allowed without case-level fail/pass movement or explicit diagnostic movement:

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge

MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

## Completion Criteria

- `archive-rag` implements a Passage-centered archival vector path with Qdrant
  enabled by default in the development lane.
- SQLite remains authoritative for archival memory state, source refs, history,
  scope eligibility, update/delete status, and final evidence rehydration.
- Qdrant is used only as an archival passage vector index.
- Vector hits are filtered by SQLite eligibility before selection and rehydrated
  from SQLite before rendering.
- Stale vector hits cannot enter final context.
- Qdrant/embedding failure falls back to lexical retrieval with diagnostics.
- Required focused tests and full verification commands pass.
- Result artifact records changed files, exact verification commands, outcomes,
  known limitations, and any case-level diagnostic movement.
- No production-ready claim, unsupported benchmark claim, forbidden dependency,
  default-boundary change, or merge is made.

## Review Failure Criteria

Master review must fail if:

- Qdrant is treated as final evidence or an authoritative memory store.
- Archival vector hits are queried or rendered without prior SQLite scope
  eligibility.
- Qdrant hits are rendered without SQLite rehydration.
- A stale Qdrant hit can enter final context.
- Update/delete leaves old vector evidence selectable.
- Tests require remote Qdrant, OpenAI API key, or network access.
- Page and archival Qdrant collections/payload namespaces are mixed.
- Final archival context items lack source refs.
- v1 fallback, v2 recall opt-in, or agent kernel opt-in defaults change without
  explicit Master-approved gate.
- Aggregate benchmark results are used to claim improvement without case-level
  movement or explicit diagnostics.
- Slave attempts to merge.

## Handoff Artifacts

Slave must produce:

- `xmuse/work/features/archive-rag/ack.json`
- `xmuse/work/features/archive-rag/result.md`
- `xmuse/work/features/archive-rag/review_verdict.json`
- changed-file summary
- exact verification command log and outcomes
- phase-by-phase completion matrix with evidence for each exit gate
- diagnostic summary for vector selected, vector unavailable, lexical fallback,
  stale vector hit, scope excluded, eligible no match, and budget drop cases
- explicit statement that no merge was performed

## Runner Type

`local_codex`

## Master Gates

Master review gate:

- inspect implementation against this blueprint;
- confirm Qdrant is index-only and SQLite remains authoritative;
- confirm source attribution, scope gate, stale-hit handling, and fallback
  diagnostics;
- confirm no forbidden dependency or default-boundary change.

Integrated tests gate:

- rerun focused archival tests;
- rerun full `pytest`, `ruff`, `mypy`, and hard eval as fresh target-branch
  verification.

Merge approval gate:

- require `xmuse/approvals/archive-rag/merge_approval.json`;
- require fresh target validation after approval;
- merge only by Master decision.

Post-merge verification gate:

- run fresh verification on the target branch after merge;
- write `xmuse/approvals/archive-rag/post_merge_verification.json`;
- record rollback/blocking decision if verification fails.
