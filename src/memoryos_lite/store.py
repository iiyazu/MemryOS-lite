import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
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

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.schemas import (
    MemoryPage,
    MemoryPatch,
    Message,
    Role,
    Session,
    TraceEvent,
)


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


class PageRecord(Base):
    __tablename__ = "memory_pages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    page_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


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


class MemoryStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        connect_args = (
            {"check_same_thread": False} if self.settings.sqlite_url.startswith("sqlite") else {}
        )
        self.engine = create_engine(self.settings.sqlite_url, connect_args=connect_args)
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
            stmt = (
                select(MessageRecord)
                .where(MessageRecord.session_id == session_id)
                .order_by(MessageRecord.created_at.asc())
            )
            records = list(db.scalars(stmt))
        messages = [
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
        if limit is not None:
            return messages[-limit:]
        return messages

    def session_token_count(self, session_id: str) -> int:
        return sum(message.token_count for message in self.list_messages(session_id))

    def save_page(self, page: MemoryPage) -> MemoryPage:
        page_dir = self.pages_dir / page.session_id
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / f"{page.id}.json"
        page_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
        with self.db() as db:
            db.add(
                PageRecord(
                    id=page.id,
                    session_id=page.session_id,
                    page_type=page.page_type.value,
                    title=page.title,
                    path=str(page_path),
                    source_message_ids_json=json.dumps(page.source_message_ids),
                    confidence=int(page.confidence * 100),
                    version=page.version,
                    created_at=page.created_at,
                    updated_at=page.updated_at,
                )
            )
        return page

    def load_page(self, page_id: str) -> MemoryPage | None:
        with self.db() as db:
            record = db.get(PageRecord, page_id)
            if record is None:
                return None
            path = Path(record.path)
        if not path.exists():
            return None
        return MemoryPage.model_validate_json(path.read_text(encoding="utf-8"))

    def list_pages(self, session_id: str | None = None) -> list[MemoryPage]:
        with self.db() as db:
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
