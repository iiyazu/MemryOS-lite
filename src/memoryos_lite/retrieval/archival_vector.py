from __future__ import annotations

import hashlib
import json
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
            for passage in passages:
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
