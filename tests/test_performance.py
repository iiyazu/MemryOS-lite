"""Tests for M5 performance optimizations."""

from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.schemas import MemoryPage, PageType
from memoryos_lite.tokenizer import TokenEstimator, _count_tokens


def _make_page(id: str, title: str, summary: str, version: int = 1) -> MemoryPage:
    return MemoryPage(
        id=id,
        session_id="ses_test",
        page_type=PageType.SOURCE_SUMMARY,
        title=title,
        summary=summary,
        facts=[],
        version=version,
    )


class TestTokenCache:
    def test_cached_count_matches_uncached(self):
        t = TokenEstimator()
        text = "hello world this is a test"
        first = t.count(text)
        second = t.count(text)
        assert first == second

    def test_lru_cache_is_hit(self):
        _count_tokens.cache_clear()
        text = "repeated text for caching"
        t = TokenEstimator()
        t.count(text)
        t.count(text)
        info = _count_tokens.cache_info()
        assert info.hits >= 1


class TestBM25Cache:
    def test_index_reused_on_same_pages(self):
        searcher = LexicalSearcher()
        pages = [_make_page("p1", "Python guide", "Learn Python programming")]
        searcher.search(pages, "Python")
        bm25_first = searcher._cached_bm25
        searcher.search(pages, "programming")
        assert searcher._cached_bm25 is bm25_first

    def test_index_rebuilt_on_new_page(self):
        searcher = LexicalSearcher()
        pages = [_make_page("p1", "Python guide", "Learn Python programming")]
        searcher.search(pages, "Python")
        bm25_first = searcher._cached_bm25
        pages.append(_make_page("p2", "Rust guide", "Learn Rust programming"))
        searcher.search(pages, "Rust")
        assert searcher._cached_bm25 is not bm25_first

    def test_index_rebuilt_on_version_change(self):
        searcher = LexicalSearcher()
        pages = [_make_page("p1", "Python guide", "Learn Python programming", version=1)]
        searcher.search(pages, "Python")
        bm25_first = searcher._cached_bm25
        pages = [_make_page("p1", "Python guide", "Updated Python content", version=2)]
        searcher.search(pages, "Python")
        assert searcher._cached_bm25 is not bm25_first
