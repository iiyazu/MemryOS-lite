"""Tests for adaptive RAG pipeline: query rewriter + LLM reranker."""

from memoryos_lite.retrieval.base import SearchHit
from memoryos_lite.retrieval.hybrid import HybridSearcher
from memoryos_lite.retrieval.lexical import LexicalSearcher
from memoryos_lite.retrieval.query_rewriter import QueryRewriter
from memoryos_lite.retrieval.reranker import LLMReranker
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


class TestQueryRewriter:
    def test_passthrough_without_api_key(self):
        rewriter = QueryRewriter(api_key=None)
        assert rewriter.rewrite("hello") == "hello"

    def test_passthrough_preserves_query(self):
        rewriter = QueryRewriter(api_key=None)
        assert rewriter.rewrite("我住在哪里？", profile_context="后端工程师") == "我住在哪里？"


class TestLLMReranker:
    def test_passthrough_without_api_key(self):
        reranker = LLMReranker(api_key=None)
        hits = [
            SearchHit(page=_page("p1", "A", "aaa"), score=0.5, reason="test"),
            SearchHit(page=_page("p2", "B", "bbb"), score=0.3, reason="test"),
        ]
        result = reranker.rerank(hits, "query", top_k=2)
        assert len(result) == 2
        assert result[0].page.id == "p1"

    def test_empty_hits(self):
        reranker = LLMReranker(api_key=None)
        assert reranker.rerank([], "query") == []

    def test_top_k_truncation(self):
        reranker = LLMReranker(api_key=None)
        hits = [
            SearchHit(page=_page(f"p{i}", f"T{i}", f"s{i}"), score=1.0 / i, reason="test")
            for i in range(1, 6)
        ]
        result = reranker.rerank(hits, "query", top_k=3)
        assert len(result) == 3


class TestHybridWithPipeline:
    def test_hybrid_with_no_rewriter_no_reranker(self):
        hybrid = HybridSearcher(lexical=LexicalSearcher(), embedding=None)
        pages = [_page("p1", "Python", "Learn Python programming")]
        hits = hybrid.search(pages, "Python", top_k=5)
        assert len(hits) >= 1

    def test_hybrid_with_passthrough_rewriter(self):
        rewriter = QueryRewriter(api_key=None)
        hybrid = HybridSearcher(lexical=LexicalSearcher(), embedding=None, query_rewriter=rewriter)
        pages = [_page("p1", "Python", "Learn Python programming")]
        hits = hybrid.search(pages, "Python", top_k=5)
        assert len(hits) >= 1

    def test_hybrid_falls_back_when_rewriter_fails(self):
        class FailingRewriter:
            def rewrite(self, query: str, profile_context: str = "") -> str:
                raise RuntimeError("rewriter unavailable")

        hybrid = HybridSearcher(
            lexical=LexicalSearcher(),
            embedding=None,
            query_rewriter=FailingRewriter(),  # type: ignore[arg-type]
        )
        pages = [_page("p1", "Python", "Learn Python programming")]

        hits = hybrid.search(pages, "Python", top_k=5)

        assert len(hits) >= 1
        assert hits[0].page.id == "p1"

    def test_hybrid_with_passthrough_reranker(self):
        reranker = LLMReranker(api_key=None)
        hybrid = HybridSearcher(lexical=LexicalSearcher(), embedding=None, reranker=reranker)
        pages = [
            _page("p1", "Python basics", "Learn Python"),
            _page("p2", "Rust guide", "Systems Rust"),
        ]
        hits = hybrid.search(pages, "Python", top_k=5)
        assert len(hits) >= 1
        assert hits[0].page.id == "p1"
