"""Hybrid searcher — RRF fusion of BM25 lexical + embedding cosine.

Runs both retrievers over the same candidate pages and fuses their
ranked lists with Reciprocal Rank Fusion. Falls back gracefully to
single-source results when one retriever returns nothing (e.g. no
embeddings persisted yet, or the query has no lexical tokens).
"""

from __future__ import annotations

from memoryos_lite.retrieval.base import SearchHit, reciprocal_rank_fusion
from memoryos_lite.retrieval.embedding import EmbeddingSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.schemas import MemoryPage


class HybridSearcher:
    def __init__(
        self,
        lexical: LexicalSearcher,
        embedding: EmbeddingSearcher | None,
        rrf_k: int = 60,
    ) -> None:
        self.lexical = lexical
        self.embedding = embedding
        self.rrf_k = rrf_k

    def search(
        self,
        pages: list[MemoryPage],
        query: str,
        top_k: int = 5,
        profile_context: str = "",
    ) -> list[SearchHit]:
        if not pages or not query:
            return []

        per_source_k = max(top_k * 2, 10)
        all_ranked: dict[str, list[SearchHit]] = {}
        lexical_hits = self.lexical.search(pages, query, top_k=per_source_k)
        if lexical_hits:
            all_ranked["lexical_0"] = lexical_hits
        if self.embedding is not None:
            emb_hits = self.embedding.search(pages, query, top_k=per_source_k)
            if emb_hits:
                all_ranked["embedding_0"] = emb_hits

        if not all_ranked:
            return []
        fused = reciprocal_rank_fusion(all_ranked, k=self.rrf_k, top_k=max(top_k * 2, 10))
        return fused[:top_k]
