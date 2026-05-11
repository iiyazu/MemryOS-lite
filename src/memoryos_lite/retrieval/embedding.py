"""Embedding-based semantic searcher.

Uses cosine similarity over stored page embeddings. When Postgres+pgvector
is the backing store, embeddings are fetched via a bulk query; when the
store runs on SQLite, embeddings come back as JSON-decoded lists through
the ``EmbeddingType`` TypeDecorator. Either way the ranking math happens
in Python for M2 — moving the KNN to SQL via
``ORDER BY embedding <=> :q`` is an M5 optimization and requires pgvector
IVFFlat indexes once the corpus is large enough.
"""

from __future__ import annotations

from memoryos_lite.retrieval.base import EmbeddingClient, SearchHit, cosine_similarity
from memoryos_lite.schemas import MemoryPage
from memoryos_lite.store import MemoryStore


class EmbeddingSearcher:
    def __init__(self, store: MemoryStore, client: EmbeddingClient) -> None:
        self.store = store
        self.client = client

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        if not pages or not query:
            return []
        page_ids = [page.id for page in pages]
        embeddings = self.store.get_page_embeddings(page_ids)
        if not embeddings:
            return []

        query_embedding = self.client.embed(query)
        if not query_embedding:
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
