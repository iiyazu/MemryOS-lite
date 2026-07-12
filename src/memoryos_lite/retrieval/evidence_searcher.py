from __future__ import annotations

from dataclasses import dataclass

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.evidence_representer import EvidenceCandidate
from memoryos_lite.retrieval.lexical import tokenize


@dataclass(frozen=True)
class EvidenceHit:
    message_id: str
    original_text: str
    index_text: str
    score: float
    source: str  # "evidence_bm25"


class EvidenceSearcher:
    def search(
        self, candidates: list[EvidenceCandidate], query: str, top_k: int = 10
    ) -> list[EvidenceHit]:
        if not candidates or not query.strip():
            return []
        seen: dict[str, EvidenceCandidate] = {}
        for c in candidates:
            if c.message_id not in seen:
                seen[c.message_id] = c
        deduped = list(seen.values())
        return self._bm25(deduped, query, top_k)

    def _bm25(
        self, candidates: list[EvidenceCandidate], query: str, top_k: int
    ) -> list[EvidenceHit]:
        tokenized = [tokenize(c.index_text) for c in candidates]
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        query_set = set(query_tokens)
        matching = [i for i, doc in enumerate(tokenized) if query_set & set(doc)]
        if not matching:
            return []
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(
            ((scores[i], candidates[i]) for i in matching), key=lambda p: p[0], reverse=True
        )
        return [
            EvidenceHit(
                message_id=c.message_id,
                original_text=c.original_text,
                index_text=c.index_text,
                score=float(s),
                source="evidence_bm25",
            )
            for s, c in ranked[:top_k]
        ]
