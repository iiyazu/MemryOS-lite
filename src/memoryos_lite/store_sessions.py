import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from memoryos_lite.schemas import Episode, Message, Role, Session
from memoryos_lite.store_models import (
    ArchivalChunkRecord,
    ArchivalDocumentRecord,
    ArchivalMemoryRecord,
    ArchivalPassageRecord,
    CoreMemoryBlockRecord,
    EpisodeRecord,
    MessageRecord,
    PageRecord,
    SessionRecord,
)


class SessionStoreMixin:
    if TYPE_CHECKING:

        @contextmanager
        def db(self) -> Iterator[DbSession]: ...

        @staticmethod
        def _watermark_part(
            db: DbSession,
            name: str,
            id_column: Any,
            timestamp_column: Any,
            predicate: Any | None,
        ) -> str: ...

        @staticmethod
        def _item_watermark_part(db: DbSession, session_id: str) -> str: ...

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
                    external_id=message.external_id,
                    metadata_json=json.dumps(message.metadata, ensure_ascii=False),
                    created_at=message.created_at,
                    token_count=message.token_count,
                )
            )
        return message

    def get_message_by_external_id(self, session_id: str, external_id: str) -> Message | None:
        """Load the durable message bound to a caller-owned idempotency key."""
        with self.db() as db:
            record = db.scalar(
                select(MessageRecord).where(
                    MessageRecord.session_id == session_id,
                    MessageRecord.external_id == external_id,
                )
            )
        return self._message_from_record(record) if record is not None else None

    @staticmethod
    def _message_from_record(record: MessageRecord) -> Message:
        return Message(
            id=record.id,
            session_id=record.session_id,
            role=Role(record.role),
            content=record.content,
            external_id=record.external_id,
            metadata=json.loads(record.metadata_json),
            created_at=record.created_at,
            token_count=record.token_count,
        )

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
                external_id=row.external_id,
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

    def session_memory_watermark(self, session_id: str) -> str:
        """Return a compact revision marker for cache keys.

        SQLite remains authoritative; cache users include this value in derived
        cache keys so writes naturally select a new key instead of stale data.
        """
        with self.db() as db:
            scoped_parts = [
                self._watermark_part(
                    db,
                    "messages",
                    MessageRecord.id,
                    MessageRecord.created_at,
                    MessageRecord.session_id == session_id,
                ),
                self._watermark_part(
                    db,
                    "episodes",
                    EpisodeRecord.id,
                    EpisodeRecord.created_at,
                    EpisodeRecord.session_id == session_id,
                ),
                self._watermark_part(
                    db,
                    "pages",
                    PageRecord.id,
                    PageRecord.updated_at,
                    PageRecord.session_id == session_id,
                ),
                self._item_watermark_part(
                    db,
                    session_id,
                ),
            ]
            global_parts = [
                self._watermark_part(
                    db,
                    "core",
                    CoreMemoryBlockRecord.id,
                    CoreMemoryBlockRecord.updated_at,
                    None,
                ),
                self._watermark_part(
                    db,
                    "archive_docs",
                    ArchivalDocumentRecord.id,
                    ArchivalDocumentRecord.updated_at,
                    None,
                ),
                self._watermark_part(
                    db,
                    "archive_chunks",
                    ArchivalChunkRecord.id,
                    ArchivalChunkRecord.updated_at,
                    None,
                ),
                self._watermark_part(
                    db,
                    "archive_passages",
                    ArchivalPassageRecord.id,
                    ArchivalPassageRecord.updated_at,
                    None,
                ),
                self._watermark_part(
                    db,
                    "archive_memories",
                    ArchivalMemoryRecord.id,
                    ArchivalMemoryRecord.updated_at,
                    None,
                ),
            ]
        return "|".join([*scoped_parts, *global_parts])

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
                    select(EpisodeRecord.message_id).where(EpisodeRecord.session_id == session_id)
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
                    external_id=message_record.external_id,
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
