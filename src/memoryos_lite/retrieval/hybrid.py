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

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        if not pages or not query:
            return []
        # Over-fetch per source so RRF has enough signal to fuse.
        per_source_k = max(top_k * 2, 10)
        lexical_hits = self.lexical.search(pages, query, top_k=per_source_k)
        embedding_hits: list[SearchHit] = []
        if self.embedding is not None:
            embedding_hits = self.embedding.search(pages, query, top_k=per_source_k)

        ranked_lists: dict[str, list[SearchHit]] = {}
        if lexical_hits:
            ranked_lists["lexical"] = lexical_hits
        if embedding_hits:
            ranked_lists["embedding"] = embedding_hits

        if not ranked_lists:
            return []
        return reciprocal_rank_fusion(ranked_lists, k=self.rrf_k, top_k=top_k)
