"""Retrieval layer: BM25 lexical + embedding cosine + RRF hybrid fusion + LLM rewrite/rerank."""

from memoryos_lite.retrieval.base import (
    EmbeddingClient,
    Searcher,
    SearchHit,
    cosine_similarity,
    reciprocal_rank_fusion,
)
from memoryos_lite.retrieval.embedding import EmbeddingSearcher
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, EpisodeSearcher
from memoryos_lite.retrieval.hybrid import HybridSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher, tokenize
from memoryos_lite.retrieval.query_analyzer import (
    QueryAnalysis,
    QueryAnalyzer,
    QueryKind,
)
from memoryos_lite.retrieval.query_rewriter import QueryRewriter
from memoryos_lite.retrieval.reranker import LLMReranker

try:
    from memoryos_lite.retrieval.item_searcher import ItemSearcher, ItemSearchHit
except ModuleNotFoundError as exc:
    if exc.name != "memoryos_lite.retrieval.item_searcher":
        raise

__all__ = [
    "EmbeddingClient",
    "EmbeddingSearcher",
    "EpisodeHit",
    "EpisodeSearcher",
    "HybridSearcher",
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
