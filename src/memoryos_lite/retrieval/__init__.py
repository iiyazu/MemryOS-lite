"""Retrieval layer: BM25 lexical + embedding cosine + RRF hybrid fusion + LLM rewrite/rerank."""

from memoryos_lite.retrieval.archival_searcher import (
    ArchivalPassageHit,
    ArchivalPassageSearcher,
)
from memoryos_lite.retrieval.base import (
    EmbeddingClient,
    Searcher,
    SearchHit,
    cosine_similarity,
    reciprocal_rank_fusion,
)
from memoryos_lite.retrieval.embedding import EmbeddingSearcher
from memoryos_lite.retrieval.episode_searcher import (
    EpisodeHit,
    EpisodeSearcher,
    RecallMemorySearcher,
)
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

    class ItemSearchHit:  # type: ignore[no-redef]
        pass

    class ItemSearcher:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def search(self, *args: object, **kwargs: object) -> list[ItemSearchHit]:
            return []

__all__ = [
    "EmbeddingClient",
    "EmbeddingSearcher",
    "ArchivalPassageHit",
    "ArchivalPassageSearcher",
    "EpisodeHit",
    "EpisodeSearcher",
    "HybridSearcher",
    "ItemSearchHit",
    "ItemSearcher",
    "LLMReranker",
    "LexicalSearcher",
    "QueryAnalysis",
    "QueryAnalyzer",
    "QueryKind",
    "QueryRewriter",
    "SearchHit",
    "Searcher",
    "RecallMemorySearcher",
    "cosine_similarity",
    "reciprocal_rank_fusion",
    "tokenize",
]
