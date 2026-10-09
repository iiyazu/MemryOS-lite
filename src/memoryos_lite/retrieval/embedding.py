"""Embedding-based semantic searcher.

Uses cosine similarity over page embeddings fetched from the relational store.
"""

from __future__ import annotations

from memoryos_lite.retrieval.base import EmbeddingClient, SearchHit, cosine_similarity
from memoryos_lite.schemas import MemoryPage
from memoryos_lite.store_protocols import PageEmbeddingStore


class EmbeddingSearcher:
    def __init__(
        self,
        store: PageEmbeddingStore,
        client: EmbeddingClient,
    ) -> None:
        self.store = store
        self.client = client

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        if not pages or not query:
            return []
        return self._search_python(pages, query, top_k)

    def _search_python(
        self,
        pages: list[MemoryPage],
        query: str,
        top_k: int,
    ) -> list[SearchHit]:
        try:
            query_embedding = self.client.embed(query)
        except Exception:
            return []
        if not query_embedding:
            return []
        return self._search_python_with_query_embedding(pages, query_embedding, top_k)

    def _search_python_with_query_embedding(
        self,
        pages: list[MemoryPage],
        query_embedding: list[float],
        top_k: int,
    ) -> list[SearchHit]:
        page_ids = [page.id for page in pages]
        embeddings = self.store.get_page_embeddings(page_ids)
        if not embeddings:
            return []
        scored: list[tuple[float, MemoryPage]] = []
        for page in pages:
            page_vec = embeddings.get(page.id)
            if not page_vec:
                continue
            score = cosine_similarity(query_embedding, page_vec)
            if score > 0:
                scored.append((score, page))
        scored.sort(
            key=lambda pair: (pair[0], pair[1].confidence, pair[1].created_at),
            reverse=True,
        )
        return [
            SearchHit(
                page=page,
                score=float(score),
                reason=f"cosine={score:.4f}",
                source="embedding",
            )
            for score, page in scored[:top_k]
        ]
