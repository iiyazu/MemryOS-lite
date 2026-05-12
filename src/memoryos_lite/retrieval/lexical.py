"""BM25 lexical searcher with corpus caching (M5).

Index is rebuilt only when the page set changes (detected via page ID + version fingerprint).
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
    def __init__(self) -> None:
        self._cache_key: tuple[tuple[str, int], ...] | None = None
        self._cached_tokenized: list[list[str]] = []
        self._cached_bm25: BM25Okapi | None = None

    def _corpus_key(self, pages: list[MemoryPage]) -> tuple[tuple[str, int], ...]:
        return tuple((p.id, p.version) for p in pages)

    def _get_index(self, pages: list[MemoryPage]) -> tuple[list[list[str]], BM25Okapi | None]:
        key = self._corpus_key(pages)
        if key == self._cache_key and self._cached_bm25 is not None:
            return self._cached_tokenized, self._cached_bm25
        tokenized = [tokenize(_page_text(page)) for page in pages]
        bm25 = BM25Okapi(tokenized) if any(tokenized) else None
        self._cache_key = key
        self._cached_tokenized = tokenized
        self._cached_bm25 = bm25
        return tokenized, bm25

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        if not pages:
            return []
        tokenized, bm25 = self._get_index(pages)
        if bm25 is None:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        query_set = set(query_tokens)
        matching_indices = [i for i, doc in enumerate(tokenized) if query_set.intersection(doc)]
        if not matching_indices:
            return []

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
