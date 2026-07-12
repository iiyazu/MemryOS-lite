"""Qdrant-backed vector index for archival passages.

This provider is intentionally separate from the page embedding provider. It
stores only lookup/index metadata for ``ArchivalPassage`` points; SQLite remains
the source of final text, source refs, scope eligibility, and update/delete
state.
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from memoryos_lite.retrieval.archival_vector import (
    ArchivalEmbeddingConfig,
    ArchivalVectorHit,
)
from memoryos_lite.v3_contracts import ArchivalPassage


class QdrantArchivalPassageStore:
    """Thin wrapper around an archival-passage-only Qdrant collection."""

    _NAMESPACE = uuid.UUID("2ca8e3ce-1a1d-4a9d-a89f-0901b2d9f4f7")
    _PAYLOAD_NAMESPACE = "memoryos_archival_passage"

    def __init__(
        self,
        url: str,
        collection: str,
        dim: int,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.collection = collection
        self.dim = dim
        client_timeout = int(timeout) if timeout is not None else None
        if url == ":memory:":
            self.client = QdrantClient(":memory:")
        else:
            self.client = QdrantClient(url=url, api_key=api_key, timeout=client_timeout)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
        )

    @classmethod
    def point_id(cls, passage_id: str) -> str:
        return str(uuid.uuid5(cls._NAMESPACE, passage_id))

    def upsert_passage(
        self,
        passage: ArchivalPassage,
        vector: list[float],
        config: ArchivalEmbeddingConfig,
    ) -> None:
        self._validate_vector(vector)
        payload = self._payload(passage, config)
        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=self.point_id(passage.id),
                    vector=list(vector),
                    payload=payload,
                )
            ],
        )

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        passage_ids: list[str] | None,
        config: ArchivalEmbeddingConfig,
    ) -> list[ArchivalVectorHit]:
        if top_k <= 0:
            return []
        self._validate_vector(vector)
        if passage_ids is not None and not passage_ids:
            return []
        conditions: list[Any] = [
            FieldCondition(
                key="namespace",
                match=MatchValue(value=self._PAYLOAD_NAMESPACE),
            ),
            FieldCondition(
                key="embedding_config_hash",
                match=MatchValue(value=config.config_hash),
            ),
        ]
        if passage_ids is not None:
            conditions.append(
                FieldCondition(
                    key="passage_id",
                    match=MatchAny(any=list(passage_ids)),
                )
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=list(vector),
            limit=top_k,
            query_filter=Filter(must=conditions),
            with_payload=True,
        )
        hits: list[ArchivalVectorHit] = []
        for point in response.points:
            payload = dict(point.payload or {})
            passage_id = payload.get("passage_id")
            if isinstance(passage_id, str):
                hits.append(
                    ArchivalVectorHit(
                        passage_id=passage_id,
                        score=float(point.score),
                        payload=payload,
                    )
                )
        return hits

    def delete_passage(self, passage_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=[self.point_id(passage_id)],
        )

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.dim:
            raise ValueError(
                f"embedding dimension mismatch: got {len(vector)}, expected {self.dim}"
            )

    def _payload(
        self,
        passage: ArchivalPassage,
        config: ArchivalEmbeddingConfig,
    ) -> dict[str, Any]:
        return {
            "namespace": self._PAYLOAD_NAMESPACE,
            "passage_id": passage.id,
            "archive_id": passage.archive_id,
            "document_id": passage.document_id,
            "chunk_id": passage.chunk_id,
            "source_id": passage.source_id,
            "file_id": passage.file_id,
            "tags": list(passage.tags),
            "passage_updated_at": passage.updated_at.isoformat(),
            "embedding_provider": config.provider,
            "embedding_model": config.model,
            "embedding_dim": config.dim,
            "embedding_config_hash": config.config_hash,
        }
