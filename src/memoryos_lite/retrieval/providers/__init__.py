"""Embedding provider facade."""

from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient, FakePageDraftClient

__all__ = [
    "DeterministicEmbeddingClient",
    "FakePageDraftClient",
]
