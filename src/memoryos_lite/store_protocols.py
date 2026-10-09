from __future__ import annotations

from typing import Protocol, runtime_checkable

from memoryos_lite.schemas import Episode, Message
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalPassage,
    ArchiveEligibilityResult,
    ArchiveEligibilityScope,
)


@runtime_checkable
class ArchiveIngestStore(Protocol):
    def create_archival_ingest_records(
        self,
        *,
        document: ArchivalDocument,
        chunks: list[ArchivalChunk],
        passages: list[ArchivalPassage],
    ) -> tuple[ArchivalDocument, list[ArchivalChunk], list[ArchivalPassage]]: ...


class RecallIndexStore(Protocol):
    def ensure_episodes_for_session(self, session_id: str) -> int: ...

    def list_episodes(self, session_id: str) -> list[Episode]: ...


class PageEmbeddingStore(Protocol):
    def get_page_embeddings(self, page_ids: list[str]) -> dict[str, list[float]]: ...


class ContextComposerStore(RecallIndexStore, Protocol):
    def list_messages(self, session_id: str, limit: int | None = None) -> list[Message]: ...

    def list_archival_passages_for_scope(
        self,
        scope: ArchiveEligibilityScope,
    ) -> ArchiveEligibilityResult: ...
