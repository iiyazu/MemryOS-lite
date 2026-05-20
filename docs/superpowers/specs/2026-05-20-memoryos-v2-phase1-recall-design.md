# MemoryOS v2 Phase 1 — Item/Episode-First Recall

## Problem

Current MemoryOS Lite still behaves like page-first RAG. The system pages
dialogue into `MemoryPage`, retrieves page summaries, then tries to recover
message-level evidence from page source refs. This works on small deterministic
cases but fails on public long-memory benchmarks:

- LongMemEval has acceptable source attribution on some slices, but answer
  quality lags because retrieved context often lacks the exact evidence shape
  needed for reasoning.
- LoCoMo exposes the core architectural flaw: page-level retrieval is too coarse,
  small pages reduce broad source-union hits, and evidence ranking does not
  reliably find the exact source messages.
- Phase 4 diagnostics showed contextual evidence variants cannot improve recall
  when they search the same page-derived candidate pool.

The first v2 change is to move the primary recall path away from page summaries
and toward mem0-style atomic memories plus raw episodic evidence, while retaining
pages as audit/compression artifacts.

## Goals

- Make `MemoryItem` and raw message evidence the primary retrieval units.
- Add an `Episode` retrieval layer over original messages or message windows.
- Keep `MemoryPage` for audit, compression, and fallback, not as the main recall
  unit.
- Preserve source attribution: every recalled item and evidence snippet must
  trace back to `source_message_ids`.
- Improve LoCoMo evidence localization before optimizing answer prompting.
- Keep offline deterministic mode usable; LLM extraction is optional and must
  have a heuristic fallback.

## Non-Goals

- Do not implement the full Letta-style autonomous agent loop in Phase 1.
- Do not require Qdrant, OpenAI, or DeepSeek for the default test path.
- Do not remove existing page APIs or existing eval baselines.
- Do not optimize UI, auth, production ownership, or deployment concerns.

## Success Metrics

Phase 1 is successful when these hold on the existing public benchmark harness:

- Hard eval remains `1.00/1.00`.
- LongMemEval 50-case `source_hit` does not regress below the current stable
  range.
- LoCoMo 50-case `msg_source_hit_at_5` improves over current `memoryos_lite`
  and targets beating the raw `vector_rag` baseline.
- New diagnostics report:
  - `item_source_hit_at_10`
  - `episode_source_hit_at_10`
  - `planned_evidence_source_hit_at_5`
  - `budget_dropped_relevant`
  - `source_not_indexed`

Answer pass rate is tracked but not the Phase 1 gate. Phase 1 optimizes recall
and evidence planning first.

## Architecture

Phase 1 introduces a recall pipeline with three retrievable memory layers:

```text
Core-like stable facts: deferred to Phase 2
Semantic memory:        MemoryItem
Episodic memory:        Episode / raw message window
Audit memory:           MemoryPage
```

Request flow:

```text
query
  -> QueryAnalyzer
  -> ItemRetriever
  -> EpisodeRetriever
  -> PageFallbackRetriever
  -> EvidencePlanner
  -> ContextBudgeter
  -> ContextPackage
```

Write flow:

```text
ingest(message)
  -> save Message
  -> save Episode index record
  -> maybe extract MemoryItem
  -> embed/index item and episode when providers exist
  -> page() only when rot guard requires compression/audit
```

## Data Model Changes

### Episode

An `Episode` is a retrievable source-grounded unit derived from raw messages.
It is not a summary. It represents either one message or a small neighbor window.

Fields:

```text
id
session_id
message_id
role
text
index_text
benchmark_session_id
benchmark_date
position
source_message_ids
embedding
created_at
```

`text` is used for answer/citation. `index_text` is used for retrieval and may
include speaker, date, neighboring turns, and page metadata.

### MemoryItem Extensions

Extend `MemoryItem` enough to be a real semantic retrieval unit:

```text
entities: list[str]
timestamp: str | None
speaker: str | None
status: active | superseded
confidence: float
superseded_by: str | None
```

The initial implementation may store these in JSON metadata if that is faster
than adding many columns, but the schema must expose them explicitly.

## Retrieval Components

### QueryAnalyzer

Classifies question shape without depending on an LLM:

```text
temporal
preference
profile
assistant_source
multi_session
knowledge_update
general
```

The result controls weights and neighbor expansion. For example,
`assistant_source` raises assistant-message evidence weight, while `temporal`
requires date-aware ordering.

### ItemRetriever

Searches `MemoryItem` using BM25 + optional embedding + RRF.

Inputs:

```text
session_id
query
top_k
include_superseded
```

Output:

```text
ItemHit(item, score, reason, source_message_ids)
```

### EpisodeRetriever

Searches all indexed episodes for the session, not only messages reachable from
top page refs. This is the main fix for the Phase 4 candidate-pool limitation.

It should support:

- BM25 over `index_text`
- optional embedding cosine
- role/date/session boosts
- query-type weighting from `QueryAnalyzer`

### EvidencePlanner

Merges item hits and episode hits into ranked evidence candidates.

Rules:

- Deduplicate by `message_id`.
- Promote exact source messages from item hits.
- Add neighbor messages for temporal and multi-hop questions when budget allows.
- Preserve `page_id` when available, but do not require a page to cite a message.
- Mark whether an evidence candidate came from item, episode, page fallback, or
  recent message.

### ContextBudgeter

Builds `ContextPackage` from planned evidence under a token budget.

Priority order:

1. Task/question text
2. High-confidence source evidence
3. Required neighbor evidence for temporal/multi-hop questions
4. Item summaries only when they add information not present in raw evidence
5. Recent messages
6. Page summaries as fallback

## Integration Plan

### Store Layer

Add tables and methods:

```text
episodes
save_episode()
list_episodes()
get_episode_embeddings()
set_episode_embedding()
```

Extend item storage to persist metadata fields and embeddings without breaking
existing records.

### Engine Layer

Refactor `MemoryOSService` so `build_context()` delegates retrieval to a new
`RecallPipeline`:

```python
package = self.recall_pipeline.build_context(
    session_id=session_id,
    task=task,
    budget=effective_budget,
    retrieval_query=retrieval_query,
)
```

Keep the old `ContextBuilder` path temporarily behind a config flag:

```text
memoryos_recall_pipeline = "v1" | "v2"
```

Default should remain `v1` until tests and public benchmark diagnostics are
green. Public eval can opt into `v2`.

### Indexing

On ingest:

- create one episode per message
- build `index_text` with role/date/session metadata and bounded neighbors
- embed if an embedding provider exists

On page:

- continue saving pages
- continue extracting items from pages
- reindex items with extended metadata

Direct item extraction during ingest is allowed after the page path is stable,
but it is not required for the first merge.

## Testing

Unit tests:

- Episode store create/list/embed round trip
- EpisodeRetriever BM25 finds exact source messages
- ItemRetriever BM25 + embedding merge deduplicates correctly
- EvidencePlanner deduplicates item/episode hits and preserves citations
- ContextBudgeter prefers raw evidence over page summaries

Regression tests:

- Existing hard eval remains passing
- Existing API tests continue to pass with default `v1`
- New `v2` public benchmark smoke test runs on a small LME/LoCoMo slice

Benchmark commands:

```bash
uv run pytest -q
uv run memoryos eval run --case-set hard --baseline memoryos_lite
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 --no-llm-answer --no-llm-judge
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite --limit 50 --no-llm-answer --no-llm-judge
```

## Risks

- The new episode layer can become equivalent to raw vector RAG if item evidence
  is not weighted carefully. The planner must report per-source contribution.
- More candidate evidence can exceed budget. The budgeter must track dropped
  relevant evidence explicitly.
- Keeping `v1` and `v2` side by side adds temporary complexity, but it gives a
  clean rollback path and makes before/after evals honest.

## Decision

Proceed with Phase 1 as an opt-in `v2` recall pipeline. The first milestone is
not answer generation improvement; it is reliable source evidence localization
from item and episode indices. Once LoCoMo evidence recall improves, Phase 2 can
add Letta-style core memory promotion and Phase 3 can optimize answer planning.
