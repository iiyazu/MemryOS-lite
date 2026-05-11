"""OpenAI-compatible embedding provider."""

from __future__ import annotations

from typing import Any

from memoryos_lite.config import Settings


class OpenAIEmbeddingClient:
    """Thin wrapper around ``langchain_openai.OpenAIEmbeddings``.

    Instantiated lazily from ``Settings``; raises ``ValueError`` if
    ``OPENAI_API_KEY`` is missing. Uses ``text-embedding-3-small`` by default
    (1536 dims, matching the ``vector(1536)`` column in ``memory_pages``).
    """

    DIM = 1536

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIEmbeddingClient")
        # Import lazily to avoid paying the langchain_openai import cost
        # when tests / offline use only the fake client.
        from langchain_openai import OpenAIEmbeddings
        from pydantic import SecretStr

        kwargs: dict[str, Any] = {
            "model": settings.memoryos_embedding_model,
            "api_key": SecretStr(settings.openai_api_key),
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAIEmbeddings(**kwargs)

    @property
    def dim(self) -> int:
        return self.DIM

    def embed(self, text: str) -> list[float]:
        return self.client.embed_query(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self.client.embed_documents(texts)
