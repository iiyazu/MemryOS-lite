# Spec: Phase 2 - Recall Memory Layer

## Goal

Upgrade the current opt-in `v2` episode recall path into a real Recall Memory
Layer while keeping default `v1` behavior unchanged.

Target compatibility state: `shadow-read`.

Phase 2 must preserve raw source attribution, support role / temporal / session
/ neighbor-aware recall, and move structured rank, neighbor, budget, drop, and
dedupe diagnostics into the recall layer. Existing `episode_*` benchmark fields
remain available, but they become compatibility projections of recall
diagnostics.

## Source Inputs

- `.hermes-loop/god_dispatch.json`: phase `phase-2`, target `shadow-read`.
- `.hermes-loop/brainstorm.md`: recommends contract-first recall layer with an
  explicit legacy adapter over the existing `episodes` table.
- `.hermes-loop/blueprint.md`: phase-2 tasks and acceptance criteria.
- Current implementation:
  - `src/memoryos_lite/v3_contracts.py` already defines `RecallMemoryEntry`,
    `DiagnosticEvent`, `LayerBudgetDecision`, and `episode_to_recall_entry`.
  - `src/memoryos_lite/store.py` persists and backfills `episodes` from
    `messages`.
  - `src/memoryos_lite/retrieval/episode_searcher.py` currently performs BM25
    episode search with a small role boost.
  - `src/memoryos_lite/retrieval/recall_pipeline.py` currently returns episode
    evidence and old metadata fields.
  - `src/memoryos_lite/evals.py` and
    `src/memoryos_lite/public_benchmarks.py` consume `episode_*` report fields.

## Non-Goals

- Do not create a new `recall_memory_entries` table in phase 2.
- Do not switch default recall from `v1` to `v2` or v3.
- Do not implement Core Memory, Archival Memory, Context Composer, or Agentic
  Kernel behavior.
- Do not special-case LongMemEval or LoCoMo case IDs inside recall search.
- Do not add Letta or Mem0 as runtime dependencies.

## Design

### Recall Entry Boundary

`Episode` remains the legacy physical storage row. `RecallMemoryEntry` is the
logical recall unit. All recall-layer code should convert through
`episode_to_recall_entry` rather than treating `Episode` as the final semantic
model.

The conversion must preserve:

- `message_id` and `source_message_ids`
- `role`
- raw text and index text
- session position
- `benchmark_session_id` and `benchmark_date` as temporal/session metadata, not
  as required ranking inputs
- message-backed `SourceRef` provenance

Backfill stays deterministic: `MemoryStore.ensure_episodes_for_session()` reads
messages ordered by `created_at` and `id`, writes missing episode rows, and the
recall layer adapts those rows into `RecallMemoryEntry` values.

### Search and Ranking

Introduce recall semantics around the existing episode searcher:

- A `RecallMemorySearcher` ranks `RecallMemoryEntry` candidates.
- The existing `EpisodeSearcher` import path remains as a compatibility wrapper
  or alias.
- Ranking uses BM25/token overlap as the base score.
- Role-aware scoring keeps the current assistant-source boost when query
  analysis identifies assistant-source intent.
- Session-aware scoring may boost explicit session/date metadata, but search
  must still work without benchmark-specific IDs.
- Temporal scoring uses available date/order metadata as generic metadata.
- Neighbor expansion may include adjacent same-session entries around direct
  hits, bounded by `top_k` and deduped by message/source ID.

No ranking rule may require a benchmark case ID. Benchmark metadata can be one
source of generic session/temporal metadata, but it cannot be the only path.

### Diagnostics

Recall diagnostics are structured `DiagnosticEvent` objects, not opaque reason
strings. Each candidate or dropped item should explain at least one of:

- `direct_hit`
- `neighbor`
- `dedupe`
- `rank`
- `budget_drop`
- `session_match`
- `temporal_match`
- `role_match`

The recall layer should still provide compact human-readable `reason` strings
for legacy `ContextEvidence`, but those strings are derived from structured
diagnostics.

### Pipeline Output

`RecallPipeline.build_context()` continues returning `ContextPackage` so the
engine and benchmark callers remain compatible.

The pipeline should:

1. Ensure recall backfill for the session.
2. Convert episodes to recall entries.
3. Search recall entries.
4. Apply budget selection.
5. Emit `ContextEvidence` for selected entries.
6. Emit structured recall diagnostics and legacy-mapped metadata.

Required metadata keys:

- `recall_candidate_message_ids`: ranked direct/neighbor candidate source IDs.
- `recall_planned_message_ids`: selected evidence source IDs after budget.
- `recall_indexed_source_ids`: source IDs available in the recall index.
- `recall_diagnostics`: serialized `DiagnosticEvent` values.
- `recall_budget_dropped`: count of recall candidates dropped by budget.
- `episode_candidate_message_ids`: compatibility mapping from
  `recall_candidate_message_ids`.
- `planned_evidence_message_ids`: compatibility mapping from
  `recall_planned_message_ids`.
- `indexed_source_ids`: compatibility mapping from `recall_indexed_source_ids`.
- `budget_dropped_relevant`: compatibility mapping from `recall_budget_dropped`.

### Benchmark Mapping

`evals.py` and `public_benchmarks.py` should treat old `episode_*` fields as
report compatibility fields. Their source of truth is recall metadata when
present, with old metadata keys as fallback during migration.

The public report must continue exposing:

- `episode_source_hit_at_10`
- `episode_candidate_message_ids`
- `planned_evidence_source_hit_at_5`
- `planned_evidence_message_ids`
- `source_not_indexed`
- `budget_dropped_relevant`

The report may also expose recall-native fields later, but phase 2 does not
require a public schema expansion.

## Compatibility Rules

- `MEMORYOS_RECALL_PIPELINE=v1` remains the default.
- `MEMORYOS_RECALL_PIPELINE=v2` is the only path that reads the new recall-layer
  semantics during phase 2.
- The `episodes` table remains authoritative recall storage for this phase.
- Existing `EpisodeSearcher` imports remain valid.
- Existing benchmark JSON keys remain valid.
- Existing source IDs remain raw message IDs.

## Acceptance Criteria

- Recall entries can be backfilled from messages through the existing
  `episodes` table and adapted to `RecallMemoryEntry`.
- Recall search does not rely on benchmark case IDs.
- Recall diagnostics explain direct hit, neighbor, drop, dedupe, and rank.
- Old `episode_*` benchmark fields continue to work as mapped diagnostics.
- `v1` default behavior remains unchanged.
- Full test suite remains green.
- LongMemEval and LoCoMo recall hit stay at or above the smoke baseline recorded
  in the blueprint: LongMemEval `8/10`, LoCoMo `5/10`.
