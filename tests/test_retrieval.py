"""Unit tests for retrieval package."""

from memoryos_lite.retrieval import HybridSearcher, LexicalSearcher
from memoryos_lite.schemas import MemoryPage, PageType


def _page(id: str, title: str, summary: str, facts: list[str] | None = None) -> MemoryPage:
    return MemoryPage(
        id=id,
        session_id="ses_test",
        page_type=PageType.SOURCE_SUMMARY,
        title=title,
        summary=summary,
        facts=facts or [],
        version=1,
    )


class TestLexicalSearcher:
    def test_basic_search(self):
        searcher = LexicalSearcher()
        pages = [
            _page("p1", "Python basics", "Learn Python programming language"),
            _page("p2", "Rust guide", "Systems programming with Rust"),
        ]
        hits = searcher.search(pages, "Python")
        assert len(hits) >= 1
        assert hits[0].page.id == "p1"

    def test_chinese_search(self):
        searcher = LexicalSearcher()
        pages = [
            _page("p1", "数据库设计", "关系型数据库的设计原则"),
            _page("p2", "前端开发", "React组件化开发实践"),
        ]
        hits = searcher.search(pages, "数据库")
        assert len(hits) >= 1
        assert hits[0].page.id == "p1"

    def test_empty_pages(self):
        searcher = LexicalSearcher()
        assert searcher.search([], "query") == []

    def test_no_match(self):
        searcher = LexicalSearcher()
        pages = [_page("p1", "Python", "Learn Python")]
        assert searcher.search(pages, "zzzzunrelated") == []

    def test_facts_are_searchable(self):
        searcher = LexicalSearcher()
        pages = [_page("p1", "Meeting", "Weekly sync", facts=["deadline is Friday"])]
        hits = searcher.search(pages, "deadline")
        assert len(hits) == 1


class TestHybridSearcher:
    def test_lexical_only_fallback(self):
        lexical = LexicalSearcher()
        hybrid = HybridSearcher(lexical=lexical, embedding=None)
        pages = [
            _page("p1", "Python basics", "Learn Python programming"),
            _page("p2", "Rust guide", "Systems programming with Rust"),
        ]
        hits = hybrid.search(pages, "Python")
        assert len(hits) >= 1
        assert hits[0].page.id == "p1"

    def test_empty_pages(self):
        hybrid = HybridSearcher(lexical=LexicalSearcher(), embedding=None)
        assert hybrid.search([], "query") == []
