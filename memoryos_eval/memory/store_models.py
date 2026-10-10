import json
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

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
    # Optional consumer scope (e.g. an xmuse module); MemoryOS stores and echoes it.
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
        Index("uq_messages_session_external", "session_id", "external_id", unique=True),
    )


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
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_archival_passages_archive_source", "archive_id", "source_id"),
        Index("ix_archival_passages_archive_file", "archive_id", "file_id"),
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


class CuratedMemoryRecord(Base):
    """One typed, source-grounded memory extracted by the LLM curator.

    Curated rows are derived state: dropping the table and replaying the
    message stream rebuilds them.  ``supersedes_id``/``superseded_by_id``
    record the deterministic ADD/UPDATE(supersede) consolidation history.
    """

    __tablename__ = "curated_memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_key: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    supersedes_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    # Deterministic consolidation: the newest version per topic_key stays active.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Lessons accumulate repeat occurrences instead of being replaced.
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_curated_memories_session_status", "session_id", "status"),
        Index("ix_curated_memories_session_created", "session_id", "created_at"),
    )


class CuratorStateRecord(Base):
    """Per-session curator watermark and cumulative counters."""

    __tablename__ = "curator_state"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_message_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_grounding: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_schema: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# These types were historically defined by ``memoryos_eval.memory.store``.  Keep their
# public identity stable while the implementation lives in this focused module;
# the composition root continues to re-export every name below.
for _compat_type in (
    EmbeddingType,
    Base,
    SessionRecord,
    MessageRecord,
    EpisodeRecord,
    TraceRecord,
    ArchivalDocumentRecord,
    ArchivalChunkRecord,
    ArchivalPassageRecord,
    ArchiveAttachmentRecord,
    CuratedMemoryRecord,
    CuratorStateRecord,
):
    _compat_type.__module__ = "memoryos_eval.memory.store"

del _compat_type
