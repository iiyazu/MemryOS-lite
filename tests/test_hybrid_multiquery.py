from unittest.mock import MagicMock

from memoryos_lite.retrieval.hybrid import HybridSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.schemas import MemoryPage


def _make_page(page_id: str, title: str) -> MemoryPage:
    return MemoryPage(
        id=page_id,
        session_id="ses_test",
        title=title,
        summary=title,
        facts=[title],
        source_message_ids=[f"msg_{page_id}"],
    )


def test_multiquery_merges_results_from_multiple_queries():
    pages = [
        _make_page("p1", "Alice lives in Shanghai"),
        _make_page("p2", "Alice moved to Beijing recently"),
        _make_page("p3", "Weather forecast for today"),
    ]
    lexical = LexicalSearcher()
    rewriter = MagicMock()
    rewriter.expand.return_value = [
        "Where does Alice live?",
        "Alice current city residence",
        "Alice home location Beijing Shanghai",
    ]
    searcher = HybridSearcher(lexical=lexical, embedding=None, query_rewriter=rewriter)
    results = searcher.search(pages, "Where does Alice live?", top_k=5)
    hit_ids = [h.page.id for h in results]
    assert "p1" in hit_ids or "p2" in hit_ids


def test_no_rewriter_uses_original_query():
    pages = [_make_page("p1", "Alice lives in Shanghai")]
    lexical = LexicalSearcher()
    searcher = HybridSearcher(lexical=lexical, embedding=None)
    results = searcher.search(pages, "Alice Shanghai", top_k=5)
    assert len(results) >= 1
    assert results[0].page.id == "p1"
