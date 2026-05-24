import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.orm import (
    Session as DbSession,
)
from sqlalchemy.types import TypeDecorator

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.schemas import (
    Episode,
    MemoryItem,
    MemoryItemType,
    MemoryPage,
    MemoryPatch,
    Message,
    PageType,
    Role,
    Session,
    TraceEvent,
    utc_now,
)
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalMemory,
    ArchivalPassage,
    ArchiveAttachment,
    ArchiveEligibilityResult,
    ArchiveEligibilityScope,
    CoreMemoryBlock,
    IdentityScope,
    MemoryHistoryEvent,
    PromotionCandidate,
    SourceRef,
    SourceSpan,
    ensure_persisted_identity_scope,
)

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

    __table_args__ = (
        Index("ix_core_memory_history_memory_created", "memory_id", "created_at"),
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

    __table_args__ = (
        Index("ix_promotion_candidates_status_created", "status", "created_at"),
    )


class MemoryStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        dsn = self.settings.sqlite_url
        self.engine = create_engine(dsn, connect_args={"check_same_thread": False})
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @property
    def pages_dir(self) -> Path:
        return self.settings.data_dir / "pages"

    @property
    def traces_dir(self) -> Path:
        return self.settings.data_dir / "traces"

    def init_db(self) -> None:
        try:
            Base.metadata.create_all(self.engine)
        except OperationalError as exc:
            if "already exists" not in str(exc):
                raise
        self._ensure_current_schema()
        # Stamp alembic_version so `alembic upgrade head` on an existing DB
        # does not fail with "table already exists".
        self._stamp_alembic_head()

    def _ensure_current_schema(self) -> None:
        with self.engine.begin() as conn:
            table_exists = conn.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'core_memory_blocks'"
                )
            ).fetchone()
            if table_exists is None:
                return
            columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(core_memory_blocks)"))
            }
            if "read_only" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE core_memory_blocks "
                        "ADD COLUMN read_only BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            if "tags_json" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE core_memory_blocks "
                        "ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'"
                    )
                )

    def _stamp_alembic_head(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version"
                    " (version_num VARCHAR(32) NOT NULL,"
                    " CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )
            row = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).fetchone()
            if row is None:
                conn.execute(
                    text(
                        "INSERT INTO alembic_version (version_num)"
                        " VALUES ('0008_add_promotion_candidates')"
                    )
                )
            elif row[0] != "0008_add_promotion_candidates":
                conn.execute(
                    text(
                        "UPDATE alembic_version "
                        "SET version_num = '0008_add_promotion_candidates'"
                    )
                )

    @contextmanager
    def db(self) -> Iterator[DbSession]:
        with self.session_factory() as session:
            yield session
            session.commit()

    def create_session(self, title: str) -> Session:
        session_model = Session(title=title)
        with self.db() as db:
            db.add(
                SessionRecord(
                    id=session_model.id,
                    title=session_model.title,
                    created_at=session_model.created_at,
                )
            )
        return session_model

    def get_session(self, session_id: str) -> Session | None:
        with self.db() as db:
            record = db.get(SessionRecord, session_id)
            if record is None:
                return None
            return Session(id=record.id, title=record.title, created_at=record.created_at)

    def get_session_by_title(self, title: str) -> Session | None:
        with self.db() as db:
            record = db.scalar(select(SessionRecord).where(SessionRecord.title == title))
            if record is None:
                return None
            return Session(id=record.id, title=record.title, created_at=record.created_at)

    def add_message(self, message: Message) -> Message:
        with self.db() as db:
            db.add(
                MessageRecord(
                    id=message.id,
                    session_id=message.session_id,
                    role=message.role.value,
                    content=message.content,
                    metadata_json=json.dumps(message.metadata, ensure_ascii=False),
                    created_at=message.created_at,
                    token_count=message.token_count,
                )
            )
        return message

    def list_messages(self, session_id: str, limit: int | None = None) -> list[Message]:
        with self.db() as db:
            if limit is not None:
                stmt = (
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_id)
                    .order_by(MessageRecord.created_at.desc())
                    .limit(limit)
                )
                records = list(reversed(list(db.scalars(stmt))))
            else:
                stmt = (
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_id)
                    .order_by(MessageRecord.created_at.asc())
                )
                records = list(db.scalars(stmt))
        return [
            Message(
                id=row.id,
                session_id=row.session_id,
                role=Role(row.role),
                content=row.content,
                metadata=json.loads(row.metadata_json),
                created_at=row.created_at,
                token_count=row.token_count,
            )
            for row in records
        ]

    def save_episode(self, episode: Episode) -> Episode:
        with self.db() as db:
            db.add(
                EpisodeRecord(
                    id=episode.id,
                    session_id=episode.session_id,
                    message_id=episode.message_id,
                    role=episode.role.value,
                    text=episode.text,
                    index_text=episode.index_text,
                    benchmark_session_id=episode.benchmark_session_id,
                    benchmark_date=episode.benchmark_date,
                    position=episode.position,
                    source_message_ids_json=json.dumps(episode.source_message_ids),
                    created_at=episode.created_at,
                )
            )
        return episode

    def list_episodes(self, session_id: str) -> list[Episode]:
        with self.db() as db:
            stmt = (
                select(EpisodeRecord)
                .where(EpisodeRecord.session_id == session_id)
                .order_by(EpisodeRecord.position.asc(), EpisodeRecord.created_at.asc())
            )
            records = list(db.scalars(stmt))
        return [self._episode_from_record(row) for row in records]

    def ensure_episodes_for_session(self, session_id: str) -> int:
        with self.db() as db:
            message_stmt = (
                select(MessageRecord)
                .where(MessageRecord.session_id == session_id)
                .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
            )
            message_records = list(db.scalars(message_stmt))
            if not message_records:
                return 0

            existing_message_ids = set(
                db.scalars(
                    select(EpisodeRecord.message_id).where(
                        EpisodeRecord.session_id == session_id
                    )
                )
            )
            max_position = db.scalar(
                select(func.coalesce(func.max(EpisodeRecord.position), 0)).where(
                    EpisodeRecord.session_id == session_id
                )
            )
            position = int(max_position or 0)
            created = 0
            for message_record in message_records:
                message = Message(
                    id=message_record.id,
                    session_id=message_record.session_id,
                    role=Role(message_record.role),
                    content=message_record.content,
                    metadata=json.loads(message_record.metadata_json),
                    created_at=message_record.created_at,
                    token_count=message_record.token_count,
                )
                if message.id in existing_message_ids:
                    continue
                position += 1
                episode = self._episode_from_message(message, position)
                db.add(
                    EpisodeRecord(
                        id=episode.id,
                        session_id=episode.session_id,
                        message_id=episode.message_id,
                        role=episode.role.value,
                        text=episode.text,
                        index_text=episode.index_text,
                        benchmark_session_id=episode.benchmark_session_id,
                        benchmark_date=episode.benchmark_date,
                        position=episode.position,
                        source_message_ids_json=json.dumps(episode.source_message_ids),
                        created_at=episode.created_at,
                    )
                )
                created += 1
        return created

    def set_episode_embedding(self, episode_id: str, embedding: list[float]) -> None:
        with self.db() as db:
            record = db.get(EpisodeRecord, episode_id)
            if record is not None:
                record.embedding = embedding

    def get_episode_embeddings(self, episode_ids: list[str]) -> dict[str, list[float]]:
        if not episode_ids:
            return {}
        with self.db() as db:
            stmt = select(EpisodeRecord.id, EpisodeRecord.embedding).where(
                EpisodeRecord.id.in_(episode_ids)
            )
            rows = list(db.execute(stmt))
        return {episode_id: emb for episode_id, emb in rows if emb is not None}

    def _episode_from_record(self, record: EpisodeRecord) -> Episode:
        return Episode(
            id=record.id,
            session_id=record.session_id,
            message_id=record.message_id,
            role=Role(record.role),
            text=record.text,
            index_text=record.index_text,
            benchmark_session_id=record.benchmark_session_id,
            benchmark_date=record.benchmark_date,
            position=record.position,
            source_message_ids=json.loads(record.source_message_ids_json),
            created_at=record.created_at,
        )

    def _episode_from_message(self, message: Message, position: int) -> Episode:
        benchmark_session_id = message.metadata.get("benchmark_session_id")
        benchmark_date = message.metadata.get("benchmark_date")
        text_value = message.content
        if isinstance(benchmark_session_id, str):
            prefix = f"[{benchmark_session_id}] "
            if text_value.startswith(prefix):
                text_value = text_value[len(prefix) :]
        index_parts = []
        if isinstance(benchmark_session_id, str):
            index_parts.append(f"session={benchmark_session_id}")
        if isinstance(benchmark_date, str):
            index_parts.append(f"date={benchmark_date}")
        index_parts.append(f"speaker={message.role.value}")
        index_text = f"[{' '.join(index_parts)}] {text_value}"
        return Episode(
            session_id=message.session_id,
            message_id=message.id,
            role=message.role,
            text=text_value,
            index_text=index_text,
            benchmark_session_id=benchmark_session_id
            if isinstance(benchmark_session_id, str)
            else None,
            benchmark_date=benchmark_date if isinstance(benchmark_date, str) else None,
            position=position,
            source_message_ids=[message.id],
            created_at=message.created_at,
        )

    def session_token_count(self, session_id: str) -> int:
        with self.db() as db:
            total = db.scalar(
                select(func.coalesce(func.sum(MessageRecord.token_count), 0)).where(
                    MessageRecord.session_id == session_id
                )
            )
        return int(total or 0)

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
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            producer=record.producer,
            legacy_page_id=record.legacy_page_id,
            metadata=json.loads(record.metadata_json),
            created_at=MemoryStore._aware(record.created_at),
            updated_at=MemoryStore._aware(record.updated_at),
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
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            metadata=json.loads(record.metadata_json),
            created_at=MemoryStore._aware(record.created_at),
            updated_at=MemoryStore._aware(record.updated_at),
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
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            legacy_item_id=record.legacy_item_id,
            metadata=json.loads(record.metadata_json),
            created_at=MemoryStore._aware(record.created_at),
            updated_at=MemoryStore._aware(record.updated_at),
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
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            history=[
                MemoryHistoryEvent.model_validate(event)
                for event in json.loads(record.history_json)
            ],
            entity_links=json.loads(record.entity_links_json),
            legacy_item_id=record.legacy_item_id,
            metadata=json.loads(record.metadata_json),
            created_at=MemoryStore._aware(record.created_at),
            updated_at=MemoryStore._aware(record.updated_at),
            deleted_at=MemoryStore._aware(record.deleted_at),
        )

    @staticmethod
    def _archive_attachment_from_record(record: ArchiveAttachmentRecord) -> ArchiveAttachment:
        return ArchiveAttachment(
            id=record.id,
            archive_id=record.archive_id,
            scope_type=record.scope_type,  # type: ignore[arg-type]
            scope_id=record.scope_id,
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            metadata=json.loads(record.metadata_json),
            created_at=MemoryStore._aware(record.created_at),
        )

    @staticmethod
    def _promotion_candidate_from_record(
        record: PromotionCandidateRecord,
    ) -> PromotionCandidate:
        identity_scope = None
        if record.identity_scope_json:
            identity_scope = IdentityScope.model_validate(
                json.loads(record.identity_scope_json)
            )
        return PromotionCandidate(
            id=record.id,
            source_layer=record.source_layer,  # type: ignore[arg-type]
            target_layer=record.target_layer,  # type: ignore[arg-type]
            operation=record.operation,  # type: ignore[arg-type]
            content=record.content,
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            identity_scope=identity_scope,
            reason=record.reason,
            confidence=record.confidence,
            status=record.status,  # type: ignore[arg-type]
            write_source=record.write_source,  # type: ignore[arg-type]
            metadata=json.loads(record.metadata_json),
            created_at=MemoryStore._aware(record.created_at),
            updated_at=MemoryStore._aware(record.updated_at),
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
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
            metadata=json.loads(record.metadata_json),
            created_at=record.created_at,
            updated_at=record.updated_at,
            deleted_at=record.deleted_at,
            deleted_by_event_id=record.deleted_by_event_id,
        )

    @staticmethod
    def _history_event_from_record(record: CoreMemoryHistoryRecord) -> MemoryHistoryEvent:
        return MemoryHistoryEvent(
            id=record.id,
            memory_id=record.memory_id,
            memory_type=record.memory_type,  # type: ignore[arg-type]
            operation=record.operation,  # type: ignore[arg-type]
            source_refs=MemoryStore._load_source_refs(record.source_refs_json),
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
            source_refs_json=MemoryStore._dump_source_refs(event.source_refs),
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
        record.scope_json = (
            passage.scope.model_dump_json() if passage.scope is not None else None
        )
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
        if passage.archive_id and passage.source_id:
            raise ValueError("agent/archive passages cannot set source_id")
        if not passage.archive_id and not passage.source_id:
            raise ValueError("agent/archive passages require archive_id")

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
            if (
                passage.archive_id is not None
                and passage.archive_id in eligible_archive_ids
            )
            or (passage.source_id is not None and passage.source_id in source_ids)
        ]
        eligible_ids = {passage.id for passage in eligible_passages}
        return ArchiveEligibilityResult(
            scope=scope,
            eligible_archive_ids=eligible_archive_ids,
            eligible_passages=eligible_passages,
            scope_excluded_passage_ids=[
                passage.id for passage in all_passages if passage.id not in eligible_ids
            ],
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
        ref = SourceRef(source_type="message", source_id=message.id, session_id=message.session_id)
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
        return self.create_archival_passage(
            ArchivalPassage(
                id=f"apsg_{document.id}",
                document_id=document.id,
                archive_id=document.archive_id,
                text=text,
                citation=SourceSpan(start=0, end=len(text)),
                source_id=None if document.archive_id else document.source_id,
                file_id=None if document.archive_id else document.file_id,
                tags=list(document.tags),
                source_refs=source_refs,
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

    def save_page(self, page: MemoryPage) -> MemoryPage:
        page_dir = self.pages_dir / page.session_id
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / f"{page.id}.json"
        content_json = page.model_dump_json(indent=2)
        with self.db() as db:
            db.add(
                PageRecord(
                    id=page.id,
                    session_id=page.session_id,
                    page_type=page.page_type.value,
                    title=page.title,
                    path=str(page_path),
                    content_json=content_json,
                    source_message_ids_json=json.dumps(page.source_message_ids),
                    confidence=int(page.confidence * 100),
                    version=page.version,
                    superseded_by=page.superseded_by,
                    created_at=page.created_at,
                    updated_at=page.updated_at,
                )
            )
        page_path.write_text(content_json, encoding="utf-8")
        return page

    def set_page_embedding(self, page_id: str, embedding: list[float]) -> None:
        with self.db() as db:
            record = db.get(PageRecord, page_id)
            if record is not None:
                record.embedding = embedding

    def mark_page_superseded(self, page_id: str, by_page_id: str) -> MemoryPage | None:
        """Mark ``page_id`` as superseded by ``by_page_id`` and persist.

        Updates the on-disk JSON (source of truth for the field) and the
        ``content_json`` + ``updated_at`` columns so that later loads see
        the new state. Clears the embedding so the page is excluded from
        ANN retrieval. Returns the updated page, or ``None`` if not found.
        """
        page = self.load_page(page_id)
        if page is None:
            return None
        page.superseded_by = by_page_id
        page.updated_at = utc_now()
        self.update_page(page)
        with self.db() as db:
            record = db.get(PageRecord, page_id)
            if record is not None:
                record.embedding = None
        return page

    def update_page(self, page: MemoryPage) -> None:
        """Persist an already-loaded page back to DB and disk."""
        content_json = page.model_dump_json(indent=2)
        with self.db() as db:
            record = db.get(PageRecord, page.id)
            if record is None:
                return
            record.content_json = content_json
            record.updated_at = page.updated_at
            record.version = page.version
            record.confidence = int(page.confidence * 100)
            record.superseded_by = page.superseded_by
            page_path = Path(record.path)
        page_path.write_text(content_json, encoding="utf-8")

    def get_page_embeddings(self, page_ids: list[str]) -> dict[str, list[float]]:
        if not page_ids:
            return {}
        with self.db() as db:
            stmt = select(PageRecord.id, PageRecord.embedding).where(PageRecord.id.in_(page_ids))
            rows = list(db.execute(stmt))
        return {page_id: embedding for page_id, embedding in rows if embedding is not None}

    def load_page(self, page_id: str) -> MemoryPage | None:
        with self.db() as db:
            record = db.get(PageRecord, page_id)
            if record is None:
                return None
            if record.content_json:
                return MemoryPage.model_validate_json(record.content_json)
            path = Path(record.path)
        if not path.exists():
            return None
        return MemoryPage.model_validate_json(path.read_text(encoding="utf-8"))

    def list_pages(
        self,
        session_id: str | None = None,
        limit: int | None = None,
        include_superseded: bool = True,
    ) -> list[MemoryPage]:
        with self.db() as db:
            if limit is not None:
                stmt = select(PageRecord).order_by(PageRecord.created_at.desc()).limit(limit)
                if session_id is not None:
                    stmt = stmt.where(PageRecord.session_id == session_id)
                if not include_superseded:
                    stmt = stmt.where(PageRecord.superseded_by == None)  # noqa: E711
                records = list(reversed(list(db.scalars(stmt))))
            else:
                stmt = select(PageRecord).order_by(PageRecord.created_at.asc())
                if session_id is not None:
                    stmt = stmt.where(PageRecord.session_id == session_id)
                if not include_superseded:
                    stmt = stmt.where(PageRecord.superseded_by == None)  # noqa: E711
                records = list(db.scalars(stmt))
        pages: list[MemoryPage] = []
        for record in records:
            if record.content_json:
                pages.append(MemoryPage.model_validate_json(record.content_json))
            else:
                path = Path(record.path)
                if path.exists():
                    pages.append(MemoryPage.model_validate_json(path.read_text(encoding="utf-8")))
        return pages

    def list_global_core_pages(self) -> list[MemoryPage]:
        """Return core_profile pages across all sessions."""
        with self.db() as db:
            stmt = (
                select(PageRecord)
                .where(PageRecord.page_type == PageType.CORE_PROFILE.value)
                .order_by(PageRecord.created_at.asc())
            )
            records = list(db.scalars(stmt))
        pages: list[MemoryPage] = []
        for record in records:
            page = self.load_page(record.id)
            if page is not None:
                pages.append(page)
        return pages

    def save_patch(self, patch: MemoryPatch) -> MemoryPatch:
        with self.db() as db:
            db.add(
                PatchRecord(
                    id=patch.id,
                    target_page_id=patch.target_page_id,
                    payload_json=patch.model_dump_json(),
                    verified=int(patch.verified),
                    created_at=patch.created_at,
                )
            )
        return patch

    def add_trace(self, event: TraceEvent) -> TraceEvent:
        with self.db() as db:
            db.add(
                TraceRecord(
                    id=event.id,
                    session_id=event.session_id,
                    event_type=event.event_type,
                    payload_json=json.dumps(event.payload, ensure_ascii=False),
                    created_at=event.created_at,
                )
            )
        trace_path = self.traces_dir / f"{event.session_id}.jsonl"
        with trace_path.open("a", encoding="utf-8") as file:
            file.write(event.model_dump_json() + "\n")
        return event

    def list_traces(self, session_id: str) -> list[TraceEvent]:
        with self.db() as db:
            stmt = (
                select(TraceRecord)
                .where(TraceRecord.session_id == session_id)
                .order_by(TraceRecord.created_at.asc())
            )
            records = list(db.scalars(stmt))
        return [
            TraceEvent(
                id=row.id,
                session_id=row.session_id,
                event_type=row.event_type,
                payload=json.loads(row.payload_json),
                created_at=row.created_at,
            )
            for row in records
        ]

    def save_items(self, items: list[MemoryItem]) -> None:
        if not items:
            return
        with self.db() as db:
            for item in items:
                db.add(
                    ItemRecord(
                        id=item.id,
                        page_id=item.page_id,
                        session_id=item.session_id,
                        item_type=item.item_type.value,
                        content=item.content,
                        source_message_ids_json=json.dumps(item.source_message_ids),
                        created_at=item.created_at,
                    )
                )

    def list_items(
        self,
        session_id: str,
        page_id: str | None = None,
    ) -> list[MemoryItem]:
        with self.db() as db:
            stmt = (
                select(ItemRecord)
                .where(ItemRecord.session_id == session_id)
                .order_by(ItemRecord.created_at.asc())
            )
            if page_id is not None:
                stmt = stmt.where(ItemRecord.page_id == page_id)
            records = list(db.scalars(stmt))
        return [
            MemoryItem(
                id=row.id,
                page_id=row.page_id,
                session_id=row.session_id,
                item_type=MemoryItemType(row.item_type),
                content=row.content,
                source_message_ids=json.loads(row.source_message_ids_json),
                created_at=row.created_at,
            )
            for row in records
        ]

    def set_item_embedding(self, item_id: str, embedding: list[float]) -> None:
        with self.db() as db:
            record = db.get(ItemRecord, item_id)
            if record is not None:
                record.embedding = embedding

    def get_item_embeddings(self, item_ids: list[str]) -> dict[str, list[float]]:
        if not item_ids:
            return {}
        with self.db() as db:
            stmt = select(ItemRecord.id, ItemRecord.embedding).where(
                ItemRecord.id.in_(item_ids)
            )
            rows = list(db.execute(stmt))
        return {item_id: emb for item_id, emb in rows if emb is not None}

    def load_item(self, item_id: str) -> MemoryItem | None:
        with self.db() as db:
            record = db.get(ItemRecord, item_id)
            if record is None:
                return None
            return MemoryItem(
                id=record.id,
                page_id=record.page_id,
                session_id=record.session_id,
                item_type=MemoryItemType(record.item_type),
                content=record.content,
                source_message_ids=json.loads(record.source_message_ids_json),
                created_at=record.created_at,
            )

    def update_item_content(self, item_id: str, content: str) -> bool:
        with self.db() as db:
            record = db.get(ItemRecord, item_id)
            if record is None:
                return False
            record.content = content
        return True

    def reset(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self._stamp_alembic_head()
        if self.pages_dir.exists():
            for path in self.pages_dir.rglob("*.json"):
                path.unlink()
        if self.traces_dir.exists():
            for path in self.traces_dir.rglob("*.jsonl"):
                path.unlink()


def create_store(settings: Settings | None = None) -> MemoryStore:
    store = MemoryStore(settings)
    store.init_db()
    return store
