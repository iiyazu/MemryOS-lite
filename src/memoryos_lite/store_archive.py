"""Archive, source-proof, and governed-memory persistence behavior.

This module owns the archive-facing slice of ``MemoryStore``.  The concrete
composition root supplies ``db()`` and the SQLAlchemy session lifecycle.
"""

import json
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, overload

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from memoryos_lite.schemas import Message, utc_now
from memoryos_lite.store_models import (
    ArchivalChunkRecord,
    ArchivalDocumentRecord,
    ArchivalMemoryHistoryRecord,
    ArchivalMemoryRecord,
    ArchivalPassagePage,
    ArchivalPassageRecord,
    ArchiveAttachmentRecord,
    ContextPolicyCandidateRecord,
    CoreMemoryBlockRecord,
    CoreMemoryHistoryRecord,
    PromotionCandidateRecord,
)
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalMemory,
    ArchivalPassage,
    ArchiveAttachment,
    ArchiveEligibilityResult,
    ArchiveEligibilityScope,
    ContextPolicyCandidate,
    ContextPolicyCandidateStatus,
    CoreMemoryBlock,
    IdentityScope,
    MemoryHistoryEvent,
    PromotionCandidate,
    PromotionStatus,
    SourceRef,
    SourceSpan,
    SourceType,
    ensure_persisted_identity_scope,
)


class ArchiveStoreMixin:
    """Persistence operations for core and archival memory."""

    if TYPE_CHECKING:

        def db(self) -> AbstractContextManager[DbSession]: ...

    @staticmethod
    def _dump_source_refs(source_refs: list[SourceRef]) -> str:
        return json.dumps([ref.model_dump(mode="json") for ref in source_refs], ensure_ascii=False)

    @staticmethod
    def _load_source_refs(source_refs_json: str) -> list[SourceRef]:
        return [SourceRef.model_validate(ref) for ref in json.loads(source_refs_json)]

    @staticmethod
    def _dump_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @staticmethod
    @overload
    def _aware(value: datetime) -> datetime: ...

    @staticmethod
    @overload
    def _aware(value: None) -> None: ...

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)

    @staticmethod
    def _require_source_refs(source_refs: list[SourceRef], write_name: str) -> None:
        if not source_refs:
            raise ValueError(f"{write_name} requires source_refs")

    @staticmethod
    def _document_from_record(record: ArchivalDocumentRecord) -> ArchivalDocument:
        return ArchivalDocument(
            id=record.id,
            archive_id=record.archive_id,
            title=record.title,
            text=record.text,
            version=record.version,
            source_id=record.source_id,
            file_id=record.file_id,
            tags=json.loads(record.tags_json),
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            producer=record.producer,
            legacy_page_id=record.legacy_page_id,
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
        )

    @staticmethod
    def _chunk_from_record(record: ArchivalChunkRecord) -> ArchivalChunk:
        return ArchivalChunk(
            id=record.id,
            document_id=record.document_id,
            archive_id=record.archive_id,
            text=record.text,
            start=record.start,
            end=record.end,
            tags=json.loads(record.tags_json),
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
        )

    @staticmethod
    def _passage_from_record(record: ArchivalPassageRecord) -> ArchivalPassage:
        citation = None
        if record.citation_start is not None and record.citation_end is not None:
            citation = SourceSpan(start=record.citation_start, end=record.citation_end)
        scope = None
        if record.scope_json:
            scope = IdentityScope.model_validate(json.loads(record.scope_json))
        return ArchivalPassage(
            id=record.id,
            document_id=record.document_id,
            chunk_id=record.chunk_id,
            archive_id=record.archive_id,
            text=record.text,
            citation=citation,
            source_id=record.source_id,
            file_id=record.file_id,
            scope=scope,
            tags=json.loads(record.tags_json),
            score=record.score,
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            legacy_item_id=record.legacy_item_id,
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
        )

    @staticmethod
    def _archival_memory_from_record(record: ArchivalMemoryRecord) -> ArchivalMemory:
        scope = None
        if record.identity_scope_json:
            scope = IdentityScope.model_validate(json.loads(record.identity_scope_json))
        return ArchivalMemory(
            id=record.id,
            archive_id=record.archive_id,
            memory_type=record.memory_type,  # type: ignore[arg-type]
            content=record.content,
            identity_scope=scope,
            source_id=record.source_id,
            file_id=record.file_id,
            tags=json.loads(record.tags_json),
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            history=[
                MemoryHistoryEvent.model_validate(event)
                for event in json.loads(record.history_json)
            ],
            entity_links=json.loads(record.entity_links_json),
            legacy_item_id=record.legacy_item_id,
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
            deleted_at=ArchiveStoreMixin._aware(record.deleted_at),
        )

    @staticmethod
    def _archive_attachment_from_record(record: ArchiveAttachmentRecord) -> ArchiveAttachment:
        return ArchiveAttachment(
            id=record.id,
            archive_id=record.archive_id,
            scope_type=record.scope_type,  # type: ignore[arg-type]
            scope_id=record.scope_id,
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
        )

    @staticmethod
    def _promotion_candidate_from_record(
        record: PromotionCandidateRecord,
    ) -> PromotionCandidate:
        identity_scope = None
        if record.identity_scope_json:
            identity_scope = IdentityScope.model_validate(json.loads(record.identity_scope_json))
        return PromotionCandidate(
            id=record.id,
            source_layer=record.source_layer,  # type: ignore[arg-type]
            target_layer=record.target_layer,  # type: ignore[arg-type]
            operation=record.operation,  # type: ignore[arg-type]
            content=record.content,
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            identity_scope=identity_scope,
            reason=record.reason,
            confidence=record.confidence,
            status=record.status,  # type: ignore[arg-type]
            write_source=record.write_source,  # type: ignore[arg-type]
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
        )

    @staticmethod
    def _context_policy_candidate_from_record(
        record: ContextPolicyCandidateRecord,
    ) -> ContextPolicyCandidate:
        return ContextPolicyCandidate(
            id=record.id,
            session_id=record.session_id,
            policy_type=record.policy_type,  # type: ignore[arg-type]
            feedback_type=record.feedback_type,  # type: ignore[arg-type]
            suggested_action=record.suggested_action,
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            status=record.status,  # type: ignore[arg-type]
            fingerprint=record.fingerprint,
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
        )

    @staticmethod
    def _core_block_from_record(record: CoreMemoryBlockRecord) -> CoreMemoryBlock:
        return CoreMemoryBlock(
            id=record.id,
            label=record.label,
            description=record.description,
            value=record.value,
            limit_tokens=record.limit_tokens,
            read_only=record.read_only,
            tags=json.loads(record.tags_json),
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            metadata=json.loads(record.metadata_json),
            created_at=record.created_at,
            updated_at=record.updated_at,
            deleted_at=record.deleted_at,
            deleted_by_event_id=record.deleted_by_event_id,
        )

    @staticmethod
    def _history_event_from_record(
        record: CoreMemoryHistoryRecord | ArchivalMemoryHistoryRecord,
    ) -> MemoryHistoryEvent:
        return MemoryHistoryEvent(
            id=record.id,
            memory_id=record.memory_id,
            memory_type=record.memory_type,  # type: ignore[arg-type]
            operation=record.operation,  # type: ignore[arg-type]
            source_refs=ArchiveStoreMixin._load_source_refs(record.source_refs_json),
            actor=record.actor,  # type: ignore[arg-type]
            reason=record.reason,
            before=json.loads(record.before_json) if record.before_json is not None else None,
            after=json.loads(record.after_json) if record.after_json is not None else None,
            created_at=record.created_at,
        )

    @staticmethod
    def _history_record_from_event(event: MemoryHistoryEvent) -> CoreMemoryHistoryRecord:
        return CoreMemoryHistoryRecord(
            id=event.id,
            memory_id=event.memory_id,
            memory_type=event.memory_type,
            operation=event.operation,
            actor=event.actor,
            reason=event.reason,
            source_refs_json=ArchiveStoreMixin._dump_source_refs(event.source_refs),
            before_json=(
                json.dumps(event.before, ensure_ascii=False) if event.before is not None else None
            ),
            after_json=(
                json.dumps(event.after, ensure_ascii=False) if event.after is not None else None
            ),
            created_at=event.created_at,
        )

    def create_core_memory_block(
        self,
        block: CoreMemoryBlock,
        *,
        actor: str = "system",
        reason: str = "core memory block created",
    ) -> CoreMemoryBlock:
        created = CoreMemoryBlock(
            id=block.id,
            label=block.label,
            description=block.description,
            value=block.value,
            limit_tokens=block.limit_tokens,
            read_only=block.read_only,
            tags=list(block.tags),
            source_refs=list(block.source_refs),
            metadata=dict(block.metadata),
            created_at=block.created_at,
            updated_at=block.updated_at,
        )
        event = MemoryHistoryEvent(
            memory_id=created.id,
            memory_type="core_block",
            operation="add",
            actor=actor,  # type: ignore[arg-type]
            reason=reason,
            before=None,
            after=created.model_dump(mode="json"),
            source_refs=list(created.source_refs),
            created_at=created.created_at,
        )
        with self.db() as db:
            db.add(
                CoreMemoryBlockRecord(
                    id=created.id,
                    label=created.label,
                    description=created.description,
                    value=created.value,
                    limit_tokens=created.limit_tokens,
                    read_only=created.read_only,
                    tags_json=json.dumps(created.tags, ensure_ascii=False),
                    source_refs_json=self._dump_source_refs(created.source_refs),
                    metadata_json=json.dumps(created.metadata, ensure_ascii=False),
                    deleted_at=created.deleted_at,
                    deleted_by_event_id=created.deleted_by_event_id,
                    created_at=created.created_at,
                    updated_at=created.updated_at,
                )
            )
            db.add(self._history_record_from_event(event))
        return created

    def get_core_memory_block(
        self,
        block_id: str,
        include_deleted: bool = False,
    ) -> CoreMemoryBlock | None:
        with self.db() as db:
            record = db.get(CoreMemoryBlockRecord, block_id)
            if record is None:
                return None
            if record.deleted_at is not None and not include_deleted:
                return None
            return self._core_block_from_record(record)

    def list_core_memory_blocks(self, include_deleted: bool = False) -> list[CoreMemoryBlock]:
        with self.db() as db:
            stmt = select(CoreMemoryBlockRecord).order_by(
                CoreMemoryBlockRecord.created_at.asc(),
                CoreMemoryBlockRecord.label.asc(),
                CoreMemoryBlockRecord.id.asc(),
            )
            records = list(db.scalars(stmt))
        blocks = [self._core_block_from_record(record) for record in records]
        if include_deleted:
            return blocks
        return [block for block in blocks if block.deleted_at is None]

    def update_core_memory_block(
        self,
        block: CoreMemoryBlock,
        *,
        actor: str | None = None,
        reason: str | None = None,
        source_refs: list[SourceRef] | None = None,
        operation: Literal["update", "replace"] = "update",
    ) -> CoreMemoryBlock | None:
        if not actor:
            raise ValueError("core memory store updates require actor")
        if not reason:
            raise ValueError("core memory store updates require reason")
        if not source_refs:
            raise ValueError("core memory store updates require source_refs")
        with self.db() as db:
            record = db.get(CoreMemoryBlockRecord, block.id)
            if record is None:
                return None
            if record.read_only:
                raise ValueError("read-only core memory block cannot be mutated")
            before = self._core_block_from_record(record)
            record.label = block.label
            record.description = block.description
            record.value = block.value
            record.limit_tokens = block.limit_tokens
            record.read_only = block.read_only
            record.tags_json = json.dumps(block.tags, ensure_ascii=False)
            record.source_refs_json = self._dump_source_refs(block.source_refs)
            record.metadata_json = json.dumps(block.metadata, ensure_ascii=False)
            record.deleted_at = block.deleted_at
            record.deleted_by_event_id = block.deleted_by_event_id
            record.updated_at = block.updated_at
            after = self._core_block_from_record(record)
            db.add(
                self._history_record_from_event(
                    MemoryHistoryEvent(
                        memory_id=before.id,
                        memory_type="core_block",
                        operation=operation,
                        actor=actor,  # type: ignore[arg-type]
                        reason=reason,
                        before=before.model_dump(mode="json"),
                        after=after.model_dump(mode="json"),
                        source_refs=list(source_refs),
                    )
                )
            )
            return after

    def delete_core_memory_block(
        self,
        block_id: str,
        source_refs: list[SourceRef],
        actor: str,
        reason: str,
    ) -> CoreMemoryBlock | None:
        with self.db() as db:
            record = db.get(CoreMemoryBlockRecord, block_id)
            if record is None:
                return None
            if record.read_only:
                raise ValueError("read-only core memory block cannot be mutated")
            before = self._core_block_from_record(record)
            event = MemoryHistoryEvent(
                memory_id=before.id,
                memory_type="core_block",
                operation="delete",
                actor=actor,  # type: ignore[arg-type]
                reason=reason,
                before=before.model_dump(mode="json"),
                after=None,
                source_refs=list(source_refs),
            )
            db.add(self._history_record_from_event(event))
            record.deleted_at = event.created_at
            record.deleted_by_event_id = event.id
            record.updated_at = event.created_at
            return self._core_block_from_record(record)

    def append_core_memory_history(self, event: MemoryHistoryEvent) -> MemoryHistoryEvent:
        with self.db() as db:
            db.add(self._history_record_from_event(event))
        return event

    def list_core_memory_history(self, block_id: str) -> list[MemoryHistoryEvent]:
        with self.db() as db:
            stmt = (
                select(CoreMemoryHistoryRecord)
                .where(CoreMemoryHistoryRecord.memory_id == block_id)
                .order_by(
                    CoreMemoryHistoryRecord.created_at.asc(),
                    CoreMemoryHistoryRecord.id.asc(),
                )
            )
            records = list(db.scalars(stmt))
        return [self._history_event_from_record(record) for record in records]

    def create_archival_document(self, document: ArchivalDocument) -> ArchivalDocument:
        self._require_source_refs(document.source_refs, "archival document write")
        with self.db() as db:
            db.add(
                ArchivalDocumentRecord(
                    id=document.id,
                    archive_id=document.archive_id,
                    title=document.title,
                    text=document.text,
                    version=document.version,
                    source_id=document.source_id,
                    file_id=document.file_id,
                    tags_json=self._dump_json(document.tags),
                    source_refs_json=self._dump_source_refs(document.source_refs),
                    producer=document.producer,
                    legacy_page_id=document.legacy_page_id,
                    metadata_json=self._dump_json(document.metadata),
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                )
            )
        return document

    def get_archival_document(self, document_id: str) -> ArchivalDocument | None:
        with self.db() as db:
            record = db.get(ArchivalDocumentRecord, document_id)
            return None if record is None else self._document_from_record(record)

    def create_archival_chunk(self, chunk: ArchivalChunk) -> ArchivalChunk:
        self._require_source_refs(chunk.source_refs, "archival chunk write")
        with self.db() as db:
            db.add(
                ArchivalChunkRecord(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    archive_id=chunk.archive_id,
                    text=chunk.text,
                    start=chunk.start,
                    end=chunk.end,
                    tags_json=self._dump_json(chunk.tags),
                    source_refs_json=self._dump_source_refs(chunk.source_refs),
                    metadata_json=self._dump_json(chunk.metadata),
                    created_at=chunk.created_at,
                    updated_at=chunk.updated_at,
                )
            )
        return chunk

    def list_archival_chunks(self, document_id: str | None = None) -> list[ArchivalChunk]:
        with self.db() as db:
            stmt = select(ArchivalChunkRecord).order_by(
                ArchivalChunkRecord.start.asc(),
                ArchivalChunkRecord.created_at.asc(),
            )
            if document_id is not None:
                stmt = stmt.where(ArchivalChunkRecord.document_id == document_id)
            records = list(db.scalars(stmt))
        return [self._chunk_from_record(record) for record in records]

    def create_archival_passage(self, passage: ArchivalPassage) -> ArchivalPassage:
        self._require_source_refs(passage.source_refs, "archival passage write")
        self._validate_archival_passage_identity(passage)
        with self.db() as db:
            db.add(
                ArchivalPassageRecord(
                    id=passage.id,
                    document_id=passage.document_id,
                    chunk_id=passage.chunk_id,
                    archive_id=passage.archive_id,
                    text=passage.text,
                    citation_start=passage.citation.start if passage.citation else None,
                    citation_end=passage.citation.end if passage.citation else None,
                    source_id=passage.source_id,
                    file_id=passage.file_id,
                    scope_json=(
                        passage.scope.model_dump_json() if passage.scope is not None else None
                    ),
                    tags_json=self._dump_json(passage.tags),
                    score=passage.score,
                    source_refs_json=self._dump_source_refs(passage.source_refs),
                    legacy_item_id=passage.legacy_item_id,
                    metadata_json=self._dump_json(passage.metadata),
                    created_at=passage.created_at,
                    updated_at=passage.updated_at,
                )
            )
        return passage

    def create_archival_ingest_records(
        self,
        *,
        document: ArchivalDocument,
        chunks: list[ArchivalChunk],
        passages: list[ArchivalPassage],
    ) -> tuple[ArchivalDocument, list[ArchivalChunk], list[ArchivalPassage]]:
        self._require_source_refs(document.source_refs, "archival document write")
        for chunk in chunks:
            self._require_source_refs(chunk.source_refs, "archival chunk write")
        for passage in passages:
            self._require_source_refs(passage.source_refs, "archival passage write")
            self._validate_archival_passage_identity(passage)
        with self.db() as db:
            db.add(
                ArchivalDocumentRecord(
                    id=document.id,
                    archive_id=document.archive_id,
                    title=document.title,
                    text=document.text,
                    version=document.version,
                    source_id=document.source_id,
                    file_id=document.file_id,
                    tags_json=self._dump_json(document.tags),
                    source_refs_json=self._dump_source_refs(document.source_refs),
                    producer=document.producer,
                    legacy_page_id=document.legacy_page_id,
                    metadata_json=self._dump_json(document.metadata),
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                )
            )
            for chunk in chunks:
                db.add(
                    ArchivalChunkRecord(
                        id=chunk.id,
                        document_id=chunk.document_id,
                        archive_id=chunk.archive_id,
                        text=chunk.text,
                        start=chunk.start,
                        end=chunk.end,
                        tags_json=self._dump_json(chunk.tags),
                        source_refs_json=self._dump_source_refs(chunk.source_refs),
                        metadata_json=self._dump_json(chunk.metadata),
                        created_at=chunk.created_at,
                        updated_at=chunk.updated_at,
                    )
                )
            for passage in passages:
                db.add(
                    ArchivalPassageRecord(
                        id=passage.id,
                        document_id=passage.document_id,
                        chunk_id=passage.chunk_id,
                        archive_id=passage.archive_id,
                        text=passage.text,
                        citation_start=(passage.citation.start if passage.citation else None),
                        citation_end=passage.citation.end if passage.citation else None,
                        source_id=passage.source_id,
                        file_id=passage.file_id,
                        scope_json=(
                            passage.scope.model_dump_json() if passage.scope is not None else None
                        ),
                        tags_json=self._dump_json(passage.tags),
                        score=passage.score,
                        source_refs_json=self._dump_source_refs(passage.source_refs),
                        legacy_item_id=passage.legacy_item_id,
                        metadata_json=self._dump_json(passage.metadata),
                        created_at=passage.created_at,
                        updated_at=passage.updated_at,
                    )
                )
        return document, chunks, passages

    def _archival_passage_from_memory(self, memory: ArchivalMemory) -> ArchivalPassage:
        scope = memory.identity_scope
        if scope is None and memory.archive_id is not None:
            scope = IdentityScope(archive_id=memory.archive_id)
        source_id = None
        file_id = None
        if memory.archive_id is None:
            source_id = memory.source_id
            if source_id is None:
                source_id = next(
                    (
                        source_ref.source_id
                        for source_ref in memory.source_refs
                        if source_ref.source_id
                    ),
                    None,
                )
            if source_id is None:
                file_id = memory.file_id
        return ArchivalPassage(
            id=self._archival_passage_id(memory.id),
            archive_id=memory.archive_id,
            text=memory.content,
            citation=SourceSpan(start=0, end=len(memory.content)),
            source_id=source_id,
            file_id=file_id,
            scope=scope,
            tags=list(memory.tags),
            source_refs=list(memory.source_refs),
            legacy_item_id=memory.id,
            metadata={
                **memory.metadata,
                "producer": "archival_memory",
                "archival_memory_id": memory.id,
                "memory_type": memory.memory_type,
                "memory_updated_at": memory.updated_at.isoformat(),
            },
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )

    @staticmethod
    def _archival_passage_id(memory_id: str) -> str:
        return f"apsg_{memory_id}"

    def _upsert_archival_passage_for_memory(
        self,
        db: DbSession,
        memory: ArchivalMemory,
    ) -> None:
        passage = self._archival_passage_from_memory(memory)
        self._validate_archival_passage_identity(passage)
        record = db.get(ArchivalPassageRecord, passage.id)
        if record is None:
            db.add(
                ArchivalPassageRecord(
                    id=passage.id,
                    document_id=passage.document_id,
                    chunk_id=passage.chunk_id,
                    archive_id=passage.archive_id,
                    text=passage.text,
                    citation_start=passage.citation.start if passage.citation else None,
                    citation_end=passage.citation.end if passage.citation else None,
                    source_id=passage.source_id,
                    file_id=passage.file_id,
                    scope_json=(
                        passage.scope.model_dump_json() if passage.scope is not None else None
                    ),
                    tags_json=self._dump_json(passage.tags),
                    score=passage.score,
                    source_refs_json=self._dump_source_refs(passage.source_refs),
                    legacy_item_id=passage.legacy_item_id,
                    metadata_json=self._dump_json(passage.metadata),
                    created_at=passage.created_at,
                    updated_at=passage.updated_at,
                )
            )
            return
        record.document_id = passage.document_id
        record.chunk_id = passage.chunk_id
        record.archive_id = passage.archive_id
        record.text = passage.text
        record.citation_start = passage.citation.start if passage.citation else None
        record.citation_end = passage.citation.end if passage.citation else None
        record.source_id = passage.source_id
        record.file_id = passage.file_id
        record.scope_json = passage.scope.model_dump_json() if passage.scope is not None else None
        record.tags_json = self._dump_json(passage.tags)
        record.score = passage.score
        record.source_refs_json = self._dump_source_refs(passage.source_refs)
        record.legacy_item_id = passage.legacy_item_id
        record.metadata_json = self._dump_json(passage.metadata)
        record.updated_at = passage.updated_at

    def _delete_archival_passage_for_memory(self, db: DbSession, memory_id: str) -> None:
        passage_id = self._archival_passage_id(memory_id)
        record = db.get(ArchivalPassageRecord, passage_id)
        if record is not None:
            db.delete(record)

    @staticmethod
    def _validate_archival_passage_identity(passage: ArchivalPassage) -> None:
        if passage.archive_id and (passage.source_id or passage.file_id):
            raise ValueError("agent/archive passages cannot set source_id or file_id")
        if not passage.archive_id and not passage.source_id and not passage.file_id:
            raise ValueError("agent/archive passages require archive_id, source_id, or file_id")

    def list_archival_passages(
        self,
        archive_id: str | None = None,
        source_id: str | None = None,
        file_id: str | None = None,
    ) -> list[ArchivalPassage]:
        with self.db() as db:
            stmt = select(ArchivalPassageRecord).order_by(
                ArchivalPassageRecord.created_at.asc(),
                ArchivalPassageRecord.id.asc(),
            )
            if archive_id is not None:
                stmt = stmt.where(ArchivalPassageRecord.archive_id == archive_id)
            if source_id is not None:
                stmt = stmt.where(ArchivalPassageRecord.source_id == source_id)
            if file_id is not None:
                stmt = stmt.where(ArchivalPassageRecord.file_id == file_id)
            records = list(db.scalars(stmt))
        return [self._passage_from_record(record) for record in records]

    def list_archival_passages_page(
        self,
        archive_id: str | None = None,
        source_id: str | None = None,
        file_id: str | None = None,
        producer: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> ArchivalPassagePage:
        normalized_limit = min(max(limit, 1), 500)
        normalized_offset = max(offset, 0)
        passages = self.list_archival_passages(
            archive_id=archive_id,
            source_id=source_id,
            file_id=file_id,
        )
        if producer is not None:
            passages = [
                passage
                for passage in passages
                if str(passage.metadata.get("producer") or "") == producer
            ]
        total = len(passages)
        return ArchivalPassagePage(
            passages=passages[normalized_offset : normalized_offset + normalized_limit],
            total=total,
            limit=normalized_limit,
            offset=normalized_offset,
        )

    def get_archival_passages_by_ids(
        self,
        passage_ids: list[str],
    ) -> dict[str, ArchivalPassage]:
        ids = self._dedupe_strings(passage_ids)
        if not ids:
            return {}
        with self.db() as db:
            stmt = (
                select(ArchivalPassageRecord)
                .where(ArchivalPassageRecord.id.in_(ids))
                .order_by(
                    ArchivalPassageRecord.created_at.asc(),
                    ArchivalPassageRecord.id.asc(),
                )
            )
            records = list(db.scalars(stmt))
        return {record.id: self._passage_from_record(record) for record in records}

    def resolve_attached_archive_ids(
        self,
        scope: ArchiveEligibilityScope,
    ) -> list[str]:
        eligible = list(scope.archive_ids)
        pairs: list[tuple[str, str]] = [("session", scope.session_id)]
        if scope.identity_scope is not None:
            identity = scope.identity_scope
            pairs.extend(
                (scope_type, scope_id)
                for scope_type, scope_id in [
                    ("user", identity.user_id),
                    ("agent", identity.agent_id),
                    ("run", identity.run_id),
                    ("session", identity.session_id),
                    ("project", identity.project_id),
                ]
                if scope_id
            )
            if identity.archive_id:
                eligible.append(identity.archive_id)
        pairs.extend(("source", source_id) for source_id in scope.source_ids)
        seen_pairs: set[tuple[str, str]] = set()
        for scope_type, scope_id in pairs:
            pair = (scope_type, scope_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            for attachment in self.list_archive_attachments(
                scope_type=scope_type,
                scope_id=scope_id,
            ):
                eligible.append(attachment.archive_id)
        return self._dedupe_strings(eligible)

    def list_archival_passages_for_scope(
        self,
        scope: ArchiveEligibilityScope,
    ) -> ArchiveEligibilityResult:
        eligible_archive_ids = self.resolve_attached_archive_ids(scope)
        all_passages = self.list_archival_passages()
        source_ids = set(scope.source_ids)
        eligible_passages = [
            passage
            for passage in all_passages
            if (passage.archive_id is not None and passage.archive_id in eligible_archive_ids)
            or (passage.source_id is not None and passage.source_id in source_ids)
        ]
        eligible_ids = {passage.id for passage in eligible_passages}
        scope_excluded_passages = [
            passage for passage in all_passages if passage.id not in eligible_ids
        ]
        return ArchiveEligibilityResult(
            scope=scope,
            eligible_archive_ids=eligible_archive_ids,
            eligible_passages=eligible_passages,
            scope_excluded_passages=scope_excluded_passages,
            scope_excluded_passage_ids=[passage.id for passage in scope_excluded_passages],
        )

    def create_archive_attachment(self, attachment: ArchiveAttachment) -> ArchiveAttachment:
        self._require_source_refs(attachment.source_refs, "archive attachment write")
        with self.db() as db:
            db.add(
                ArchiveAttachmentRecord(
                    id=attachment.id,
                    archive_id=attachment.archive_id,
                    scope_type=attachment.scope_type,
                    scope_id=attachment.scope_id,
                    source_refs_json=self._dump_source_refs(attachment.source_refs),
                    metadata_json=self._dump_json(attachment.metadata),
                    created_at=attachment.created_at,
                )
            )
        return attachment

    def list_archive_attachments(
        self,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> list[ArchiveAttachment]:
        with self.db() as db:
            stmt = select(ArchiveAttachmentRecord).order_by(
                ArchiveAttachmentRecord.created_at.asc(),
                ArchiveAttachmentRecord.id.asc(),
            )
            if scope_type is not None:
                stmt = stmt.where(ArchiveAttachmentRecord.scope_type == scope_type)
            if scope_id is not None:
                stmt = stmt.where(ArchiveAttachmentRecord.scope_id == scope_id)
            records = list(db.scalars(stmt))
        return [self._archive_attachment_from_record(record) for record in records]

    def create_promotion_candidate(
        self,
        candidate: PromotionCandidate,
    ) -> PromotionCandidate:
        self._require_source_refs(candidate.source_refs, "promotion candidate write")
        ensure_persisted_identity_scope(candidate.identity_scope)
        with self.db() as db:
            db.add(
                PromotionCandidateRecord(
                    id=candidate.id,
                    source_layer=candidate.source_layer,
                    target_layer=candidate.target_layer,
                    operation=candidate.operation,
                    content=candidate.content,
                    source_refs_json=self._dump_source_refs(candidate.source_refs),
                    identity_scope_json=(
                        candidate.identity_scope.model_dump_json()
                        if candidate.identity_scope is not None
                        else None
                    ),
                    reason=candidate.reason,
                    confidence=candidate.confidence,
                    status=candidate.status,
                    write_source=candidate.write_source,
                    metadata_json=self._dump_json(candidate.metadata),
                    created_at=candidate.created_at,
                    updated_at=candidate.updated_at,
                )
            )
        return candidate

    def get_promotion_candidate(self, candidate_id: str) -> PromotionCandidate | None:
        with self.db() as db:
            record = db.get(PromotionCandidateRecord, candidate_id)
            return None if record is None else self._promotion_candidate_from_record(record)

    def list_promotion_candidates(
        self,
        *,
        status: str | None = None,
        target_layer: str | None = None,
    ) -> list[PromotionCandidate]:
        with self.db() as db:
            stmt = select(PromotionCandidateRecord).order_by(
                PromotionCandidateRecord.created_at.asc(),
                PromotionCandidateRecord.id.asc(),
            )
            if status is not None:
                stmt = stmt.where(PromotionCandidateRecord.status == status)
            if target_layer is not None:
                stmt = stmt.where(PromotionCandidateRecord.target_layer == target_layer)
            records = list(db.scalars(stmt))
        return [self._promotion_candidate_from_record(record) for record in records]

    def update_promotion_candidate_status(
        self,
        candidate_id: str,
        *,
        status: PromotionStatus,
        metadata: dict[str, Any] | None = None,
    ) -> PromotionCandidate | None:
        updated_at = utc_now()
        with self.db() as db:
            record = db.get(PromotionCandidateRecord, candidate_id)
            if record is None:
                return None
            record.status = status
            if metadata is not None:
                record.metadata_json = self._dump_json(metadata)
            record.updated_at = updated_at
            db.add(record)
        return self.get_promotion_candidate(candidate_id)

    def create_context_policy_candidate(
        self,
        candidate: ContextPolicyCandidate,
    ) -> ContextPolicyCandidate:
        self._require_source_refs(
            candidate.source_refs,
            "context policy candidate write",
        )
        with self.db() as db:
            db.add(
                ContextPolicyCandidateRecord(
                    id=candidate.id,
                    session_id=candidate.session_id,
                    policy_type=candidate.policy_type,
                    feedback_type=candidate.feedback_type,
                    suggested_action=candidate.suggested_action,
                    source_refs_json=self._dump_source_refs(candidate.source_refs),
                    status=candidate.status,
                    fingerprint=candidate.fingerprint,
                    metadata_json=self._dump_json(candidate.metadata),
                    created_at=candidate.created_at,
                    updated_at=candidate.updated_at,
                )
            )
        return candidate

    def get_context_policy_candidate(
        self,
        candidate_id: str,
    ) -> ContextPolicyCandidate | None:
        with self.db() as db:
            record = db.get(ContextPolicyCandidateRecord, candidate_id)
            if record is None:
                return None
            return self._context_policy_candidate_from_record(record)

    def get_context_policy_candidate_by_fingerprint(
        self,
        fingerprint: str,
    ) -> ContextPolicyCandidate | None:
        with self.db() as db:
            record = db.scalar(
                select(ContextPolicyCandidateRecord).where(
                    ContextPolicyCandidateRecord.fingerprint == fingerprint
                )
            )
            if record is None:
                return None
            return self._context_policy_candidate_from_record(record)

    def list_context_policy_candidates(
        self,
        *,
        status: ContextPolicyCandidateStatus | None = None,
        session_id: str | None = None,
        feedback_type: str | None = None,
    ) -> list[ContextPolicyCandidate]:
        with self.db() as db:
            stmt = select(ContextPolicyCandidateRecord).order_by(
                ContextPolicyCandidateRecord.created_at.asc(),
                ContextPolicyCandidateRecord.id.asc(),
            )
            if status is not None:
                stmt = stmt.where(ContextPolicyCandidateRecord.status == status)
            if session_id is not None:
                stmt = stmt.where(ContextPolicyCandidateRecord.session_id == session_id)
            if feedback_type is not None:
                stmt = stmt.where(ContextPolicyCandidateRecord.feedback_type == feedback_type)
            records = list(db.scalars(stmt))
        return [self._context_policy_candidate_from_record(record) for record in records]

    def update_context_policy_candidate_status(
        self,
        candidate_id: str,
        *,
        status: ContextPolicyCandidateStatus,
        metadata: dict[str, Any] | None = None,
    ) -> ContextPolicyCandidate | None:
        updated_at = utc_now()
        with self.db() as db:
            record = db.get(ContextPolicyCandidateRecord, candidate_id)
            if record is None:
                return None
            record.status = status
            if metadata is not None:
                record.metadata_json = self._dump_json(metadata)
            record.updated_at = updated_at
            db.add(record)
        return self.get_context_policy_candidate(candidate_id)

    def add_archival_memory(
        self,
        memory: ArchivalMemory,
        *,
        actor: str,
        reason: str,
    ) -> ArchivalMemory:
        self._require_source_refs(memory.source_refs, "archival memory write")
        ensure_persisted_identity_scope(memory.identity_scope)
        event = MemoryHistoryEvent(
            memory_id=memory.id,
            memory_type="archival_memory",
            operation="add",
            actor=actor,  # type: ignore[arg-type]
            reason=reason,
            after=memory.model_dump(mode="json"),
            source_refs=list(memory.source_refs),
            created_at=memory.created_at,
        )
        memory.history.append(event)
        with self.db() as db:
            db.add(self._archival_memory_record(memory))
            db.add(self._archival_history_record(event))
            self._upsert_archival_passage_for_memory(db, memory)
        return memory

    def update_archival_memory(
        self,
        memory_id: str,
        *,
        content: str,
        source_refs: list[SourceRef],
        actor: str,
        reason: str,
    ) -> ArchivalMemory | None:
        self._require_source_refs(source_refs, "archival memory update")
        with self.db() as db:
            record = db.get(ArchivalMemoryRecord, memory_id)
            if record is None:
                return None
            before = self._archival_memory_from_record(record)
            record.content = content
            record.source_refs_json = self._dump_source_refs(source_refs)
            record.updated_at = utc_now()
            updated = self._archival_memory_from_record(record)
            event = MemoryHistoryEvent(
                memory_id=memory_id,
                memory_type="archival_memory",
                operation="update",
                actor=actor,  # type: ignore[arg-type]
                reason=reason,
                before=before.model_dump(mode="json"),
                after=updated.model_dump(mode="json"),
                source_refs=list(source_refs),
                created_at=record.updated_at,
            )
            history = json.loads(record.history_json)
            history.append(event.model_dump(mode="json"))
            record.history_json = self._dump_json(history)
            db.add(self._archival_history_record(event))
            self._upsert_archival_passage_for_memory(db, updated)
            return updated

    def delete_archival_memory(
        self,
        memory_id: str,
        *,
        source_refs: list[SourceRef],
        actor: str,
        reason: str,
    ) -> ArchivalMemory | None:
        self._require_source_refs(source_refs, "archival memory delete")
        with self.db() as db:
            record = db.get(ArchivalMemoryRecord, memory_id)
            if record is None:
                return None
            before = self._archival_memory_from_record(record)
            record.deleted_at = utc_now()
            record.updated_at = record.deleted_at
            deleted = self._archival_memory_from_record(record)
            event = MemoryHistoryEvent(
                memory_id=memory_id,
                memory_type="archival_memory",
                operation="delete",
                actor=actor,  # type: ignore[arg-type]
                reason=reason,
                before=before.model_dump(mode="json"),
                after=None,
                source_refs=list(source_refs),
                created_at=record.deleted_at,
            )
            history = json.loads(record.history_json)
            history.append(event.model_dump(mode="json"))
            record.history_json = self._dump_json(history)
            db.add(self._archival_history_record(event))
            self._delete_archival_passage_for_memory(db, memory_id)
            return deleted

    def list_archival_memory_history(self, memory_id: str) -> list[MemoryHistoryEvent]:
        with self.db() as db:
            stmt = (
                select(ArchivalMemoryHistoryRecord)
                .where(ArchivalMemoryHistoryRecord.memory_id == memory_id)
                .order_by(
                    ArchivalMemoryHistoryRecord.created_at.asc(),
                    ArchivalMemoryHistoryRecord.id.asc(),
                )
            )
            records = list(db.scalars(stmt))
        return [self._history_event_from_record(record) for record in records]

    def create_archival_document_from_message(
        self,
        message: Message,
        *,
        archive_id: str,
        title: str,
    ) -> ArchivalDocument:
        ref = SourceRef(
            source_type=SourceType.MESSAGE,
            source_id=message.id,
            session_id=message.session_id,
        )
        return self.create_archival_document(
            ArchivalDocument(
                id=f"adoc_{message.id}",
                archive_id=archive_id,
                title=title,
                text=message.content,
                source_refs=[ref],
                producer="message",
            )
        )

    def create_archival_passage_from_document(
        self,
        document: ArchivalDocument,
        *,
        text: str,
        source_refs: list[SourceRef],
    ) -> ArchivalPassage:
        start = document.text.find(text)
        if start < 0:
            raise ValueError("archival passage text must appear in document text")
        citation = SourceSpan(start=start, end=start + len(text))
        passage_source_refs = [
            source_ref.model_copy(update={"span": citation, "quote": text})
            for source_ref in source_refs
        ]
        return self.create_archival_passage(
            ArchivalPassage(
                id=f"apsg_{document.id}",
                document_id=document.id,
                archive_id=document.archive_id,
                text=text,
                citation=citation,
                source_id=None if document.archive_id else document.source_id,
                file_id=None if document.archive_id else document.file_id,
                tags=list(document.tags),
                source_refs=passage_source_refs,
                metadata={"producer": document.producer},
            )
        )

    def create_archival_memory_from_consolidation(
        self,
        *,
        content: str,
        memory_type: str,
        archive_id: str,
        source_refs: list[SourceRef],
    ) -> ArchivalMemory:
        return self.add_archival_memory(
            ArchivalMemory(
                id=f"amem_{len(content)}_{archive_id}",
                archive_id=archive_id,
                memory_type=memory_type,  # type: ignore[arg-type]
                content=content,
                source_refs=source_refs,
                metadata={"producer": "consolidation"},
            ),
            actor="system",
            reason="consolidation",
        )

    def _archival_memory_record(self, memory: ArchivalMemory) -> ArchivalMemoryRecord:
        return ArchivalMemoryRecord(
            id=memory.id,
            archive_id=memory.archive_id,
            memory_type=memory.memory_type,
            content=memory.content,
            identity_scope_json=(
                memory.identity_scope.model_dump_json()
                if memory.identity_scope is not None
                else None
            ),
            source_id=memory.source_id,
            file_id=memory.file_id,
            tags_json=self._dump_json(memory.tags),
            source_refs_json=self._dump_source_refs(memory.source_refs),
            history_json=self._dump_json(
                [event.model_dump(mode="json") for event in memory.history]
            ),
            entity_links_json=self._dump_json(memory.entity_links),
            legacy_item_id=memory.legacy_item_id,
            metadata_json=self._dump_json(memory.metadata),
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            deleted_at=memory.deleted_at,
        )

    def _archival_history_record(
        self,
        event: MemoryHistoryEvent,
    ) -> ArchivalMemoryHistoryRecord:
        return ArchivalMemoryHistoryRecord(
            id=event.id,
            memory_id=event.memory_id,
            memory_type=event.memory_type,
            operation=event.operation,
            actor=event.actor,
            reason=event.reason,
            source_refs_json=self._dump_source_refs(event.source_refs),
            before_json=(
                json.dumps(event.before, ensure_ascii=False) if event.before is not None else None
            ),
            after_json=(
                json.dumps(event.after, ensure_ascii=False) if event.after is not None else None
            ),
            created_at=event.created_at,
        )
