"""Retrieval layer: BM25 lexical + embedding cosine + RRF hybrid fusion."""

from memoryos_lite.retrieval.base import (
    EmbeddingClient,
    Searcher,
    SearchHit,
    cosine_similarity,
    reciprocal_rank_fusion,
)
from memoryos_lite.retrieval.embedding import EmbeddingSearcher
from memoryos_lite.retrieval.hybrid import HybridSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher, tokenize

__all__ = [
    "EmbeddingClient",
    "EmbeddingSearcher",
    "HybridSearcher",
    "LexicalSearcher",
    "SearchHit",
    "Searcher",
    "cosine_similarity",
    "reciprocal_rank_fusion",
    "tokenize",
]
