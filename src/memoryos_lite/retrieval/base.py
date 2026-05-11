"""Retrieval primitives shared across lexical, embedding, and hybrid searchers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from memoryos_lite.schemas import MemoryPage


@dataclass(frozen=True)
class SearchHit:
    """A single retrieval result.

    ``reason`` is a short tag used by the context builder / trace logs to
    explain why a page surfaced (e.g. ``bm25=3.14`` or ``cosine=0.82``).
    ``source`` identifies which retriever produced the hit — ``"hybrid"``
    means the hit came from RRF fusion of multiple retrievers.
    """

    page: MemoryPage
    score: float
    reason: str
    source: str = "lexical"


class Searcher(Protocol):
    """Contract every retriever implements.

    ``pages`` is the candidate set (typically all pages for a session).
    The protocol intentionally mirrors the legacy ``MemorySearcher.search``
    signature so callers elsewhere in the engine stay unchanged.
    """

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]: ...


class EmbeddingClient(Protocol):
    """Minimal interface every embedding provider must satisfy."""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


# ---------- helpers ----------


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


@dataclass
class _RRFEntry:
    page: MemoryPage
    total: float = 0.0
    components: dict[str, float] = field(default_factory=dict)


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[SearchHit]],
    k: int = 60,
    top_k: int = 5,
) -> list[SearchHit]:
    """Fuse multiple ranked hit lists via Reciprocal Rank Fusion.

    Each ranked list is weighted equally. ``k=60`` is the Cormack et al.
    default and is well-defended in the literature. The fused score is the
    sum of ``1 / (k + rank_i)`` across lists; the result is re-sorted and
    truncated to ``top_k``.

    The ``reason`` field on returned hits records the per-source contribution
    so eval traces stay debuggable — e.g. ``rrf lexical=0.0164 embedding=0.0152``.
    """

    aggregated: dict[str, _RRFEntry] = {}
    for source, hits in ranked_lists.items():
        for rank, hit in enumerate(hits):
            score = 1.0 / (k + rank + 1)  # 1-indexed rank
            entry = aggregated.setdefault(hit.page.id, _RRFEntry(page=hit.page))
            entry.total += score
            entry.components[source] = entry.components.get(source, 0.0) + score

    ordered = sorted(aggregated.values(), key=lambda e: e.total, reverse=True)
    fused: list[SearchHit] = []
    for entry in ordered[:top_k]:
        reason = "rrf " + " ".join(
            f"{source}={score:.4f}" for source, score in sorted(entry.components.items())
        )
        fused.append(
            SearchHit(
                page=entry.page,
                score=entry.total,
                reason=reason,
                source="hybrid",
            )
        )
    return fused
