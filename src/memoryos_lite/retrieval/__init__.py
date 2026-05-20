"""Retrieval layer: BM25 lexical + embedding cosine + RRF hybrid fusion + LLM rewrite/rerank."""

from memoryos_lite.retrieval.base import (
    EmbeddingClient,
    Searcher,
    SearchHit,
    cosine_similarity,
    reciprocal_rank_fusion,
)
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, EpisodeSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher, tokenize
from memoryos_lite.retrieval.query_analyzer import (
    QueryAnalysis,
    QueryAnalyzer,
    QueryKind,
)
from memoryos_lite.retrieval.query_rewriter import QueryRewriter
from memoryos_lite.retrieval.reranker import LLMReranker

_OPTIONAL_QDRANT_MODULES = {
    "memoryos_lite.retrieval.providers.qdrant",
    "qdrant_client",
}

try:
    from memoryos_lite.retrieval.embedding import EmbeddingSearcher
except ModuleNotFoundError as exc:
    if exc.name not in _OPTIONAL_QDRANT_MODULES:
        raise

try:
    from memoryos_lite.retrieval.hybrid import HybridSearcher
except ModuleNotFoundError as exc:
    if exc.name not in _OPTIONAL_QDRANT_MODULES:
        raise

try:
    from memoryos_lite.retrieval.item_searcher import ItemSearcher, ItemSearchHit
except ModuleNotFoundError as exc:
    if exc.name != "memoryos_lite.retrieval.item_searcher":
        raise

__all__ = [
    "EmbeddingClient",
    "EpisodeHit",
    "EpisodeSearcher",
    "LLMReranker",
    "LexicalSearcher",
    "QueryAnalysis",
    "QueryAnalyzer",
    "QueryKind",
    "QueryRewriter",
    "SearchHit",
    "Searcher",
    "cosine_similarity",
    "reciprocal_rank_fusion",
    "tokenize",
]

if "ItemSearcher" in globals():
    __all__.extend(["ItemSearchHit", "ItemSearcher"])

if "EmbeddingSearcher" in globals():
    __all__.append("EmbeddingSearcher")

if "HybridSearcher" in globals():
    __all__.append("HybridSearcher")
