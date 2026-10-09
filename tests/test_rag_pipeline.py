"""Tests for the hybrid lexical + embedding retrieval pipeline."""

from memoryos_lite.retrieval.hybrid import HybridSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.schemas import MemoryPage, PageType


def _page(id: str, title: str, summary: str) -> MemoryPage:
    return MemoryPage(
        id=id,
        session_id="ses_test",
        page_type=PageType.SOURCE_SUMMARY,
        title=title,
        summary=summary,
        facts=[],
        version=1,
    )


class TestHybridWithPipeline:
    def test_hybrid_with_no_rewriter_no_reranker(self):
        hybrid = HybridSearcher(lexical=LexicalSearcher(), embedding=None)
        pages = [_page("p1", "Python", "Learn Python programming")]
        hits = hybrid.search(pages, "Python", top_k=5)
        assert len(hits) >= 1
