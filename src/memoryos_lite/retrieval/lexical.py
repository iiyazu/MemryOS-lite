"""BM25 lexical searcher.

Upgrades the legacy term-overlap scoring to true BM25 via ``rank-bm25``.
Tokenization keeps the original bilingual shape: Latin words + CJK
unigrams + CJK bigrams, so Chinese queries that previously worked
continue to.

The index is rebuilt on every ``search`` call. For the M2 corpus size
(≤ a few hundred pages per session) this is cheap. The design note in
``docs/store-interface.md`` marks caching as an M5 concern.
"""

from __future__ import annotations

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.base import SearchHit
from memoryos_lite.schemas import MemoryPage


def tokenize(text: str) -> list[str]:
    """Bilingual tokenizer: Latin tokens + CJK unigrams + CJK bigrams."""
    normalized = text.replace("/", " ").lower()
    tokens: list[str] = [token for token in normalized.split() if token]
    cjk_chars = [char for char in normalized if "一" <= char <= "鿿"]
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:], strict=False))
    return tokens


def _page_text(page: MemoryPage) -> str:
    parts = [
        page.title,
        page.summary,
        *page.facts,
        *page.decisions,
        *page.open_questions,
    ]
    return " ".join(parts)


class LexicalSearcher:
    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        if not pages:
            return []
        tokenized = [tokenize(_page_text(page)) for page in pages]
        if not any(tokenized):
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        # Only rank pages whose vocabulary actually intersects the query.
        # BM25Okapi returns negative scores on tiny corpora where a term
        # appears in >50% of documents (IDF flips sign), so we can't gate on
        # ``score > 0`` — an intersecting-vocab check is the correct filter.
        query_set = set(query_tokens)
        matching_indices = [i for i, doc in enumerate(tokenized) if query_set.intersection(doc)]
        if not matching_indices:
            return []

        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query_tokens)

        ranked = sorted(
            ((scores[i], pages[i]) for i in matching_indices),
            key=lambda pair: (pair[0], pair[1].confidence, pair[1].created_at),
            reverse=True,
        )
        return [
            SearchHit(page=page, score=float(score), reason=f"bm25={score:.4f}", source="lexical")
            for score, page in ranked[:top_k]
        ]
