from unittest.mock import MagicMock, patch

from memoryos_lite.retrieval.query_rewriter import ExpandedQueries, QueryRewriter


def test_expand_returns_multiple_queries_with_llm():
    rewriter = QueryRewriter(
        model="deepseek-v4-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    mock_result = ExpandedQueries(
        variants=["What is Alice's home city?", "Where does Alice live now?"]
    )
    with patch.object(rewriter, "_llm") as mock_llm:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_result
        mock_llm.with_structured_output.return_value = mock_structured
        result = rewriter.expand("Where does Alice live?")

    assert len(result) >= 2
    assert "Where does Alice live?" in result


def test_expand_without_llm_returns_original_only():
    rewriter = QueryRewriter()
    result = rewriter.expand("Where does Alice live?")
    assert result == ["Where does Alice live?"]
