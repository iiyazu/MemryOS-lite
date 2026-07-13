from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Literal, Protocol, runtime_checkable

from sqlalchemy.orm import Session as DbSession

from memoryos_lite.schemas import Episode, Message
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalMemory,
    ArchivalPassage,
    ArchiveEligibilityResult,
    ArchiveEligibilityScope,
    ContextPolicyCandidate,
    ContextPolicyCandidateStatus,
    CoreMemoryBlock,
    PromotionCandidate,
    PromotionStatus,
    SourceRef,
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


class CoreMemoryStore(Protocol):
    def create_core_memory_block(
        self,
        block: CoreMemoryBlock,
        *,
        actor: str = "system",
        reason: str = "core memory block created",
    ) -> CoreMemoryBlock: ...

    def get_core_memory_block(
        self,
        block_id: str,
        include_deleted: bool = False,
    ) -> CoreMemoryBlock | None: ...

    def list_core_memory_blocks(
        self,
        include_deleted: bool = False,
    ) -> list[CoreMemoryBlock]: ...

    def update_core_memory_block(
        self,
        block: CoreMemoryBlock,
        *,
        actor: str | None = None,
        reason: str | None = None,
        source_refs: list[SourceRef] | None = None,
        operation: Literal["update", "replace"] = "update",
    ) -> CoreMemoryBlock | None: ...

    def delete_core_memory_block(
        self,
        block_id: str,
        source_refs: list[SourceRef],
        actor: str,
        reason: str,
    ) -> CoreMemoryBlock | None: ...


class MemoryLifecycleStore(Protocol):
    def add_archival_memory(
        self,
        memory: ArchivalMemory,
        *,
        actor: str,
        reason: str,
    ) -> ArchivalMemory: ...

    def create_promotion_candidate(
        self,
        candidate: PromotionCandidate,
    ) -> PromotionCandidate: ...

    def update_promotion_candidate_status(
        self,
        candidate_id: str,
        *,
        status: PromotionStatus,
        metadata: dict[str, Any] | None = None,
    ) -> PromotionCandidate | None: ...


@runtime_checkable
class PromotionMaintenanceStore(CoreMemoryStore, MemoryLifecycleStore, Protocol):
    def db(self) -> AbstractContextManager[DbSession]: ...

    def get_promotion_candidate(
        self,
        candidate_id: str,
    ) -> PromotionCandidate | None: ...


class RecallIndexStore(Protocol):
    def ensure_episodes_for_session(self, session_id: str) -> int: ...

    def list_episodes(self, session_id: str) -> list[Episode]: ...

    def session_memory_watermark(self, session_id: str) -> str: ...


class PageEmbeddingStore(Protocol):
    def get_page_embeddings(self, page_ids: list[str]) -> dict[str, list[float]]: ...


class ContextComposerStore(RecallIndexStore, Protocol):
    def list_messages(self, session_id: str, limit: int | None = None) -> list[Message]: ...

    def list_core_memory_blocks(
        self,
        include_deleted: bool = False,
    ) -> list[CoreMemoryBlock]: ...

    def list_archival_passages_for_scope(
        self,
        scope: ArchiveEligibilityScope,
    ) -> ArchiveEligibilityResult: ...

    def list_context_policy_candidates(
        self,
        *,
        status: ContextPolicyCandidateStatus | None = None,
        session_id: str | None = None,
        feedback_type: str | None = None,
    ) -> list[ContextPolicyCandidate]: ...
