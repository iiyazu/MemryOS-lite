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
    qdrant_import_error = exc

    class QdrantEmbeddingStore:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ImportError(
                "QdrantEmbeddingStore requires the optional qdrant provider"
            ) from qdrant_import_error


try:
    from memoryos_lite.retrieval.providers.qdrant_archival import (
        QdrantArchivalPassageStore,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "memoryos_lite.retrieval.providers.qdrant_archival",
        "qdrant_client",
    }:
        raise
    qdrant_archival_import_error = exc

    class QdrantArchivalPassageStore:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ImportError(
                "QdrantArchivalPassageStore requires the optional qdrant provider"
            ) from qdrant_archival_import_error


__all__ = [
    "DeterministicEmbeddingClient",
    "FakePageDraftClient",
    "OpenAIEmbeddingClient",
    "QdrantArchivalPassageStore",
    "QdrantEmbeddingStore",
]
