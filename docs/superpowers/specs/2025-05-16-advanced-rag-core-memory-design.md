# Advanced RAG + Core Memory + Salience Design

## Context

MemoryOS Lite achieves 30% source_hit on LongMemEval under pure heuristic conditions.
Phase 2 identified that the retrieval bottleneck is not BM25 vs embedding quality, but
the inability to distinguish answer-bearing sessions from noise sessions. The existing
codebase has Query Rewrite and LLM Rerank implemented but disabled. This design adds
multi-query expansion, enables the full pipeline, and introduces Core Memory + Salience
as a second iteration.

## Success Criteria

| Level | Metric | Target |
|-------|--------|--------|
| Gate | hard eval | 1.00/1.00 |
| Gate | LongMemEval source_hit | >= 30% (no regression) |
| Stretch | LongMemEval source_hit | 40%+ |
| Demo | Deterministic answer eval | Core memory correct + salience ordering correct |

## Architecture Overview

```
Iteration 1 (Advanced RAG):
  Query → [Multi-query expansion (2-3 variants)]
       → per-variant: BM25 + embedding → RRF fusion
       → merge all variants (dedupe by page_id)
       → [LLM Rerank]
       → top_k → prompt assembly

Iteration 2 (Core Memory + Salience):
  Paging → extract core memory blocks (profile/preferences/goals)
  Retrieval → salience_score = similarity * recency_decay
  Context → core memory (always injected) + retrieved pages/items
```

## Iteration 1: Advanced RAG Pipeline

### 1.1 Enable Query Rewrite (existing code)

- Set `memoryos_rewrite_enabled: True` in benchmark run settings
- Requires `chat_api_key` (DeepSeek)
- File: `src/memoryos_lite/retrieval/query_rewriter.py` (no changes needed)
- File: `src/memoryos_lite/public_benchmarks.py` (pass DeepSeek key in run_settings)

### 1.2 Enable LLM Rerank (existing code)

- Set `memoryos_rerank_enabled: True` in benchmark run settings
- File: `src/memoryos_lite/retrieval/reranker.py` (no changes needed)

### 1.3 Multi-query Expansion (new)

Extend existing `QueryRewriter` to return 2-3 variant queries instead of 1.

**Current interface:**
```python
class QueryRewriter:
    def rewrite(self, query: str, profile_context: str = "") -> str
```

**New interface:**
```python
class QueryRewriter:
    def rewrite(self, query: str, profile_context: str = "") -> str
    def expand(self, query: str, profile_context: str = "") -> list[str]
        # Returns 2-3 variant queries (including original)
```

**Integration in HybridSearcher.search():**
```python
if self.query_rewriter and self.query_rewriter.can_expand:
    queries = self.query_rewriter.expand(query)
    all_hits = []
    for q in queries:
        hits = self._search_single(q, pages, top_k)
        all_hits.extend(hits)
    fused = dedupe_and_merge(all_hits)
else:
    fused = self._search_single(query, pages, top_k)
```

**LLM prompt for expansion:**
```
Generate 2-3 alternative phrasings of this query for memory retrieval.
Each variant should approach the question from a different angle.
Return as JSON array of strings.
Original: "{query}"
```

### 1.4 Benchmark Configuration

For LongMemEval with Advanced RAG enabled:
```python
run_settings = settings.model_copy(update={
    "memoryos_rewrite_enabled": True,
    "memoryos_rerank_enabled": True,
    "memoryos_embedding_provider": "fastembed",
    "deepseek_api_key": settings.deepseek_api_key,  # pass through
})
```

## Iteration 2: Core Memory + Salience

### 2.1 Core Memory Block

**Data model:**
```python
class CoreMemoryBlock(BaseModel):
    id: str
    session_id: str
    section: str          # "user_profile" | "preferences" | "active_goals"
    content: str
    updated_at: datetime
    version: int = 1
```

**Storage:** New `core_memory_blocks` table in SQLite.

**Maintenance:**
- Auto-extract during paging: identify profile/preference/goal facts from page
- Agent tool: `update_core_memory(section, content)`
- Conflict resolution: newer information overwrites older

**Context injection:**
- Always injected at the top of context, before page summaries
- Fixed budget cap: 200 tokens
- Format: `[Core Memory] user_profile: ... | preferences: ... | goals: ...`

### 2.2 Salience Scoring

**Formula:**
```
final_score = raw_similarity * recency_decay(item)
recency_decay = exp(-0.01 * hours_since_last_access)
```

- Half-life: ~69 hours (~3 days)
- `last_accessed_at` updated on each retrieval hit
- Schema reserves `reinforcement_count: int = 0` (unused in v1)

**Integration point:** After RRF fusion in ItemSearcher, multiply by recency_decay.

**Schema changes to MemoryItem:**
```python
last_accessed_at: datetime = Field(default_factory=utc_now)
reinforcement_count: int = 0  # reserved
```

### 2.3 Demo Eval Cases

5-10 deterministic cases proving core memory + salience work:

1. User states name/location → core memory contains it
2. User updates location → core memory reflects update (not old value)
3. Query about user profile → context includes core memory
4. Frequently accessed item → ranks higher than stale item with same similarity
5. Old item with no access → decays below newer items

## Files to Modify

| File | Iteration | Change |
|------|-----------|--------|
| `src/memoryos_lite/config.py` | 1 | No change (settings exist) |
| `src/memoryos_lite/public_benchmarks.py` | 1 | Pass DeepSeek key, enable rewrite/rerank |
| `src/memoryos_lite/retrieval/query_rewriter.py` | 1 | Add `expand()` method |
| `src/memoryos_lite/retrieval/hybrid.py` | 1 | Multi-query search loop |
| `src/memoryos_lite/schemas.py` | 2 | Add CoreMemoryBlock, extend MemoryItem |
| `src/memoryos_lite/store.py` | 2 | Add core_memory_blocks table + CRUD |
| `src/memoryos_lite/engine.py` | 2 | Core memory extraction + salience scoring |
| `src/memoryos_lite/retrieval/item_searcher.py` | 2 | Apply recency_decay |

## Constraints

- DeepSeek API key required for rewrite/rerank/expansion
- Benchmark without API key falls back to current behavior (no regression)
- Hard eval must remain 1.00/1.00
- No changes to existing test assertions (additive only)
