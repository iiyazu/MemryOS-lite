"""Embedding provider facade."""

from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient, FakePageDraftClient
from memoryos_lite.retrieval.providers.openai import OpenAIEmbeddingClient

try:
    from memoryos_lite.retrieval.providers.qdrant import QdrantEmbeddingStore
except ModuleNotFoundError as exc:
    if exc.name not in {
        "memoryos_lite.retrieval.providers.qdrant",
        "qdrant_client",
    }:
        raise

__all__ = [
    "DeterministicEmbeddingClient",
    "FakePageDraftClient",
    "OpenAIEmbeddingClient",
]

if "QdrantEmbeddingStore" in globals():
    __all__.append("QdrantEmbeddingStore")
