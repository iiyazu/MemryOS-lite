"""LLM-based reranker for search results.

Scores each candidate page against the query using an LLM,
incorporating page metadata (confidence, recency) as signals.
Falls back to passthrough when no API key is configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, SecretStr

from memoryos_lite.retrieval.base import SearchHit


class RerankedItem(BaseModel):
    """Structured output for a single reranked item."""

    page_id: str = Field(description="ID of the page being scored")
    relevance_score: int = Field(description="Relevance score 0-10", ge=0, le=10)
    reason: str = Field(description="Brief justification for the score")


class RerankResult(BaseModel):
    """Structured output from the reranker."""

    items: list[RerankedItem] = Field(description="Scored items")


class LLMReranker:
    """Reranks search hits using LLM relevance scoring.

    Considers:
    - Semantic relevance to query
    - Page confidence score
    - Page recency (updated_at)

    Falls back to passthrough (original order) when no LLM available.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = 60.0,
        use_structured: bool = True,
    ) -> None:
        self._llm = None
        self._use_structured = use_structured
        if api_key:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {}
            if base_url:
                kwargs["base_url"] = base_url
            self._llm = ChatOpenAI(
                model=model,
                api_key=SecretStr(api_key),
                temperature=0,
                timeout=timeout,
                **kwargs,
            )

    def rerank(self, hits: list[SearchHit], query: str, top_k: int = 5) -> list[SearchHit]:
        """Rerank hits by LLM-scored relevance. Returns top_k results."""
        if not hits:
            return []
        if self._llm is None:
            return hits[:top_k]

        candidates = []
        for hit in hits:
            page = hit.page
            age_hours = (datetime.now(UTC) - page.updated_at).total_seconds() / 3600
            candidates.append(
                f"- ID: {page.id} | Title: {page.title} | "
                f"Summary: {page.summary[:100]} | "
                f"Confidence: {page.confidence:.0%} | "
                f"Age: {age_hours:.0f}h"
            )

        system = (
            "You are a relevance judge for a memory retrieval system. "
            "Score each candidate page's relevance to the query (0-10). "
            "Consider: semantic match, page confidence, and recency. "
            "Higher confidence and more recent pages get slight bonus."
        )
        user_msg = f"Query: {query}\n\nCandidates:\n" + "\n".join(candidates)

        try:
            if self._use_structured:
                structured = self._llm.with_structured_output(RerankResult)
                result = structured.invoke(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ]
                )
            else:
                import json as _json

                system += (
                    "\n\nRespond with ONLY a JSON object: "
                    '{"items": [{"page_id": "...", "relevance_score": 0-10, "reason": "..."}]}'
                )
                raw = self._llm.invoke(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ]
                )
                content = raw.content
                if not isinstance(content, str):
                    return hits[:top_k]
                data = _json.loads(content)
                result = RerankResult(**data)
        except Exception:
            return hits[:top_k]

        if not isinstance(result, RerankResult):
            return hits[:top_k]

        score_map = {item.page_id: item.relevance_score for item in result.items}
        scored = [(hit, score_map.get(hit.page.id, 5)) for hit in hits]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [hit for hit, _ in scored[:top_k]]
