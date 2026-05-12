import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, create_engine, func, select, text
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
    MemoryPage,
    MemoryPatch,
    Message,
    PageType,
    Role,
    Session,
    TraceEvent,
    utc_now,
)

EMBEDDING_DIM = 1536


class EmbeddingType(TypeDecorator):
    """Store ``list[float]`` as pgvector on Postgres, JSON text elsewhere.

    Reads always return ``list[float] | None`` regardless of dialect so the
    retrieval layer can stay dialect-agnostic.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value) if not isinstance(value, list) else value
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
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_memory_pages_session_type", "session_id", "page_type"),
        Index("ix_memory_pages_created", "created_at"),
    )


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


class MemoryStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        dsn = self.settings.sqlite_url
        connect_args = {"check_same_thread": False} if dsn.startswith("sqlite") else {}
        self.engine = create_engine(
            dsn,
            connect_args=connect_args,
            pool_pre_ping=not dsn.startswith("sqlite"),
        )
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @property
    def pages_dir(self) -> Path:
        return self.settings.data_dir / "pages"

    @property
    def traces_dir(self) -> Path:
        return self.settings.data_dir / "traces"

    def init_db(self) -> None:
        if self.engine.dialect.name == "postgresql":
            with self.engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        try:
            Base.metadata.create_all(self.engine)
        except OperationalError as exc:
            if "already exists" not in str(exc):
                raise

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

    def session_token_count(self, session_id: str) -> int:
        with self.db() as db:
            total = db.scalar(
                select(func.coalesce(func.sum(MessageRecord.token_count), 0)).where(
                    MessageRecord.session_id == session_id
                )
            )
        return int(total or 0)

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
        the new state. Returns the updated page, or ``None`` if it does
        not exist.
        """
        page = self.load_page(page_id)
        if page is None:
            return None
        page.superseded_by = by_page_id
        page.updated_at = utc_now()
        content_json = page.model_dump_json(indent=2)
        with self.db() as db:
            record = db.get(PageRecord, page_id)
            if record is None:
                return None
            record.content_json = content_json
            record.updated_at = page.updated_at
            page_path = Path(record.path)
        page_path.write_text(content_json, encoding="utf-8")
        return page

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
        self, session_id: str | None = None, limit: int | None = None
    ) -> list[MemoryPage]:
        with self.db() as db:
            if limit is not None:
                stmt = select(PageRecord).order_by(PageRecord.created_at.desc()).limit(limit)
                if session_id is not None:
                    stmt = stmt.where(PageRecord.session_id == session_id)
                records = list(reversed(list(db.scalars(stmt))))
            else:
                stmt = select(PageRecord).order_by(PageRecord.created_at.asc())
                if session_id is not None:
                    stmt = stmt.where(PageRecord.session_id == session_id)
                records = list(db.scalars(stmt))
        pages: list[MemoryPage] = []
        for record in records:
            page = self.load_page(record.id)
            if page is not None:
                pages.append(page)
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

    def reset(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
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
