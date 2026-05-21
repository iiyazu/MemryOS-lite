from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

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


class ArchivalPassageSearcher:
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
            return [
                self._hit(hit.passage, hit.score, hit.reason, "archival_text")
                for hit in lexical_hits
            ]
        if mode == "vector":
            fallback = lexical_hits or [self._zero_hit(passage) for passage in candidates[:top_k]]
            return [
                self._hit(
                    hit.passage,
                    hit.score,
                    f"vector_unavailable; lexical_fallback {hit.reason}",
                    "archival_vector",
                )
                for hit in fallback[:top_k]
            ]
        if mode == "hybrid":
            return [
                self._hit(
                    hit.passage,
                    hit.score,
                    f"lexical={hit.score:.4f}; vector_unavailable",
                    "archival_hybrid",
                )
                for hit in lexical_hits[:top_k]
            ]
        raise ValueError(f"unsupported archival passage search mode: {mode}")

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
    ) -> ArchivalPassageHit:
        return ArchivalPassageHit(
            passage=passage,
            score=score,
            reason=reason,
            source=source,
            citation=passage.citation,
            source_refs=list(passage.source_refs),
            metadata={
                "archive_id": passage.archive_id,
                "document_id": passage.document_id,
                "chunk_id": passage.chunk_id,
                "source_id": passage.source_id,
                "file_id": passage.file_id,
                "tags": list(passage.tags),
                "created_at": passage.created_at,
                "updated_at": passage.updated_at,
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
