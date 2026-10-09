"""Trace persistence and store reset, composed with the concrete store runtime."""

import json
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session as DbSession

from memoryos_lite.schemas import TraceEvent
from memoryos_lite.store_models import Base, TraceRecord

if TYPE_CHECKING:
    from memoryos_lite.config import Settings


class LegacyStoreMixin:
    """Trace and maintenance persistence methods."""

    # Supplied by StoreRuntimeMixin in the concrete MemoryStore composition.
    settings: "Settings"

    engine: Engine

    if TYPE_CHECKING:

        def db(self) -> AbstractContextManager[DbSession]: ...

        @property
        def traces_dir(self) -> Path: ...

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
        if self.traces_dir.exists():
            for path in self.traces_dir.rglob("*.jsonl"):
                path.unlink()
