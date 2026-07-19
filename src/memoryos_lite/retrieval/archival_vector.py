from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Protocol

from memoryos_lite.retrieval.base import EmbeddingClient
from memoryos_lite.v3_contracts import ArchivalPassage


@dataclass(frozen=True)
class ArchivalEmbeddingConfig:
    provider: str
    model: str
    dim: int
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def config_hash(self) -> str:
        payload = {
            "provider": self.provider,
            "model": self.model,
            "dim": self.dim,
            "extra": dict(sorted(self.extra.items())),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ArchivalVectorHit:
    passage_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchivalVectorDiagnostic:
    event_type: str
    reason_code: str
    item_id: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchivalVectorSearchResult:
    hits: list[ArchivalVectorHit] = field(default_factory=list)
    diagnostics: list[ArchivalVectorDiagnostic] = field(default_factory=list)


class ArchivalVectorStore(Protocol):
    def upsert_passage(
        self,
        passage: ArchivalPassage,
        vector: list[float],
        config: ArchivalEmbeddingConfig,
    ) -> None: ...

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        passage_ids: list[str] | None,
        config: ArchivalEmbeddingConfig,
    ) -> list[ArchivalVectorHit]: ...


class LocalArchivalVectorStore:
    """Bounded process-local vector cache for offline archival recall.

    The cache contains vectors and opaque passage identifiers only. Passage text,
    source references, and authority remain in the durable archive store and are
    re-proved by the caller after retrieval.
    """

    def __init__(self, *, dim: int, max_vectors: int = 20_000) -> None:
        if dim <= 0 or max_vectors <= 0:
            raise ValueError("local archival vector configuration invalid")
        self.dim = dim
        self.max_vectors = max_vectors
        self._vectors: OrderedDict[tuple[str, str], tuple[tuple[float, ...], str]] = OrderedDict()

    def begin_index(
        self,
        *,
        config: ArchivalEmbeddingConfig,
        passage_ids: list[str],
    ) -> None:
        for key in tuple(self._vectors):
            _passage_id, config_hash = key
            if config_hash != config.config_hash:
                self._vectors.pop(key, None)

    def needs_index(
        self,
        passage: ArchivalPassage,
        config: ArchivalEmbeddingConfig,
    ) -> bool:
        key = (passage.id, config.config_hash)
        cached = self._vectors.get(key)
        if cached is None:
            return True
        _vector, content_hash = cached
        current_hash = hashlib.sha256(passage.text.encode("utf-8")).hexdigest()
        if content_hash != current_hash:
            return True
        self._vectors.move_to_end(key)
        return False

    def upsert_passage(
        self,
        passage: ArchivalPassage,
        vector: list[float],
        config: ArchivalEmbeddingConfig,
    ) -> None:
        values = self._validated_vector(vector)
        key = (passage.id, config.config_hash)
        self._vectors[key] = (
            values,
            hashlib.sha256(passage.text.encode("utf-8")).hexdigest(),
        )
        self._vectors.move_to_end(key)
        while len(self._vectors) > self.max_vectors:
            self._vectors.popitem(last=False)

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
        query = self._validated_vector(vector)
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm == 0:
            return []
        eligible = None if passage_ids is None else set(passage_ids)
        ranked: list[tuple[float, str]] = []
        for (passage_id, config_hash), (candidate, _content_hash) in self._vectors.items():
            if config_hash != config.config_hash or (
                eligible is not None and passage_id not in eligible
            ):
                continue
            candidate_norm = math.sqrt(sum(value * value for value in candidate))
            if candidate_norm == 0:
                continue
            score = sum(left * right for left, right in zip(query, candidate, strict=True)) / (
                query_norm * candidate_norm
            )
            ranked.append((score, passage_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            ArchivalVectorHit(
                passage_id=passage_id,
                score=score,
                payload={
                    "backend": "local",
                    "embedding_config_hash": config.config_hash,
                },
            )
            for score, passage_id in ranked[:top_k]
        ]

    def _validated_vector(self, vector: list[float]) -> tuple[float, ...]:
        if len(vector) != self.dim or any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding dimension mismatch")
        return tuple(float(value) for value in vector)


class ArchivalVectorIndex:
    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        vector_store: ArchivalVectorStore,
        config: ArchivalEmbeddingConfig,
    ) -> None:
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        self.config = config

    def search(
        self,
        passages: list[ArchivalPassage],
        query: str,
        *,
        top_k: int,
    ) -> ArchivalVectorSearchResult:
        if not passages or not query.strip() or top_k <= 0:
            return ArchivalVectorSearchResult()
        diagnostics: list[ArchivalVectorDiagnostic] = []
        passage_ids = [passage.id for passage in passages]
        index_diagnostics = self.index_passages(passages)
        diagnostics.extend(index_diagnostics)
        if any(diagnostic.reason_code == "vector_index_error" for diagnostic in index_diagnostics):
            return ArchivalVectorSearchResult(diagnostics=diagnostics)
        try:
            query_vector = self.embedding_client.embed(query)
            if not query_vector:
                diagnostics.append(
                    ArchivalVectorDiagnostic(
                        event_type="archival_vector_unavailable",
                        reason_code="empty_query_embedding",
                        metadata={"candidate_count": len(passages)},
                    )
                )
                return ArchivalVectorSearchResult(diagnostics=diagnostics)
            hits = self.vector_store.query(
                query_vector,
                top_k=top_k,
                passage_ids=passage_ids,
                config=self.config,
            )
        except Exception as exc:
            diagnostics.append(
                ArchivalVectorDiagnostic(
                    event_type="archival_vector_unavailable",
                    reason_code="vector_index_error",
                    metadata={
                        "error": str(exc),
                        "candidate_count": len(passages),
                    },
                )
            )
            return ArchivalVectorSearchResult(diagnostics=diagnostics)
        return ArchivalVectorSearchResult(hits=hits, diagnostics=diagnostics)

    def index_passages(
        self,
        passages: list[ArchivalPassage],
    ) -> list[ArchivalVectorDiagnostic]:
        diagnostics: list[ArchivalVectorDiagnostic] = []
        try:
            begin_index = getattr(self.vector_store, "begin_index", None)
            if callable(begin_index):
                begin_index(
                    config=self.config,
                    passage_ids=[passage.id for passage in passages],
                )
            for passage in passages:
                needs_index = getattr(self.vector_store, "needs_index", None)
                if callable(needs_index) and not needs_index(passage, self.config):
                    continue
                vector = self.embedding_client.embed(passage.text)
                if not vector:
                    diagnostics.append(
                        ArchivalVectorDiagnostic(
                            event_type="archival_vector_unavailable",
                            reason_code="empty_passage_embedding",
                            item_id=passage.id,
                        )
                    )
                    continue
                self.vector_store.upsert_passage(passage, vector, self.config)
        except Exception as exc:
            diagnostics.append(
                ArchivalVectorDiagnostic(
                    event_type="archival_vector_unavailable",
                    reason_code="vector_index_error",
                    metadata={
                        "error": str(exc),
                        "candidate_count": len(passages),
                    },
                )
            )
        return diagnostics
