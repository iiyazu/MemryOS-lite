"""Embedding provider facade."""

from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient, FakePageDraftClient
from memoryos_lite.retrieval.providers.openai import OpenAIEmbeddingClient
from memoryos_lite.retrieval.providers.qdrant import QdrantEmbeddingStore

__all__ = [
    "DeterministicEmbeddingClient",
    "FakePageDraftClient",
    "OpenAIEmbeddingClient",
    "QdrantEmbeddingStore",
]
