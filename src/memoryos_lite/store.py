import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
        # Stamp alembic_version so `alembic upgrade head` on an existing DB
        # does not fail with "table already exists".
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
                        " VALUES ('0002_add_superseded_by')"
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
