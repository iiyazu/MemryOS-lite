"""Hybrid searcher — RRF fusion of BM25 lexical + embedding cosine.

Runs both retrievers over the same candidate pages and fuses their
ranked lists with Reciprocal Rank Fusion. Falls back gracefully to
single-source results when one retriever returns nothing (e.g. no
embeddings persisted yet, or the query has no lexical tokens).

Optionally integrates:
- QueryRewriter: LLM-based query expansion before retrieval
- LLMReranker: LLM-based relevance scoring after RRF fusion
"""

from __future__ import annotations

from memoryos_lite.retrieval.base import SearchHit, reciprocal_rank_fusion
from memoryos_lite.retrieval.embedding import EmbeddingSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.retrieval.query_rewriter import QueryRewriter
from memoryos_lite.retrieval.reranker import LLMReranker
from memoryos_lite.schemas import MemoryPage


class HybridSearcher:
    def __init__(
        self,
        lexical: LexicalSearcher,
        embedding: EmbeddingSearcher | None,
        rrf_k: int = 60,
        query_rewriter: QueryRewriter | None = None,
        reranker: LLMReranker | None = None,
    ) -> None:
        self.lexical = lexical
        self.embedding = embedding
        self.rrf_k = rrf_k
        self.query_rewriter = query_rewriter
        self.reranker = reranker

    def search(
        self,
        pages: list[MemoryPage],
        query: str,
        top_k: int = 5,
        profile_context: str = "",
    ) -> list[SearchHit]:
        if not pages or not query:
            return []

        # Step 1: Query rewriting (LLM-based, no-op if no rewriter)
        search_query = query
        if self.query_rewriter is not None:
            try:
                search_query = self.query_rewriter.rewrite(query, profile_context)
            except Exception:
                search_query = query

        # Step 2: Dual retrieval + RRF fusion
        per_source_k = max(top_k * 2, 10)
        lexical_hits = self.lexical.search(pages, search_query, top_k=per_source_k)
        embedding_hits: list[SearchHit] = []
        if self.embedding is not None:
            embedding_hits = self.embedding.search(pages, search_query, top_k=per_source_k)

        ranked_lists: dict[str, list[SearchHit]] = {}
        if lexical_hits:
            ranked_lists["lexical"] = lexical_hits
        if embedding_hits:
            ranked_lists["embedding"] = embedding_hits

        if not ranked_lists:
            return []
        fused = reciprocal_rank_fusion(ranked_lists, k=self.rrf_k, top_k=max(top_k * 2, 10))

        # Step 3: LLM reranking (no-op if no reranker)
        if self.reranker is not None:
            return self.reranker.rerank(fused, query, top_k=top_k)
        return fused[:top_k]
