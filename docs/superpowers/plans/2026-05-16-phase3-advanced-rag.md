# Phase 3 Iteration 1: Advanced RAG Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the full Advanced RAG pipeline (query rewrite + multi-query expansion + LLM rerank) using DeepSeek, and measure impact on LongMemEval source_hit.

**Architecture:** Extend existing `QueryRewriter` with an `expand()` method that generates 2-3 query variants via LLM. Modify `HybridSearcher` to search per-variant and merge results before reranking. Enable rewrite+rerank in public benchmark settings by passing through the DeepSeek API key.

**Tech Stack:** DeepSeek API (OpenAI-compatible), langchain_openai, fastembed, existing retrieval layer.

---

## File Structure

| File | Role |
|------|------|
| `src/memoryos_lite/retrieval/query_rewriter.py` | Add `expand()` method |
| `src/memoryos_lite/retrieval/hybrid.py` | Multi-query search loop |
| `src/memoryos_lite/public_benchmarks.py` | Pass DeepSeek key, enable flags |
| `tests/test_query_expansion.py` | Tests for expand() |
| `tests/test_hybrid_multiquery.py` | Tests for multi-query search |

---

### Task 1: Multi-query Expansion in QueryRewriter

**Files:**
- Modify: `src/memoryos_lite/retrieval/query_rewriter.py`
- Create: `tests/test_query_expansion.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_expansion.py
from unittest.mock import MagicMock, patch
from memoryos_lite.retrieval.query_rewriter import QueryRewriter, ExpandedQueries


def test_expand_returns_multiple_queries_with_llm():
    """expand() should return 2-3 variant queries including original."""
    rewriter = QueryRewriter(
        model="deepseek-v4-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    mock_result = ExpandedQueries(
        variants=["What is Alice's home city?", "Where does Alice live now?"]
    )
    with patch.object(rewriter, "_llm") as mock_llm:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_result
        mock_llm.with_structured_output.return_value = mock_structured
        result = rewriter.expand("Where does Alice live?")

    assert len(result) >= 2
    assert "Where does Alice live?" in result


def test_expand_without_llm_returns_original_only():
    """expand() without LLM returns list with just the original query."""
    rewriter = QueryRewriter()
    result = rewriter.expand("Where does Alice live?")
    assert result == ["Where does Alice live?"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_query_expansion.py -v`
Expected: FAIL — `ExpandedQueries` not defined, `expand` method not found.

- [ ] **Step 3: Implement expand() in QueryRewriter**

Add to `src/memoryos_lite/retrieval/query_rewriter.py`:

```python
class ExpandedQueries(BaseModel):
    """Structured output from multi-query expansion."""
    variants: list[str] = Field(
        description="2-3 alternative phrasings of the query"
    )


# Add to QueryRewriter class:
    def expand(self, query: str, profile_context: str = "") -> list[str]:
        """Generate 2-3 query variants for multi-path retrieval."""
        if self._llm is None:
            return [query]

        system = (
            "Generate 2-3 alternative phrasings of this query for memory retrieval. "
            "Each variant should approach the question from a different angle. "
            "Include keywords that might appear in the answer, not just the question."
        )
        if profile_context:
            system += f"\n\nUser context:\n{profile_context}"

        structured = self._llm.with_structured_output(ExpandedQueries)
        try:
            result = structured.invoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Original query: {query}"},
                ]
            )
            if isinstance(result, ExpandedQueries) and result.variants:
                variants = [query] + [v for v in result.variants if v != query]
                return variants[:4]
        except Exception:
            pass
        return [query]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_query_expansion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/retrieval/query_rewriter.py tests/test_query_expansion.py
git commit -m "feat(retrieval): add multi-query expansion to QueryRewriter"
```

---

### Task 2: Multi-query Search Loop in HybridSearcher

**Files:**
- Modify: `src/memoryos_lite/retrieval/hybrid.py`
- Create: `tests/test_hybrid_multiquery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hybrid_multiquery.py
from unittest.mock import MagicMock
from memoryos_lite.retrieval.hybrid import HybridSearcher
from memoryos_lite.retrieval.base import SearchHit
from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.schemas import MemoryPage
from memoryos_lite.utils import utc_now


def _make_page(page_id: str, title: str) -> MemoryPage:
    return MemoryPage(
        id=page_id,
        session_id="ses_test",
        title=title,
        summary=title,
        facts=[title],
        source_message_ids=[f"msg_{page_id}"],
    )


def test_multiquery_merges_results_from_multiple_queries():
    """Multi-query should find pages that single query misses."""
    pages = [
        _make_page("p1", "Alice lives in Shanghai"),
        _make_page("p2", "Alice moved to Beijing recently"),
        _make_page("p3", "Weather forecast for today"),
    ]
    lexical = LexicalSearcher()
    rewriter = MagicMock()
    rewriter.expand.return_value = [
        "Where does Alice live?",
        "Alice current city residence",
        "Alice home location",
    ]
    searcher = HybridSearcher(
        lexical=lexical, embedding=None, query_rewriter=rewriter
    )
    results = searcher.search(pages, "Where does Alice live?", top_k=5)
    hit_ids = [h.page.id for h in results]
    # Multi-query should find both p1 and p2 via different query variants
    assert "p1" in hit_ids or "p2" in hit_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hybrid_multiquery.py -v`
Expected: FAIL — `expand` not called, or `AttributeError`.

- [ ] **Step 3: Modify HybridSearcher.search() for multi-query**

Replace the search method body in `src/memoryos_lite/retrieval/hybrid.py`:

```python
    def search(
        self,
        pages: list[MemoryPage],
        query: str,
        top_k: int = 5,
        profile_context: str = "",
    ) -> list[SearchHit]:
        if not pages or not query:
            return []

        # Step 1: Query expansion (multi-query or single rewrite)
        queries: list[str]
        if self.query_rewriter is not None and hasattr(self.query_rewriter, "expand"):
            try:
                queries = self.query_rewriter.expand(query, profile_context)
            except Exception:
                queries = [query]
        elif self.query_rewriter is not None:
            try:
                queries = [self.query_rewriter.rewrite(query, profile_context)]
            except Exception:
                queries = [query]
        else:
            queries = [query]

        # Step 2: Per-query dual retrieval + merge
        per_source_k = max(top_k * 2, 10)
        all_ranked: dict[str, list[SearchHit]] = {}
        for i, q in enumerate(queries):
            lexical_hits = self.lexical.search(pages, q, top_k=per_source_k)
            if lexical_hits:
                all_ranked[f"lexical_{i}"] = lexical_hits
            if self.embedding is not None:
                emb_hits = self.embedding.search(pages, q, top_k=per_source_k)
                if emb_hits:
                    all_ranked[f"embedding_{i}"] = emb_hits

        if not all_ranked:
            return []
        fused = reciprocal_rank_fusion(
            all_ranked, k=self.rrf_k, top_k=max(top_k * 2, 10)
        )

        # Step 3: LLM reranking
        if self.reranker is not None:
            return self.reranker.rerank(fused, query, top_k=top_k)
        return fused[:top_k]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hybrid_multiquery.py tests/test_query_expansion.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `uv run pytest -q -p no:cacheprovider`
Expected: All pass (263+)

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/retrieval/hybrid.py tests/test_hybrid_multiquery.py
git commit -m "feat(retrieval): multi-query search loop in HybridSearcher"
```

---

### Task 3: Enable Advanced RAG in Public Benchmarks

**Files:**
- Modify: `src/memoryos_lite/public_benchmarks.py`

- [ ] **Step 1: Modify benchmark settings to pass DeepSeek key**

In `src/memoryos_lite/public_benchmarks.py`, change `run_settings`:

```python
    run_settings = settings.model_copy(
        update={
            "data_dir": run_dir,
            "database_url": None,
            "memoryos_paging_mode": "heuristic",
            "openai_api_key": None,
            "deepseek_api_key": settings.deepseek_api_key,  # pass through
            "rot_safe_budget": 4_800,
            "memoryos_embedding_provider": "fastembed",
            "memoryos_rewrite_enabled": bool(settings.deepseek_api_key),
            "memoryos_rerank_enabled": bool(settings.deepseek_api_key),
        }
    )
```

- [ ] **Step 2: Run hard eval to verify no regression**

Run: `uv run memoryos eval run --case-set hard --baseline memoryos_lite`
Expected: 1.00/1.00

- [ ] **Step 3: Run LongMemEval with Advanced RAG**

Run:
```bash
uv run memoryos eval public --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 \
  --run-id phase3_advanced_rag
```

- [ ] **Step 4: Run diagnostic and compare**

Run:
```bash
uv run memoryos eval diagnose .memoryos/evals/phase3_advanced_rag_longmemeval.json
```

Compare source_hit against baseline (30%). Record:
- source_hit before/after
- fail→pass cases
- pass→fail cases (regressions)
- API cost (number of LLM calls)

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/public_benchmarks.py
git commit -m "feat(eval): enable rewrite + rerank + multi-query in public benchmarks"
```

---

### Task 4: Verify and Document Results

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -q -p no:cacheprovider`
Expected: All pass

- [ ] **Step 2: Record before/after comparison**

Create a summary comparing:
- Phase 2.6c (baseline, no LLM): source_hit = 30%
- Phase 3 iter 1 (Advanced RAG): source_hit = ?%
- Failure mode breakdown changes
- API cost per case

- [ ] **Step 3: Final commit with results**

```bash
git commit -m "docs: record Phase 3 iteration 1 results"
```
