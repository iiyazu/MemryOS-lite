"""Qdrant-backed vector store for page embeddings.

Wraps qdrant-client so the rest of the retrieval layer stays dialect-agnostic.
When configured, embeddings are upserted to Qdrant (in addition to the
relational column for backward compatibility) and ANN queries replace the
Python-side cosine scan in EmbeddingSearcher.

In-memory mode (`QdrantClient(":memory:")`) is used by unit tests so no real
Qdrant service is required.
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)


class QdrantEmbeddingStore:
    """Thin wrapper around a Qdrant collection of page embeddings.

    The collection stores one point per MemoryPage. Point IDs are deterministic
    UUID5 derived from the page id so upserts are idempotent. The original
    page_id is preserved in the payload for filter and lookup.
    """

    _NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

    def __init__(
        self,
        url: str,
        collection: str,
        dim: int = 1536,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.collection = collection
        self.dim = dim
        if url == ":memory:":
            self.client = QdrantClient(":memory:")
        else:
            self.client = QdrantClient(url=url, api_key=api_key, timeout=timeout)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
        )

    @classmethod
    def _point_id(cls, page_id: str) -> str:
        return str(uuid.uuid5(cls._NAMESPACE, page_id))

    def upsert(self, page_id: str, vector: list[float]) -> None:
        if len(vector) != self.dim:
            raise ValueError(
                f"embedding dimension mismatch: got {len(vector)}, expected {self.dim}"
            )
        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=self._point_id(page_id),
                    vector=list(vector),
                    payload={"page_id": page_id},
                )
            ],
        )

    def query(
        self,
        vector: list[float],
        top_k: int,
        page_ids: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return [(page_id, cosine_score)] sorted by descending score.

        When ``page_ids`` is provided, results are restricted to that set so
        the engine's session-scoped retrieval semantics are preserved.
        """
        if top_k <= 0:
            return []
        query_filter: Filter | None = None
        if page_ids:
            query_filter = Filter(
                must=[FieldCondition(key="page_id", match=MatchAny(any=list(page_ids)))]
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=list(vector),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        results: list[tuple[str, float]] = []
        for point in response.points:
            payload = point.payload or {}
            page_id = payload.get("page_id")
            if isinstance(page_id, str):
                results.append((page_id, float(point.score)))
        return results

    def delete(self, page_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=[self._point_id(page_id)],
        )
