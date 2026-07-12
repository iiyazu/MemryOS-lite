"""Embedding-based semantic searcher.

Uses cosine similarity over stored page embeddings. When a QdrantEmbeddingStore
is configured, ANN search is delegated to Qdrant. Otherwise falls back to
Python-side cosine over embeddings fetched from the relational store.
"""

from __future__ import annotations

from typing import Protocol

from memoryos_lite.retrieval.base import EmbeddingClient, SearchHit, cosine_similarity
from memoryos_lite.schemas import MemoryPage
from memoryos_lite.store import MemoryStore


class QdrantEmbeddingStore(Protocol):
    def query(
        self,
        vector: list[float],
        top_k: int,
        page_ids: list[str] | None = None,
    ) -> list[tuple[str, float]]: ...


class EmbeddingSearcher:
    def __init__(
        self,
        store: MemoryStore,
        client: EmbeddingClient,
        qdrant_store: QdrantEmbeddingStore | None = None,
    ) -> None:
        self.store = store
        self.client = client
        self.qdrant_store = qdrant_store

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        if not pages or not query:
            return []
        if self.qdrant_store is not None:
            try:
                query_embedding = self.client.embed(query)
            except Exception:
                return []
            if not query_embedding:
                return []
            try:
                return self._search_qdrant(pages, query_embedding, top_k)
            except Exception:
                return self._search_python_with_query_embedding(pages, query_embedding, top_k)
        return self._search_python(pages, query, top_k)

    def _search_qdrant(
        self,
        pages: list[MemoryPage],
        query_embedding: list[float],
        top_k: int,
    ) -> list[SearchHit]:
        assert self.qdrant_store is not None
        page_ids = [page.id for page in pages]
        page_by_id = {page.id: page for page in pages}
        results = self.qdrant_store.query(query_embedding, top_k=top_k, page_ids=page_ids)
        hits: list[SearchHit] = []
        for page_id, score in results:
            page = page_by_id.get(page_id)
            if page is not None and score > 0:
                hits.append(
                    SearchHit(
                        page=page,
                        score=float(score),
                        reason=f"qdrant_cosine={score:.4f}",
                        source="embedding",
                    )
                )
        return hits

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
