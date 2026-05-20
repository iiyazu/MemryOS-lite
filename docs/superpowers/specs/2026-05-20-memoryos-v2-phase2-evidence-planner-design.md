# MemoryOS v2 Phase 2 — Evidence Planner and Context Packing

## Problem

Phase 1 added an opt-in episode-first recall path. It can search raw message
episodes and expose v2 diagnostics, but the current `RecallPipeline` is still a
thin top-k loader:

```text
QueryAnalyzer -> EpisodeSearcher(top_k=10) -> append hits while budget allows
```

That is enough to prove that raw message evidence is reachable, but it is not
enough to make evidence consistently useful for LongMemEval and LoCoMo:

- The planner does not explicitly distinguish source evidence, neighbor
  evidence, role/date/session diversity, or fallback evidence.
- Temporal and multi-session questions need adjacent turns and date/session
  context, but Phase 1 only stores neighbor context in `index_text`; it does
  not add neighboring source messages to the final evidence plan.
- Assistant-source questions need stronger role-aware ordering than a simple
  score boost.
- Diagnostics show candidate and planned IDs, but they do not explain *why* an
  evidence item entered the plan, was expanded, or was dropped.
- `core_memory` remains deferred. It should eventually cache stable facts, but
  Phase 2 should not add a lossy always-on memory layer before raw evidence
  planning is reliable.

## Goals

- Keep default `v1` behavior unchanged.
- Improve v2 planned evidence quality without adding LLM, Qdrant, or new
  external dependencies.
- Introduce an explicit evidence planning stage inside v2 recall.
- Add deterministic neighbor expansion for temporal and multi-session queries.
- Add role-aware and session/date-aware ranking rules that are explainable in
  `ContextPackage.metadata`.
- Keep source attribution grounded in original `message_id` /
  `source_message_ids`.
- Preserve current smoke baseline:
  - hard eval remains `1.00/1.00`
  - LongMemEval v2 smoke planned evidence does not regress below `8/10`
  - LoCoMo v2 smoke planned evidence targets improvement over `5/10`
  - `source_not_indexed` remains `0/10` on both current smoke slices

## Non-Goals

- Do not make v2 the default.
- Do not implement `core_memory` in this phase.
- Do not add new persistent tables.
- Do not change public benchmark answer generation or LLM judge behavior.
- Do not introduce dataset-specific case-id rules or benchmark-string hacks.
- Do not remove page/item APIs or v1 diagnostics.

## Design

Phase 2 keeps the Phase 1 retrieval units and adds a deterministic planner:

```text
query
  -> QueryAnalyzer
  -> EpisodeSearcher
  -> EvidencePlanner
       score normalization
       role/session/date boosts
       neighbor expansion
       dedupe
       budget-aware packing
       decision metadata
  -> ContextPackage
```

The planner operates only on in-memory `Episode` records returned by
`store.list_episodes(session_id)`. It does not require new persistence.

`EpisodeSearcher` must expose structured overlap data on each hit so the
planner never has to parse a free-text reason string:

```text
EpisodeHit
  episode
  score
  lexical_overlap: int
  matched_terms: list[str]
  role_boost: float
  session_boost: float
  temporal_boost: float
  source: str
  reason: str
```

`reason` stays human-readable for traces, but the planner must use the
structured fields above for all ranking and metadata decisions.

## Query Analysis

`QueryAnalysis` should keep a primary `kind` for compatibility, but it must
also expose additive flags so one query can be both temporal and
assistant-source aware.

```text
kind: temporal | assistant_source | multi_session | general
flags:
  needs_neighbors: bool
  prefer_assistant_roles: bool
  prefer_temporal_order: bool
  prefer_session_diversity: bool
  neighbor_before: int
  neighbor_after: int
```

Interpretation rules:

- `kind` is determined by the first matching cue in this order:
  `assistant_source` -> `temporal` -> `multi_session` -> `general`.
- `flags` are additive and may coexist even when one `kind` wins.
- `assistant_source` queries always set `prefer_assistant_roles=true`.
- `temporal` queries always set `needs_neighbors=true`,
  `prefer_temporal_order=true`, `neighbor_before=1`, `neighbor_after=1`.
- `multi_session` queries always set `prefer_session_diversity=true`.
- `general` queries keep all flags false unless a direct lexical cue requires
  a neighbor, in which case `needs_neighbors=true` and one of the neighbor
  counters may be set without changing `kind`.

## Evidence Candidate Model

Add an internal planner dataclass, not a public schema:

```text
PlannedEvidence
  episode
  score
  origin: episode | neighbor
  reason
  parent_message_id: str | None
  rank_features: dict[str, float | str | bool]
  lexical_overlap: int
  matched_terms: list[str]
```

`origin="episode"` means the message was a direct search hit. `origin="neighbor"`
means it was added because a direct hit needed surrounding turns. Neighbor
evidence must record `parent_message_id` so diagnostics can explain why it
appeared.

## Ranking Rules

Ranking remains deterministic and local:

1. Start from `EpisodeHit.score`.
2. Add role boost:
   - assistant-source query + assistant role: strong boost.
   - assistant-source query + immediately preceding user neighbor: small boost.
3. Add session/date diversity tie-break:
   - for multi-session queries, avoid filling all top slots from one
     `benchmark_session_id` when similarly scored candidates from other
     sessions exist.
4. Add exact/near lexical overlap bonus from structured search output rather
   than parsing free-text reason strings.
5. Penalize duplicate message IDs and duplicate normalized text.

The planner should not hard-code benchmark case IDs, expected answers, or
dataset-specific proper nouns.

## Neighbor Expansion

Neighbor expansion uses episode `position` within the same `session_id`.

Rules:

- For temporal queries, add up to one previous and one next episode around each
  direct hit.
- For assistant-source queries, add the immediately preceding user episode
  around assistant hits.
- For multi-session queries, add neighbors only after at least two direct hits
  from distinct `benchmark_session_id` values are planned, unless budget would
  otherwise leave fewer than three evidence snippets.
- Neighbor evidence is lower priority than direct hits unless its role is
  explicitly preferred by the query analysis.

## Budget Packing

Budget packing should be explicit:

1. Reserve task text first.
2. Add direct source hits by planned rank.
3. Add required neighbors.
4. Stop before exceeding budget.

When an evidence candidate is dropped, metadata should record:

```text
dropped_evidence_message_ids
dropped_evidence_origins
dropped_evidence_reasons
budget_dropped_relevant
```

`budget_dropped_relevant` remains a count for compatibility. Phase 2 may also
add richer fields, but existing public report fields must keep their meaning.

## ContextPackage Metadata

Phase 2 must preserve existing metadata keys:

```text
episode_backfilled
item_candidate_source_ids
indexed_source_ids
episode_candidate_message_ids
planned_evidence_message_ids
planned_evidence_origins
budget_dropped_relevant
```

Add planner diagnostics:

```text
query_kind
planner_decisions
planned_evidence_parent_ids
planned_evidence_scores
dropped_evidence_message_ids
dropped_evidence_reasons
neighbor_expanded_message_ids
distinct_planned_benchmark_session_ids
```

`planner_decisions` should be a list of small dictionaries that can be serialized
into traces and eval reports without custom encoders.

Stable `planner_decisions` shape:

```text
[
  {
    "step": "direct_hit" | "neighbor" | "drop" | "dedupe" | "rank",
    "message_id": "msg_123",
    "origin": "episode" | "neighbor",
    "reason": "assistant_source_boost" | "temporal_neighbor" | ...,
    "score_before": 1.2,
    "score_after": 3.4,
    "kept": true,
    "tokens": 18,
    "parent_message_id": "msg_122" | null,
    "benchmark_session_id": "s1" | null,
    "benchmark_date": "2026-01-01" | null
  }
]
```

Rules:

- Every final planned evidence item must generate at least one `planner_decisions`
  entry.
- Every dropped evidence item must generate at least one `drop` entry.
- Every deduped evidence item must generate at least one `dedupe` entry.
- `reason` must be one of a fixed enum:
  `direct_hit`, `assistant_source_boost`, `temporal_neighbor`,
  `multi_session_diversity`, `budget_drop`, `duplicate_message`,
  `duplicate_text`, `role_preference`.
- `score_before` and `score_after` are required for `rank`, `direct_hit`,
  `neighbor`, and `drop` steps.
- `tokens` is required for `neighbor`, `direct_hit`, and `drop` steps.

## Public Benchmark Diagnostics

Keep current public report fields stable. Add optional fields only if they come
from `ContextPackage.metadata` and are useful for debugging:

- `query_kind`
- `neighbor_expanded_message_ids`
- `dropped_evidence_message_ids`
- `distinct_planned_benchmark_session_ids`

The public harness should continue to run when v2 is disabled and should not
mark non-v2 runs as `source_not_indexed`.

## Testing Strategy

Unit tests:

- QueryAnalyzer returns expected planner flags for temporal, assistant-source,
  multi-session, and general queries.
- EvidencePlanner dedupes direct hits and neighbor expansions.
- Assistant-source query ranks assistant evidence before user evidence when
  scores are close.
- Temporal query adds neighbors in position order.
- Multi-session query prefers distinct benchmark sessions when candidates are
  close.
- Budget packing records dropped evidence reasons.

Integration tests:

- v1 default still creates no episodes on ingest and does not route through v2.
- v2 build_context returns planner metadata and non-empty evidence on a small
  synthetic session.
- v2 public diagnostic fields remain present and JSON-serializable.
- `source_not_indexed` remains false for non-v2 runs and still uses the full
  indexed source set in v2 reports.

Verification:

```bash
uv run pytest tests/test_engine.py tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_public_benchmarks.py tests/test_public_benchmarks_items.py tests/test_diagnostic_report.py tests/test_evals.py tests/test_evals_advanced.py -q
uv run pytest -q
uv run memoryos eval run --case-set hard --baseline memoryos_lite
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id v2_lme_phase2_smoke
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id v2_locomo_phase2_smoke
```

## Success Criteria

Phase 2 is acceptable when:

- Full tests pass.
- Hard eval remains `1.00/1.00`.
- v1 default behavior remains unchanged.
- v2 smoke LongMemEval planned evidence remains at least `8/10`.
- v2 smoke LoCoMo planned evidence is at least `5/10` on the frozen 10-case
  smoke command.
- `source_not_indexed` remains `0/10` on both frozen smoke commands.
- `planner_decisions` is present, JSON-serializable, and passes the unit tests
  for temporal and assistant-source synthetic sessions.
- The following command succeeds with exit code 0:

```bash
uv run pytest tests/test_engine.py tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_public_benchmarks.py tests/test_public_benchmarks_items.py tests/test_diagnostic_report.py tests/test_evals.py tests/test_evals_advanced.py -q
```

## Deferred: Core Memory

`core_memory` remains a later layer. It should eventually store stable,
source-backed facts that are useful across tasks, similar to Letta-style memory
blocks. It should not be introduced before episode evidence planning is stable,
because a lossy always-on core layer can hide whether the system can still cite
the original source messages.
