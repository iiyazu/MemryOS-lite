"""Curator persistence slice: curated memories and per-session watermark state."""

import json
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from memoryos_lite.schemas import Message, Role, new_id, utc_now
from memoryos_lite.store_models import (
    CuratedMemoryRecord,
    CuratorStateRecord,
    MessageRecord,
)


@dataclass(frozen=True)
class CuratedMemoryRow:
    id: str
    session_id: str
    kind: str
    topic_key: str
    statement: str
    sources: list[dict[str, str]]
    status: str
    supersedes_id: str | None
    superseded_by_id: str | None
    run_id: str
    model: str
    created_at: datetime
    version: int = 0
    occurrences: int = 1


@dataclass(frozen=True)
class CuratorStateRow:
    session_id: str
    last_message_seq: int
    last_run_at: datetime | None
    last_error_code: str | None
    runs: int
    proposals: int
    rejected_grounding: int
    rejected_schema: int
    llm_errors: int


@dataclass(frozen=True)
class CuratedMemoryWrite:
    """One memory row to insert in a curator window.

    ``supersedes_id`` links the replaced row (advisory chain);
    ``also_supersedes`` flips further same-topic rows to superseded.  A write
    with ``superseded_by_id`` arrived out of order: it is stored already
    superseded by that newer active row.
    """

    kind: str
    topic_key: str
    statement: str
    sources: list[dict[str, str]]
    supersedes_id: str | None = None
    version: int = 0
    occurrences: int = 1
    also_supersedes: tuple[str, ...] = ()
    superseded_by_id: str | None = None


class CuratorStoreMixin:
    """Curated-memory writes and curator watermark state for the composed store."""

    if TYPE_CHECKING:

        def db(self) -> AbstractContextManager[DbSession]: ...

    @staticmethod
    def _curated_memory_row(record: CuratedMemoryRecord) -> CuratedMemoryRow:
        return CuratedMemoryRow(
            id=record.id,
            session_id=record.session_id,
            kind=record.kind,
            topic_key=record.topic_key,
            statement=record.statement,
            sources=json.loads(record.sources_json),
            status=record.status,
            supersedes_id=record.supersedes_id,
            superseded_by_id=record.superseded_by_id,
            run_id=record.run_id,
            model=record.model,
            created_at=record.created_at,
            version=record.version or 0,
            occurrences=record.occurrences or 1,
        )

    @staticmethod
    def _curator_state_row(record: CuratorStateRecord) -> CuratorStateRow:
        return CuratorStateRow(
            session_id=record.session_id,
            last_message_seq=record.last_message_seq,
            last_run_at=record.last_run_at,
            last_error_code=record.last_error_code,
            runs=record.runs,
            proposals=record.proposals,
            rejected_grounding=record.rejected_grounding,
            rejected_schema=record.rejected_schema,
            llm_errors=record.llm_errors,
        )

    def get_curator_state(self, session_id: str) -> CuratorStateRow | None:
        with self.db() as db:
            record = db.get(CuratorStateRecord, session_id)
            return self._curator_state_row(record) if record is not None else None

    def get_curated_memory(self, memory_id: str) -> CuratedMemoryRow | None:
        with self.db() as db:
            record = db.get(CuratedMemoryRecord, memory_id)
            return self._curated_memory_row(record) if record is not None else None

    def get_curated_memories_by_ids(self, memory_ids: list[str]) -> dict[str, CuratedMemoryRow]:
        if not memory_ids:
            return {}
        with self.db() as db:
            records = db.scalars(
                select(CuratedMemoryRecord).where(CuratedMemoryRecord.id.in_(memory_ids))
            )
            return {record.id: self._curated_memory_row(record) for record in records}

    def list_active_curated_memories(
        self,
        session_id: str,
        *,
        limit: int | None = None,
    ) -> list[CuratedMemoryRow]:
        with self.db() as db:
            stmt = (
                select(CuratedMemoryRecord)
                .where(
                    CuratedMemoryRecord.session_id == session_id,
                    CuratedMemoryRecord.status == "active",
                )
                .order_by(
                    CuratedMemoryRecord.created_at.asc(),
                    CuratedMemoryRecord.id.asc(),
                )
            )
            if limit is not None:
                stmt = stmt.limit(max(1, int(limit)))
            records = list(db.scalars(stmt))
        return [self._curated_memory_row(record) for record in records]

    def list_curated_memories(
        self,
        session_id: str,
        *,
        limit: int = 32,
    ) -> list[CuratedMemoryRow]:
        """Return the newest ``limit`` curated rows, oldest first."""

        clean_limit = max(1, min(int(limit), 64))
        with self.db() as db:
            records = list(
                reversed(
                    list(
                        db.scalars(
                            select(CuratedMemoryRecord)
                            .where(CuratedMemoryRecord.session_id == session_id)
                            .order_by(
                                CuratedMemoryRecord.created_at.desc(),
                                CuratedMemoryRecord.id.desc(),
                            )
                            .limit(clean_limit)
                        )
                    )
                )
            )
        return [self._curated_memory_row(record) for record in records]

    def count_session_messages(self, session_id: str) -> int:
        with self.db() as db:
            total = db.scalar(
                select(func.count(MessageRecord.id)).where(MessageRecord.session_id == session_id)
            )
        return int(total or 0)

    def list_curator_session_ids(self) -> list[str]:
        with self.db() as db:
            message_sessions = db.scalars(select(MessageRecord.session_id).distinct())
            state_sessions = db.scalars(select(CuratorStateRecord.session_id))
            return sorted({*message_sessions, *state_sessions})

    def list_messages_for_curation(
        self,
        session_id: str,
        *,
        after_seq: int,
        limit: int,
    ) -> list[Message]:
        """Return a deterministic ordered slice of a session's message stream.

        The curator watermark counts consumed positions in
        ``(created_at, id)`` order; this slice keeps that ordering stable even
        when messages share a timestamp.
        """

        clean_after = max(0, int(after_seq))
        clean_limit = max(1, int(limit))
        with self.db() as db:
            records = list(
                db.scalars(
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_id)
                    .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
                    .offset(clean_after)
                    .limit(clean_limit)
                )
            )
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

    def curator_counter_totals(self) -> dict[str, int]:
        with self.db() as db:
            rows = list(db.scalars(select(CuratorStateRecord)))
        totals = {
            "sessions": len(rows),
            "runs": 0,
            "proposals": 0,
            "rejected_grounding": 0,
            "rejected_schema": 0,
            "llm_errors": 0,
        }
        for row in rows:
            totals["runs"] += row.runs
            totals["proposals"] += row.proposals
            totals["rejected_grounding"] += row.rejected_grounding
            totals["rejected_schema"] += row.rejected_schema
            totals["llm_errors"] += row.llm_errors
        return totals

    def apply_curator_window(
        self,
        *,
        session_id: str,
        run_id: str,
        model: str,
        last_message_seq: int,
        writes: list[CuratedMemoryWrite],
        ops_count: int = 0,
        runs: int = 0,
        rejected_grounding: int = 0,
        rejected_schema: int = 0,
        llm_errors: int = 0,
        error_code: str | None = None,
    ) -> list[CuratedMemoryRow]:
        """Commit one processed window: memories, supersede links, and watermark.

        Inserts and supersede flips happen in the same transaction as the
        watermark advance, so a crash cannot supersede a memory without
        recording that the window was consumed.
        """

        now = utc_now()
        created: list[CuratedMemoryRow] = []
        with self.db() as db:
            for write in writes:
                record = CuratedMemoryRecord(
                    id=new_id("cmem"),
                    session_id=session_id,
                    kind=write.kind,
                    topic_key=write.topic_key,
                    statement=write.statement,
                    sources_json=json.dumps(write.sources, ensure_ascii=False),
                    status="active" if write.superseded_by_id is None else "superseded",
                    supersedes_id=write.supersedes_id,
                    superseded_by_id=write.superseded_by_id,
                    run_id=run_id,
                    model=model,
                    created_at=now,
                    version=write.version,
                    occurrences=write.occurrences,
                )
                db.add(record)
                targets = ([write.supersedes_id] if write.supersedes_id is not None else []) + list(
                    write.also_supersedes
                )
                for target in targets:
                    old = db.get(CuratedMemoryRecord, target)
                    if old is not None and old.session_id == session_id and old.status == "active":
                        old.status = "superseded"
                        old.superseded_by_id = record.id
                created.append(self._curated_memory_row(record))
            self._mutate_curator_state(
                db,
                session_id,
                last_message_seq=last_message_seq,
                last_run_at=now,
                last_error_code=error_code,
                runs=runs,
                proposals=ops_count,
                rejected_grounding=rejected_grounding,
                rejected_schema=rejected_schema,
                llm_errors=llm_errors,
            )
        return created

    def bump_curator_state(
        self,
        *,
        session_id: str,
        runs: int = 0,
        ops_count: int = 0,
        rejected_grounding: int = 0,
        rejected_schema: int = 0,
        llm_errors: int = 0,
        error_code: str | None = None,
    ) -> None:
        """Record counters for a window that did not advance the watermark."""

        with self.db() as db:
            self._mutate_curator_state(
                db,
                session_id,
                last_message_seq=None,
                last_run_at=utc_now() if runs else None,
                last_error_code=error_code,
                runs=runs,
                proposals=ops_count,
                rejected_grounding=rejected_grounding,
                rejected_schema=rejected_schema,
                llm_errors=llm_errors,
            )

    @staticmethod
    def _mutate_curator_state(
        db: DbSession,
        session_id: str,
        *,
        last_message_seq: int | None,
        last_run_at: datetime | None,
        last_error_code: str | None,
        runs: int,
        proposals: int,
        rejected_grounding: int,
        rejected_schema: int,
        llm_errors: int,
    ) -> None:
        state = db.get(CuratorStateRecord, session_id)
        if state is None:
            state = CuratorStateRecord(
                session_id=session_id,
                last_message_seq=0,
                runs=0,
                proposals=0,
                rejected_grounding=0,
                rejected_schema=0,
                llm_errors=0,
            )
            db.add(state)
        if last_message_seq is not None:
            state.last_message_seq = last_message_seq
        if last_run_at is not None:
            state.last_run_at = last_run_at
        if runs or last_error_code is not None:
            state.last_error_code = last_error_code
        state.runs += runs
        state.proposals += proposals
        state.rejected_grounding += rejected_grounding
        state.rejected_schema += rejected_schema
        state.llm_errors += llm_errors
