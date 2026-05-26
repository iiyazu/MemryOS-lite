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


class ExpandedQueries(BaseModel):
    """Structured output from multi-query expansion."""

    variants: list[str] = Field(description="2-3 alternative phrasings of the query")


class QueryRewriter:
    """Rewrites queries using LLM with optional profile context.

    When no LLM client is available, acts as a passthrough.
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

            kwargs: dict[str, str] = {}
            if base_url:
                kwargs["base_url"] = base_url
            self._llm = ChatOpenAI(
                model=model,
                api_key=api_key,
                temperature=0,
                timeout=timeout,
                **kwargs,
            )  # type: ignore[arg-type]

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

        if self._use_structured:
            structured = self._llm.with_structured_output(RewrittenQuery)
            result = structured.invoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Original query: {query}"},
                ]
            )
            if isinstance(result, RewrittenQuery):
                return result.rewritten
        else:
            import json as _json
            system += '\n\nRespond with ONLY a JSON object: {"rewritten": "...", "reasoning": "..."}'
            result = self._llm.invoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Original query: {query}"},
                ]
            )
            try:
                data = _json.loads(result.content)
                if isinstance(data, dict) and "rewritten" in data:
                    return data["rewritten"]
            except (ValueError, AttributeError):
                pass
        return query

    def expand(self, query: str, profile_context: str = "") -> list[str]:
        """Generate alternative query phrasings for multi-path retrieval."""
        if self._llm is None:
            return [query]

        system = (
            "Generate 2-3 alternative phrasings of this query for memory retrieval. "
            "Each variant should approach the question from a different angle. "
            "Include keywords that might appear in the answer, not just the question. "
            "Return concise query variants."
        )
        if profile_context:
            system += f"\n\nUser profile context:\n{profile_context}"

        try:
            if self._use_structured:
                structured = self._llm.with_structured_output(ExpandedQueries)
                result = structured.invoke(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Original query: {query}"},
                    ]
                )
            else:
                import json as _json
                system += '\n\nRespond with ONLY a JSON object: {"variants": ["query1", "query2", "query3"]}'
                result = self._llm.invoke(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Original query: {query}"},
                    ]
                )
                data = _json.loads(result.content)
                result = ExpandedQueries(**data)
        except Exception:
            return [query]

        if isinstance(result, ExpandedQueries) and result.variants:
            variants: list[str] = [query]
            for variant in result.variants:
                if variant and variant not in variants:
                    variants.append(variant)
            return variants[:4]
        return [query]
