"""LLM-based query rewriting with memory-aware context.

Rewrites raw user queries to improve retrieval quality by:
- Expanding abbreviations and implicit references
- Incorporating user profile context for disambiguation
- Generating retrieval-optimized query formulations

Falls back to the raw query when no API key is configured.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RewrittenQuery(BaseModel):
    """Structured output from the query rewriter."""

    rewritten: str = Field(description="Rewritten query optimized for retrieval")
    reasoning: str = Field(description="Brief explanation of changes made")


class QueryRewriter:
    """Rewrites queries using LLM with optional profile context.

    When no LLM client is available, acts as a passthrough.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._llm = None
        if api_key:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, str] = {}
            if base_url:
                kwargs["base_url"] = base_url
            self._llm = ChatOpenAI(model=model, api_key=api_key, temperature=0, **kwargs)  # type: ignore[arg-type]

    def rewrite(self, query: str, profile_context: str = "") -> str:
        """Rewrite query for better retrieval. Returns raw query if no LLM."""
        if self._llm is None:
            return query

        system = (
            "You are a query rewriter for a memory retrieval system. "
            "Rewrite the user's query to improve retrieval recall. "
            "Expand implicit references, add relevant keywords, "
            "but preserve the original intent. Keep it concise."
        )
        if profile_context:
            system += f"\n\nUser profile context:\n{profile_context}"

        structured = self._llm.with_structured_output(RewrittenQuery)
        result = structured.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Original query: {query}"},
            ]
        )
        if isinstance(result, RewrittenQuery):
            return result.rewritten
        return query
