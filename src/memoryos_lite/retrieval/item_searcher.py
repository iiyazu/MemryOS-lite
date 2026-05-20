"""Item-level hybrid retrieval: BM25 + embedding cosine + RRF fusion over MemoryItems."""

from __future__ import annotations

from dataclasses import dataclass

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.base import EmbeddingClient, cosine_similarity
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.schemas import MemoryItem


@dataclass(frozen=True)
class ItemSearchHit:
    item: MemoryItem
    score: float
    reason: str
    source: str = "item_hybrid"


class ItemSearcher:
    """Standalone item-level searcher. BM25 + embedding cosine fused via RRF."""

    def __init__(
        self,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._embedding_client = embedding_client

    def search(
        self,
        items: list[MemoryItem],
        query: str,
        embeddings: dict[str, list[float]] | None = None,
        top_k: int = 10,
    ) -> list[ItemSearchHit]:
        if not items or not query:
            return []
        bm25_hits = self._search_bm25(items, query, top_k=top_k)
        embedding_hits = self._search_embedding(
            items, query, embeddings=embeddings, top_k=top_k
        )
        if not bm25_hits and not embedding_hits:
            return []
        if not embedding_hits:
            return bm25_hits[:top_k]
        if not bm25_hits:
            return embedding_hits[:top_k]
        return self._rrf_fuse(bm25_hits, embedding_hits, top_k=top_k)

    def _search_bm25(
        self,
        items: list[MemoryItem],
        query: str,
        top_k: int,
    ) -> list[ItemSearchHit]:
        tokenized_items = [tokenize(item.content) for item in items]
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        query_set = set(query_tokens)
        matching_indices = [
            i for i, doc in enumerate(tokenized_items) if query_set.intersection(doc)
        ]
        if not matching_indices:
            return []
        non_empty = [doc for doc in tokenized_items if doc]
        if not non_empty:
            return []
        bm25 = BM25Okapi(tokenized_items)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(
            ((scores[i], items[i]) for i in matching_indices),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [
            ItemSearchHit(
                item=item,
                score=float(score),
                reason=f"item_bm25={score:.4f}",
                source="item_lexical",
            )
            for score, item in ranked[:top_k]
            if score > 0
        ]

    def _search_embedding(
        self,
        items: list[MemoryItem],
        query: str,
        embeddings: dict[str, list[float]] | None = None,
        top_k: int = 10,
    ) -> list[ItemSearchHit]:
        if not self._embedding_client or not embeddings:
            return []
        query_vec = self._embedding_client.embed(query)
        if not query_vec:
            return []
        scored: list[tuple[float, MemoryItem]] = []
        for item in items:
            item_vec = embeddings.get(item.id)
            if not item_vec:
                continue
            score = cosine_similarity(query_vec, item_vec)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            ItemSearchHit(
                item=item,
                score=float(score),
                reason=f"item_cosine={score:.4f}",
                source="item_embedding",
            )
            for score, item in scored[:top_k]
        ]

    def _rrf_fuse(
        self,
        bm25_hits: list[ItemSearchHit],
        embedding_hits: list[ItemSearchHit],
        top_k: int,
        k: int = 60,
    ) -> list[ItemSearchHit]:
        scores: dict[str, tuple[float, MemoryItem, dict[str, float]]] = {}
        for rank, hit in enumerate(bm25_hits):
            rrf_score = 1.0 / (k + rank + 1)
            item_id = hit.item.id
            if item_id not in scores:
                scores[item_id] = (0.0, hit.item, {})
            total, item, components = scores[item_id]
            components["lexical"] = rrf_score
            scores[item_id] = (total + rrf_score, item, components)
        for rank, hit in enumerate(embedding_hits):
            rrf_score = 1.0 / (k + rank + 1)
            item_id = hit.item.id
            if item_id not in scores:
                scores[item_id] = (0.0, hit.item, {})
            total, item, components = scores[item_id]
            components["embedding"] = rrf_score
            scores[item_id] = (total + rrf_score, item, components)
        ordered = sorted(scores.values(), key=lambda e: e[0], reverse=True)
        return [
            ItemSearchHit(
                item=item,
                score=total,
                reason="item_rrf " + " ".join(
                    f"{s}={v:.4f}" for s, v in sorted(comp.items())
                ),
                source="item_hybrid",
            )
            for total, item, comp in ordered[:top_k]
        ]
