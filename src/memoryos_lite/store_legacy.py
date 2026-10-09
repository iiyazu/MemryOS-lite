"""Legacy persistence slice composed with the concrete store runtime."""

import json
import re
from contextlib import AbstractContextManager
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session as DbSession

from memoryos_lite.schemas import (
    MemoryItem,
    MemoryItemType,
    MemoryPage,
    MemoryPatch,
    PageType,
    TraceEvent,
    utc_now,
)
from memoryos_lite.store_models import (
    Base,
    ItemRecord,
    PageRecord,
    PatchRecord,
    TraceRecord,
)

if TYPE_CHECKING:
    from memoryos_lite.config import Settings


class LegacyStoreMixin:
    """Legacy page, item, trace, and maintenance persistence methods."""

    # Supplied by StoreRuntimeMixin in the concrete MemoryStore composition.
    settings: "Settings"

    _COMPACT_TRACE_SESSION_LIMIT = 2_048
    _COMPACT_TRACE_TOTAL_LIMIT = 16_384
    _COMPACT_TRACE_FIELD_LIMIT = 64

    engine: Engine

    if TYPE_CHECKING:

        def db(self) -> AbstractContextManager[DbSession]: ...

        @property
        def pages_dir(self) -> Path: ...

        @property
        def traces_dir(self) -> Path: ...

        def _stamp_alembic_head(self) -> None: ...

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

    @staticmethod
    def _compact_trace_payload(event: TraceEvent) -> dict[str, Any]:
        """Return bounded observability data without retaining trace content.

        Compact traces are intentionally useful for health/accounting checks only:
        event payload values are represented by safe scalar counts and a digest.
        This keeps the database bounded and avoids copying prompts, retrieved text,
        provider output, or source paths into the managed sidecar trace.
        """
        canonical = json.dumps(
            {"event_type": event.event_type, "payload": event.payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        counts: dict[str, int] = {}
        count_suffixes = (
            "_count",
            "_size",
            "_tokens",
            "_token_count",
            "_duration_ms",
            "_elapsed_ms",
            "_attempt",
            "_turns",
            "_rank",
            "_total",
        )
        for key in sorted(event.payload):
            if len(counts) >= LegacyStoreMixin._COMPACT_TRACE_FIELD_LIMIT:
                break
            value = event.payload[key]
            if not isinstance(key, str):
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and (
                key.endswith(count_suffixes) or key in {"count", "size", "total"}
            ):
                counts[key[:64]] = value
            elif isinstance(value, (list, dict)) and (
                key.endswith(("_ids", "_items", "_events", "_refs", "_results"))
            ):
                counts[f"{key[:56]}_count"] = len(value)
        stage = event.event_type[:64]
        for key in ("stage", "phase", "reason_code", "status", "kind"):
            candidate = event.payload.get(key)
            if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", candidate):
                stage = candidate
                break
        return {
            "schema": "memoryos_trace_compact/v1",
            "stage": stage,
            "counts": counts,
            "digest": sha256(canonical).hexdigest(),
        }

    def _trim_compact_trace_records(self, db: DbSession, session_id: str) -> None:
        """Keep compact trace retention bounded per session and globally."""
        session_keep_ids = (
            select(TraceRecord.id)
            .where(TraceRecord.session_id == session_id)
            .order_by(TraceRecord.created_at.desc(), TraceRecord.id.desc())
            .limit(self._COMPACT_TRACE_SESSION_LIMIT)
        )
        db.execute(
            delete(TraceRecord).where(
                TraceRecord.session_id == session_id,
                ~TraceRecord.id.in_(session_keep_ids),
            )
        )
        total_keep_ids = (
            select(TraceRecord.id)
            .order_by(TraceRecord.created_at.desc(), TraceRecord.id.desc())
            .limit(self._COMPACT_TRACE_TOTAL_LIMIT)
        )
        db.execute(delete(TraceRecord).where(~TraceRecord.id.in_(total_keep_ids)))

    def add_trace(self, event: TraceEvent) -> TraceEvent:
        trace_mode = self.settings.resolved_trace_mode
        payload = self._compact_trace_payload(event) if trace_mode == "compact" else event.payload
        with self.db() as db:
            db.add(
                TraceRecord(
                    id=event.id,
                    session_id=event.session_id,
                    event_type=event.event_type,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=event.created_at,
                )
            )
            if trace_mode == "compact":
                self._trim_compact_trace_records(db, event.session_id)
        if trace_mode != "compact":
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
            stmt = select(ItemRecord.id, ItemRecord.embedding).where(ItemRecord.id.in_(item_ids))
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
