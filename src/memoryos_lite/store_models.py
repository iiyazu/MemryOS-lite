import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from memoryos_lite.v3_contracts import ArchivalPassage

EMBEDDING_DIM = 1536


class EmbeddingType(TypeDecorator):
    """Store ``list[float]`` as JSON text (SQLite-only backend)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return list(value)


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_messages_session_created", "session_id", "created_at"),)


class EpisodeRecord(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    index_text: Mapped[str] = mapped_column(Text, nullable=False)
    benchmark_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    benchmark_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_episodes_message_id", "message_id"),
        Index("ix_episodes_session_position", "session_id", "position"),
        Index("ix_episodes_session_message", "session_id", "message_id"),
    )


class PageRecord(Base):
    __tablename__ = "memory_pages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    page_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_memory_pages_session_type", "session_id", "page_type"),
        Index("ix_memory_pages_created", "created_at"),
    )


class ItemRecord(Base):
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class PatchRecord(Base):
    __tablename__ = "memory_patches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class TraceRecord(Base):
    __tablename__ = "trace_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_trace_events_session_type_created", "session_id", "event_type", "created_at"),
    )


class CoreMemoryBlockRecord(Base):
    __tablename__ = "core_memory_blocks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limit_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    deleted_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_core_memory_blocks_created", "created_at"),)


class CoreMemoryHistoryRecord(Base):
    __tablename__ = "core_memory_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_core_memory_history_memory_created", "memory_id", "created_at"),)


class ArchivalDocumentRecord(Base):
    __tablename__ = "archival_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    archive_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    producer: Mapped[str] = mapped_column(String(32), nullable=False, default="explicit_document")
    legacy_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class ArchivalChunkRecord(Base):
    __tablename__ = "archival_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    archive_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_archival_chunks_document_start", "document_id", "start"),)


class ArchivalPassageRecord(Base):
    __tablename__ = "archival_passages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    archive_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    citation_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    score: Mapped[float | None] = mapped_column(nullable=True)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    legacy_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_archival_passages_archive_source", "archive_id", "source_id"),
        Index("ix_archival_passages_archive_file", "archive_id", "file_id"),
    )


class ArchivalMemoryRecord(Base):
    __tablename__ = "archival_memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    archive_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    identity_scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    history_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    entity_links_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    legacy_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_archival_memories_archive_type", "archive_id", "memory_type"),)


class ArchivalMemoryHistoryRecord(Base):
    __tablename__ = "archival_memory_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_archival_memory_history_memory_created", "memory_id", "created_at"),
    )


class ArchiveAttachmentRecord(Base):
    __tablename__ = "archive_attachments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    archive_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_archive_attachments_scope", "scope_type", "scope_id"),)


class PromotionCandidateRecord(Base):
    __tablename__ = "promotion_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_layer: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    target_layer: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    identity_scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    write_source: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_promotion_candidates_status_created", "status", "created_at"),)


class ContextPolicyCandidateRecord(Base):
    __tablename__ = "context_policy_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    policy_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_context_policy_candidates_status_created", "status", "created_at"),)


@dataclass(frozen=True)
class ArchivalPassagePage:
    passages: list[ArchivalPassage]
    total: int
    limit: int
    offset: int


# These types were historically defined by ``memoryos_lite.store``.  Keep their
# public identity stable while the implementation lives in this focused module;
# the composition root continues to re-export every name below.
for _compat_type in (
    EmbeddingType,
    Base,
    SessionRecord,
    MessageRecord,
    EpisodeRecord,
    PageRecord,
    ItemRecord,
    PatchRecord,
    TraceRecord,
    CoreMemoryBlockRecord,
    CoreMemoryHistoryRecord,
    ArchivalDocumentRecord,
    ArchivalChunkRecord,
    ArchivalPassageRecord,
    ArchivalMemoryRecord,
    ArchivalMemoryHistoryRecord,
    ArchiveAttachmentRecord,
    PromotionCandidateRecord,
    ContextPolicyCandidateRecord,
    ArchivalPassagePage,
):
    _compat_type.__module__ = "memoryos_lite.store"

del _compat_type
