"""Archive, source-proof, and governed-memory persistence behavior.

This module owns the archive-facing slice of ``MemoryStore``.  The concrete
composition root supplies ``db()`` and the SQLAlchemy session lifecycle.
"""

import json
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, overload

from sqlalchemy import and_, false, func, or_, select, true
from sqlalchemy.orm import Session as DbSession

from memoryos_lite.store_models import (
    ArchivalChunkRecord,
    ArchivalDocumentRecord,
    ArchivalPassageRecord,
    ArchiveAttachmentRecord,
)
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalPassage,
    ArchiveAttachment,
    ArchiveEligibilityResult,
    ArchiveEligibilityScope,
    IdentityScope,
    SourceRef,
    SourceSpan,
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
            metadata=json.loads(record.metadata_json),
            created_at=ArchiveStoreMixin._aware(record.created_at),
            updated_at=ArchiveStoreMixin._aware(record.updated_at),
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

    def list_archival_documents_for_archives(
        self,
        archive_ids: list[str],
    ) -> list[ArchivalDocument]:
        """Documents of the given archives, oldest first (deterministic order)."""

        if not archive_ids:
            return []
        with self.db() as db:
            records = list(
                db.scalars(
                    select(ArchivalDocumentRecord)
                    .where(ArchivalDocumentRecord.archive_id.in_(archive_ids))
                    .order_by(
                        ArchivalDocumentRecord.created_at.asc(),
                        ArchivalDocumentRecord.id.asc(),
                    )
                )
            )
        return [self._document_from_record(record) for record in records]

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
                        metadata_json=self._dump_json(passage.metadata),
                        created_at=passage.created_at,
                        updated_at=passage.updated_at,
                    )
                )
        return document, chunks, passages

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
        archive_ids = self._dedupe_strings(eligible_archive_ids)
        source_ids = self._dedupe_strings(scope.source_ids)
        archive_match = (
            ArchivalPassageRecord.archive_id.in_(archive_ids) if archive_ids else false()
        )
        source_match = ArchivalPassageRecord.source_id.in_(source_ids) if source_ids else false()
        eligible_predicate = or_(archive_match, source_match)
        archive_excluded = (
            or_(
                ArchivalPassageRecord.archive_id.is_(None),
                ~ArchivalPassageRecord.archive_id.in_(archive_ids),
            )
            if archive_ids
            else true()
        )
        source_excluded = (
            or_(
                ArchivalPassageRecord.source_id.is_(None),
                ~ArchivalPassageRecord.source_id.in_(source_ids),
            )
            if source_ids
            else true()
        )
        excluded_predicate = and_(archive_excluded, source_excluded)
        order_by = (
            ArchivalPassageRecord.created_at.asc(),
            ArchivalPassageRecord.id.asc(),
        )
        with self.db() as db:
            eligible_count = int(
                db.scalar(select(func.count(ArchivalPassageRecord.id)).where(eligible_predicate))
                or 0
            )
            excluded_count = int(
                db.scalar(select(func.count(ArchivalPassageRecord.id)).where(excluded_predicate))
                or 0
            )
            eligible_records = list(
                db.scalars(
                    select(ArchivalPassageRecord).where(eligible_predicate).order_by(*order_by)
                )
            )
            excluded_records = list(
                db.scalars(
                    select(ArchivalPassageRecord).where(excluded_predicate).order_by(*order_by)
                )
            )
        if eligible_count != len(eligible_records) or excluded_count != len(excluded_records):
            raise RuntimeError("archival passage scope changed during SQL read")
        eligible_passages = [self._passage_from_record(record) for record in eligible_records]
        scope_excluded_passages = [self._passage_from_record(record) for record in excluded_records]
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
