# Phase 2 Final Plan: Recall Memory Layer

> Goal: upgrade the opt-in `v2` episode recall path into a real Recall Memory Layer while keeping default `v1` behavior unchanged and preserving the old `episode_*` benchmark outputs as compatibility mappings.

## Task 1: Lock in searcher compatibility with new recall semantics

**Files**
- `tests/test_episode_retrieval.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/__init__.py`

**Steps**
1. Add failing tests for:
   - `EpisodeSearcher` legacy compatibility still returning `source == "episode_bm25"`.
   - `RecallMemorySearcher` returning structured diagnostics for direct hits, neighbors, dedupe, and role/rank features.
   - Neighbor expansion on same-session adjacent entries.
2. Implement `RecallMemorySearcher` over `Episode | RecallMemoryEntry`.
3. Keep `EpisodeSearcher` as a thin legacy wrapper that preserves the old `episode_bm25` source label and import path.
4. Export `RecallMemorySearcher` from `retrieval/__init__.py`.
5. Run:
   - `uv run pytest tests/test_episode_retrieval.py -q`

**Implementation notes**
- `EpisodeHit` should carry diagnostics and rank features, but legacy `EpisodeSearcher` must remain source-compatible.
- New recall diagnostics should use structured `DiagnosticEvent` values, not opaque strings.

## Task 2: Move recall semantics into the pipeline

**Files**
- `tests/test_recall_pipeline.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/v3_contracts.py`

**Steps**
1. Add failing tests for:
   - backfill from messages into episodes, then adaptation to recall entries.
   - recall-native metadata keys:
     - `recall_candidate_message_ids`
     - `recall_planned_message_ids`
     - `recall_indexed_source_ids`
     - `recall_diagnostics`
     - `recall_budget_dropped`
   - legacy compatibility mappings:
     - `episode_candidate_message_ids`
     - `planned_evidence_message_ids`
     - `indexed_source_ids`
     - `budget_dropped_relevant`
2. In `RecallPipeline.build_context()`, convert episodes to `RecallMemoryEntry` via `episode_to_recall_entry()`.
3. Use `RecallMemorySearcher` for v2 recall.
4. Serialize diagnostics from selected hits and emit budget-drop diagnostics for skipped hits.
5. Populate both recall-native and legacy metadata keys in `ContextPackage.metadata`.
6. Preserve `v1` default behavior unchanged.
7. Run:
   - `uv run pytest tests/test_recall_pipeline.py tests/test_episode_retrieval.py -q`

**Implementation notes**
- Use `DiagnosticEvent` for direct hit, neighbor, rank, dedupe, and budget_drop.
- The budget-drop branch when task tokens already exceed budget must still emit recall metadata, not just legacy keys.

## Task 3: Make eval and public benchmark mapping prefer recall metadata

**Files**
- `tests/test_evals.py`
- `tests/test_public_benchmarks.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`

**Steps**
1. Add failing tests for:
   - recall-native metadata taking precedence over legacy `episode_*` keys.
   - public benchmark reports still exposing the old field names.
2. Add a presence-aware helper in `evals.py` that prefers recall metadata first and falls back to legacy keys only when the recall key is absent.
3. Use the same presence-aware logic for:
   - `indexed_source_ids`
   - `episode_candidate_message_ids`
   - `planned_evidence_message_ids`
   - `budget_dropped_relevant`
4. Keep `PublicBenchmarkResult.to_report()` field names unchanged.
5. If `episode_source_hit_at_10` is not already set, derive it from the compatibility candidate IDs.
6. Run:
   - `uv run pytest tests/test_evals.py tests/test_public_benchmarks.py -q`

**Implementation notes**
- Do not use truthiness fallback for integer diagnostics; check key presence or explicit `None`.
- Keep the public report schema stable.

## Task 4: Regression verification

**Files**
- none

**Steps**
1. Run focused tests:
   - `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_public_benchmarks.py -q`
2. Run the full suite:
   - `uv run pytest -q`
3. If the local benchmark data is available, run the documented LongMemEval and LoCoMo smoke commands with `MEMORYOS_RECALL_PIPELINE=v2`.
4. Leave source commits to the later GOD_ADVANCE step; do not commit during EXECUTE.

