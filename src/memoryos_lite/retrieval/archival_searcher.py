from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.archival_vector import (
    ArchivalVectorDiagnostic,
    ArchivalVectorIndex,
)
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.v3_contracts import ArchivalPassage, SourceRef, SourceSpan

SearchMode = Literal["text", "vector", "hybrid"]


@dataclass(frozen=True)
class ArchivalPassageHit:
    passage: ArchivalPassage
    score: float
    reason: str
    source: str
    citation: SourceSpan | None = None
    source_refs: list[SourceRef] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class ArchivalPassageReranker(Protocol):
    def rerank(
        self,
        hits: list[ArchivalPassageHit],
        query: str,
        top_k: int,
    ) -> list[ArchivalPassageHit]: ...


class ArchivalPassageSearcher:
    def __init__(
        self,
        *,
        vector_index: ArchivalVectorIndex | None = None,
        passage_loader: Callable[[list[str]], dict[str, ArchivalPassage]] | None = None,
        reranker: ArchivalPassageReranker | None = None,
    ) -> None:
        self.vector_index = vector_index
        self.passage_loader = passage_loader
        self.reranker = reranker
        self.last_diagnostics: list[ArchivalVectorDiagnostic] = []

    def search(
        self,
        passages: list[ArchivalPassage],
        query: str,
        *,
        top_k: int = 5,
        archive_id: str | None = None,
        source_id: str | None = None,
        file_id: str | None = None,
        tags: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        mode: SearchMode = "text",
    ) -> list[ArchivalPassageHit]:
        self.last_diagnostics = []
        candidates = [
            passage
            for passage in passages
            if self._matches_filters(
                passage,
                archive_id=archive_id,
                source_id=source_id,
                file_id=file_id,
                tags=tags,
                created_from=created_from,
                created_to=created_to,
            )
        ]
        lexical_hits = self._lexical(candidates, query, top_k=top_k)
        if mode == "text":
            hits = [
                self._hit(hit.passage, hit.score, hit.reason, "archival_text")
                for hit in lexical_hits
            ]
            return self._rerank_hits(hits, query=query, top_k=top_k)
        if mode == "vector":
            hits = self._vector_or_fallback(
                candidates,
                query,
                lexical_hits=lexical_hits,
                top_k=top_k,
                fallback_source="archival_vector",
            )
            return self._rerank_hits(hits, query=query, top_k=top_k)
        if mode == "hybrid":
            hits = [
                self._hit(
                    hit.passage,
                    hit.score,
                    f"lexical={hit.score:.4f}; vector_unavailable",
                    "archival_hybrid",
                )
                for hit in lexical_hits[:top_k]
            ]
            return self._rerank_hits(hits, query=query, top_k=top_k)
        raise ValueError(f"unsupported archival passage search mode: {mode}")

    def _rerank_hits(
        self,
        hits: list[ArchivalPassageHit],
        *,
        query: str,
        top_k: int,
    ) -> list[ArchivalPassageHit]:
        if self.reranker is None or not hits:
            return hits[:top_k]
        original_by_id = {hit.passage.id: hit for hit in hits}
        try:
            reranked = self.reranker.rerank(hits, query, top_k)
        except Exception as exc:
            self.last_diagnostics.append(
                ArchivalVectorDiagnostic(
                    event_type="archival_reranker_unavailable",
                    reason_code="reranker_error",
                    metadata={"error": str(exc), "candidate_count": len(hits)},
                )
            )
            return hits[:top_k]
        selected: list[ArchivalPassageHit] = []
        seen: set[str] = set()
        for reranked_hit in reranked:
            passage_id = reranked_hit.passage.id
            if passage_id in seen:
                continue
            original_hit = original_by_id.get(passage_id)
            if original_hit is None:
                self.last_diagnostics.append(
                    ArchivalVectorDiagnostic(
                        event_type="archival_reranker_dropped_external_hit",
                        reason_code="reranker_hit_not_in_memoryos_candidates",
                        item_id=passage_id,
                        score=reranked_hit.score,
                        metadata={
                            "source": reranked_hit.source,
                            "reason": reranked_hit.reason,
                        },
                    )
                )
                continue
            selected.append(original_hit)
            seen.add(passage_id)
            if len(selected) >= top_k:
                break
        return selected[:top_k] if selected else hits[:top_k]

    def _vector_or_fallback(
        self,
        candidates: list[ArchivalPassage],
        query: str,
        *,
        lexical_hits: list[ArchivalPassageHit],
        top_k: int,
        fallback_source: str,
    ) -> list[ArchivalPassageHit]:
        if not candidates:
            return []
        if self.vector_index is None:
            self.last_diagnostics.append(
                ArchivalVectorDiagnostic(
                    event_type="archival_vector_unavailable",
                    reason_code="no_vector_index",
                    metadata={"candidate_count": len(candidates)},
                )
            )
            return self._lexical_fallback(
                candidates,
                lexical_hits,
                top_k=top_k,
                source=fallback_source,
                reason_code="no_vector_index",
            )
        result = self.vector_index.search(candidates, query, top_k=top_k)
        self.last_diagnostics.extend(result.diagnostics)
        if not result.hits:
            return self._lexical_fallback(
                candidates,
                lexical_hits,
                top_k=top_k,
                source=fallback_source,
                reason_code="no_vector_hits",
            )
        hit_ids = [hit.passage_id for hit in result.hits]
        rehydrated = self._load_passages(hit_ids, candidates)
        eligible_ids = {passage.id for passage in candidates}
        hits: list[ArchivalPassageHit] = []
        for vector_hit in result.hits:
            passage = rehydrated.get(vector_hit.passage_id)
            if passage is None:
                self.last_diagnostics.append(
                    ArchivalVectorDiagnostic(
                        event_type="archival_stale_vector_hit",
                        reason_code="sqlite_rehydrate_missing",
                        item_id=vector_hit.passage_id,
                        score=vector_hit.score,
                        metadata={"payload": vector_hit.payload},
                    )
                )
                continue
            if passage.id not in eligible_ids:
                self.last_diagnostics.append(
                    ArchivalVectorDiagnostic(
                        event_type="archival_scope_excluded_vector_hit",
                        reason_code="vector_hit_not_eligible",
                        item_id=passage.id,
                        score=vector_hit.score,
                        metadata={"payload": vector_hit.payload},
                    )
                )
                continue
            hits.append(
                self._hit(
                    passage,
                    vector_hit.score,
                    f"qdrant_cosine={vector_hit.score:.4f}",
                    "archival_vector",
                    metadata={
                        "vector_provider": self.vector_index.config.provider,
                        "vector_model": self.vector_index.config.model,
                        "embedding_config_hash": self.vector_index.config.config_hash,
                    },
                )
            )
        if not hits:
            return self._lexical_fallback(
                candidates,
                lexical_hits,
                top_k=top_k,
                source=fallback_source,
                reason_code="no_usable_vector_hits",
            )
        return hits[:top_k]

    def _load_passages(
        self,
        passage_ids: list[str],
        candidates: list[ArchivalPassage],
    ) -> dict[str, ArchivalPassage]:
        if self.passage_loader is not None:
            return self.passage_loader(passage_ids)
        candidates_by_id = {passage.id: passage for passage in candidates}
        return {
            passage_id: candidates_by_id[passage_id]
            for passage_id in passage_ids
            if passage_id in candidates_by_id
        }

    def _lexical_fallback(
        self,
        candidates: list[ArchivalPassage],
        lexical_hits: list[ArchivalPassageHit],
        *,
        top_k: int,
        source: str,
        reason_code: str,
    ) -> list[ArchivalPassageHit]:
        self.last_diagnostics.append(
            ArchivalVectorDiagnostic(
                event_type="archival_lexical_fallback",
                reason_code=reason_code,
                metadata={"candidate_count": len(candidates)},
            )
        )
        fallback = lexical_hits or [self._zero_hit(passage) for passage in candidates[:top_k]]
        return [
            self._hit(
                hit.passage,
                hit.score,
                f"vector_unavailable; lexical_fallback {hit.reason}",
                source,
            )
            for hit in fallback[:top_k]
        ]

    def _lexical(
        self,
        passages: list[ArchivalPassage],
        query: str,
        *,
        top_k: int,
    ) -> list[ArchivalPassageHit]:
        query_tokens = tokenize(query)
        if not passages or not query_tokens:
            return []
        corpus = [tokenize(passage.text) for passage in passages]
        query_set = set(query_tokens)
        matching_indices = [i for i, tokens in enumerate(corpus) if query_set.intersection(tokens)]
        if not matching_indices:
            return []
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(
            ((float(scores[i]), passages[i]) for i in matching_indices),
            key=lambda pair: (pair[0], pair[1].created_at, pair[1].id),
            reverse=True,
        )
        return [
            self._hit(passage, score, f"bm25={score:.4f}", "archival_text")
            for score, passage in ranked[:top_k]
        ]

    def _hit(
        self,
        passage: ArchivalPassage,
        score: float,
        reason: str,
        source: str,
        metadata: dict[str, object] | None = None,
    ) -> ArchivalPassageHit:
        return ArchivalPassageHit(
            passage=passage,
            score=score,
            reason=reason,
            source=source,
            citation=passage.citation,
            source_refs=list(passage.source_refs),
            metadata={
                **passage.metadata,
                "archive_id": passage.archive_id,
                "document_id": passage.document_id,
                "chunk_id": passage.chunk_id,
                "source_id": passage.source_id,
                "file_id": passage.file_id,
                "tags": list(passage.tags),
                "created_at": passage.created_at,
                "updated_at": passage.updated_at,
                **(metadata or {}),
            },
        )

    def _zero_hit(self, passage: ArchivalPassage) -> ArchivalPassageHit:
        return self._hit(passage, 0.0, "no_lexical_match", "archival_text")

    def _matches_filters(
        self,
        passage: ArchivalPassage,
        *,
        archive_id: str | None,
        source_id: str | None,
        file_id: str | None,
        tags: list[str] | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> bool:
        if archive_id is not None and passage.archive_id != archive_id:
            return False
        if source_id is not None and passage.source_id != source_id:
            return False
        if file_id is not None and passage.file_id != file_id:
            return False
        if tags and not set(tags).issubset(set(passage.tags)):
            return False
        if created_from is not None and passage.created_at < created_from:
            return False
        if created_to is not None and passage.created_at > created_to:
            return False
        return True
