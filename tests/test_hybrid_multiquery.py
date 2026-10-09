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


def test_no_rewriter_uses_original_query():
    pages = [_make_page("p1", "Alice lives in Shanghai")]
    lexical = LexicalSearcher()
    searcher = HybridSearcher(lexical=lexical, embedding=None)
    results = searcher.search(pages, "Alice Shanghai", top_k=5)
    assert len(results) >= 1
    assert results[0].page.id == "p1"
