"""Embedding provider facade."""

from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.retrieval.providers.openai import OpenAIEmbeddingClient

__all__ = ["DeterministicEmbeddingClient", "OpenAIEmbeddingClient"]
