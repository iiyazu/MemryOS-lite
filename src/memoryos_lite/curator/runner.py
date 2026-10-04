"""Session curator: the stateful host of the curate graph for MemoryOS sessions.

``Curator.run_session`` is the single entry point used by the background
worker, the eval harness, and tests. It processes only messages after the
stored watermark, one window of ``memoryos_curator_window_messages`` at a
time: each window is one room-profile curate request (the same LangGraph loop
as ``POST /curate``: extract, check quotes, repair, deterministic
consolidation) built from the session's active memories, and the returned
memory versions are written in one transaction. The watermark advances only
for windows whose reply was usable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from memoryos_lite.config import Settings
from memoryos_lite.curator.llm import CuratorLLM, CuratorLLMError
from memoryos_lite.observability import current_observability_context
from memoryos_lite.schemas import (
    Message,
    TraceEvent,
    new_id,
    utc_now,
)
from memoryos_lite.store import MemoryStore
from memoryos_lite.store_curator import CuratedMemoryRow, CuratedMemoryWrite

if TYPE_CHECKING:
    from memoryos_lite.curator.curate import CurateActivity, CurateMemory, CurateResponse

MEMORY_KINDS = frozenset({"fact", "decision", "rule", "preference", "lesson"})
MAX_STATEMENT_CHARS = 600
MAX_TOPIC_KEY_CHARS = 255
MAX_SOURCES = 3
# A lesson accumulates the sources of its repeat occurrences, newest kept.
MAX_LESSON_SOURCES = 8
CONTEXT_MESSAGES = 4
#: Message metadata key carrying the consumer's monotonic activity order.
ACTIVITY_SEQ_KEY = "activity_seq"
ACTIVITY_TYPE_KEY = "activity_type"
_TOPIC_SEPARATORS = re.compile(r"[^\w.]+")


def normalize_topic_key(raw: str) -> str | None:
    """Canonical topic key: casefolded, word characters, ``_`` and ``.`` only."""

    key = _TOPIC_SEPARATORS.sub("_", raw.strip().casefold())
    key = re.sub(r"_+", "_", key)
    key = re.sub(r"\.+", ".", key)
    key = re.sub(r"_?\._?", ".", key).strip("._")
    if not key or len(key) > MAX_TOPIC_KEY_CHARS:
        return None
    return key


SKIP_AFTER_FAILURES = 3

REASON_KEY_MISSING = "curator_llm_key_missing"
REASON_INIT_ERROR = "curator_llm_init_error"
REASON_LLM_ERROR = "curator_llm_error"
REASON_SCHEMA_ERROR = "curator_schema_error"
REASON_REQUIRES_LANGGRAPH = "curate_requires_langgraph"


@dataclass
class CuratorRunResult:
    windows: int = 0
    operations: int = 0
    added: int = 0
    superseded: int = 0
    noop: int = 0
    rejected_grounding: int = 0
    rejected_schema: int = 0
    llm_errors: int = 0
    stale: int = 0
    status: str = "no_messages"
    error_code: str | None = None


@dataclass
class _WindowCounts:
    added: int = 0
    superseded: int = 0
    noop: int = 0
    rejected: int = 0
    stale: int = 0
    proposals: int = 0
    writes: list[CuratedMemoryWrite] = field(default_factory=list)


@dataclass(frozen=True)
class _MessageInfo:
    content: str
    version: int
    created_at: datetime
    activity_type: str | None


class _UnusableReply(Exception):
    """The LLM never produced a usable JSON reply for this window."""


def _message_info(message: Message, position: int) -> _MessageInfo:
    """Version a message by the consumer's activity order, else its position."""

    seq = message.metadata.get(ACTIVITY_SEQ_KEY)
    version = seq if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0 else position
    activity_type = message.metadata.get(ACTIVITY_TYPE_KEY)
    return _MessageInfo(
        content=message.content,
        version=version,
        created_at=message.created_at,
        activity_type=activity_type if isinstance(activity_type, str) else None,
    )


class Curator:
    def __init__(
        self,
        *,
        store: MemoryStore,
        settings: Settings,
        llm: CuratorLLM | None = None,
        model: str | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.llm = llm
        self.model = model or settings.chat_model
        self._window_failures: dict[tuple[str, int], int] = {}
        self._last_llm_ok: bool | None = None
        self._last_error_code: str | None = None

    # -- status -----------------------------------------------------------

    def status(self) -> dict[str, object]:
        counters = self.store.curator_counter_totals()
        if self.llm is None:
            if not self.settings.chat_api_key:
                state, reason = "degraded", REASON_KEY_MISSING
            else:
                state, reason = "degraded", REASON_INIT_ERROR
        elif self._last_llm_ok is False:
            state, reason = "degraded", (self._last_error_code or REASON_LLM_ERROR)
        else:
            state, reason = "ready", None
        return {
            "enabled": True,
            "state": state,
            "reason_code": reason,
            "model": self.model,
            "counters": counters,
        }

    # -- run --------------------------------------------------------------

    def run_session(self, session_id: str, *, force: bool = False) -> CuratorRunResult:
        result = CuratorRunResult()
        state = self.store.get_curator_state(session_id)
        seq = state.last_message_seq if state is not None else 0
        total = self.store.count_session_messages(session_id)
        if total <= seq:
            result.status = "no_messages"
            return result
        if self.llm is None:
            result.status = "llm_unavailable"
            result.error_code = (
                REASON_KEY_MISSING if not self.settings.chat_api_key else REASON_INIT_ERROR
            )
            result.llm_errors = 1
            return result

        from memoryos_lite.curator.curate import MAX_WINDOW_ACTIVITIES

        window_size = min(self.settings.memoryos_curator_window_messages, MAX_WINDOW_ACTIVITIES)
        run_id = new_id("crun")
        active: dict[str, CuratedMemoryRow] = {
            row.id: row for row in self.store.list_active_curated_memories(session_id)
        }
        run_counted = False

        while seq < total:
            window = self.store.list_messages_for_curation(
                session_id,
                after_seq=seq,
                limit=window_size,
            )
            if not window:
                break
            if len(window) < window_size and not force and not self._idle_due(window[0]):
                result.status = "ok" if result.windows else "idle"
                return result
            window_ids = {message.id for message in window}
            context = [
                message
                for message in (
                    self.store.list_messages_for_curation(
                        session_id,
                        after_seq=max(0, seq - CONTEXT_MESSAGES),
                        limit=min(CONTEXT_MESSAGES, seq),
                    )
                    if seq > 0
                    else []
                )
                if message.id not in window_ids
            ]
            first_position = seq - len(context) + 1
            infos = {
                message.id: _message_info(message, first_position + offset)
                for offset, message in enumerate([*context, *window])
            }

            try:
                counts = self._curate_window(session_id, context, window, active, infos)
            except ImportError:
                self._mark_llm_call(False, REASON_REQUIRES_LANGGRAPH)
                result.status = "llm_unavailable"
                result.error_code = REASON_REQUIRES_LANGGRAPH
                result.llm_errors += 1
                return result
            except (_UnusableReply, CuratorLLMError) as exc:
                schema_failure = isinstance(exc, _UnusableReply)
                skipped = self._register_window_failure(
                    session_id=session_id,
                    seq=seq,
                    window=window,
                    run_id=run_id,
                    runs=0 if run_counted else 1,
                    schema_failure=schema_failure,
                )
                if schema_failure:
                    result.rejected_schema += 1
                else:
                    result.llm_errors += 1
                result.status = "skipped" if skipped else "failed"
                result.error_code = REASON_SCHEMA_ERROR if schema_failure else REASON_LLM_ERROR
                return result

            result.windows += 1
            result.operations += counts.proposals
            created = self.store.apply_curator_window(
                session_id=session_id,
                run_id=run_id,
                model=self.model,
                last_message_seq=seq + len(window),
                writes=counts.writes,
                ops_count=counts.proposals,
                runs=0 if run_counted else 1,
                rejected_grounding=counts.rejected,
                rejected_schema=0,
                llm_errors=0,
                error_code=None,
            )
            run_counted = True
            result.added += counts.added
            result.superseded += counts.superseded
            result.noop += counts.noop
            result.rejected_grounding += counts.rejected
            result.stale += counts.stale
            result.status = "ok"
            self._window_failures.pop((session_id, seq), None)
            for write, row in zip(counts.writes, created, strict=True):
                for target in (write.supersedes_id, *write.also_supersedes):
                    if target is not None:
                        active.pop(target, None)
                if row.status == "active":
                    active[row.id] = row
                self._trace_written(session_id, row, infos)
            self._trace(
                session_id,
                "curator_window_processed",
                {
                    "window_start_seq": seq,
                    "window_size": len(window),
                    "operations": counts.proposals,
                    "added": counts.added,
                    "superseded": counts.superseded,
                    "noop": counts.noop,
                    "rejected_grounding": counts.rejected,
                    "rejected_schema": 0,
                    "stale": counts.stale,
                },
            )
            seq += len(window)

        return result

    # -- internals --------------------------------------------------------

    def _idle_due(self, oldest: Message) -> bool:
        created = oldest.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        waited_s = (utc_now() - created).total_seconds()
        return waited_s >= self.settings.memoryos_curator_idle_flush_s

    def _mark_llm_call(self, ok: bool, error_code: str | None) -> None:
        self._last_llm_ok = ok
        if ok:
            self._last_error_code = None
        elif error_code is not None:
            self._last_error_code = error_code

    def _curate_window(
        self,
        session_id: str,
        context: list[Message],
        window: list[Message],
        active: dict[str, CuratedMemoryRow],
        infos: dict[str, _MessageInfo],
    ) -> _WindowCounts:
        """One room-profile curate request for this window, mapped to store writes."""

        from memoryos_lite.curator.curate import MAX_ACTIVE_MEMORIES, MAX_REPAIRS, CurateRequest
        from memoryos_lite.curator.graph import REPLY_NOT_JSON, run_curate

        llm = self.llm
        if llm is None:
            raise CuratorLLMError("curator LLM unavailable")
        max_active = min(self.settings.memoryos_curator_max_active_in_prompt, MAX_ACTIVE_MEMORIES)
        request = CurateRequest(
            scope_id=session_id,
            profile="room",
            active=[_curate_memory(row) for row in list(active.values())[-max_active:]],
            context=[_curate_activity(message, infos[message.id]) for message in context],
            window=[_curate_activity(message, infos[message.id]) for message in window],
            max_repairs=MAX_REPAIRS,
        )
        try:
            response = run_curate(request, llm)
        except CuratorLLMError:
            self._mark_llm_call(False, REASON_LLM_ERROR)
            raise
        except ImportError:
            raise
        except Exception as exc:
            self._mark_llm_call(False, REASON_LLM_ERROR)
            raise CuratorLLMError(f"provider call failed: {type(exc).__name__}") from exc
        if REPLY_NOT_JSON in response.diagnostics.final_violations:
            self._mark_llm_call(False, REASON_SCHEMA_ERROR)
            raise _UnusableReply
        self._mark_llm_call(True, None)
        return _window_writes(response, active)

    def _trace_written(
        self,
        session_id: str,
        row: CuratedMemoryRow,
        infos: dict[str, _MessageInfo],
    ) -> None:
        """Record one committed memory and how long its newest source waited.

        ``source_lag_s`` is the time from the newest cited message of this
        window being ingested to the memory being committed, e.g. a gate
        failure becoming an available lesson.
        """

        cited = [
            infos[source["message_id"]] for source in row.sources if source["message_id"] in infos
        ]
        newest = max(cited, key=lambda info: info.created_at, default=None)
        lag: float | None = None
        if newest is not None:
            ingested = newest.created_at
            if ingested.tzinfo is None:
                ingested = ingested.replace(tzinfo=UTC)
            committed = row.created_at
            if committed.tzinfo is None:
                committed = committed.replace(tzinfo=UTC)
            lag = round(max(0.0, (committed - ingested).total_seconds()), 3)
        self._trace(
            session_id,
            "curator_memory_written",
            {
                "memory_id": row.id,
                "kind": row.kind,
                "topic_key": row.topic_key,
                "status": row.status,
                "version": row.version,
                "occurrences": row.occurrences,
                "supersedes_id": row.supersedes_id,
                "activity_types": sorted(
                    {info.activity_type for info in cited if info.activity_type is not None}
                ),
                "source_lag_s": lag,
            },
        )

    def _register_window_failure(
        self,
        *,
        session_id: str,
        seq: int,
        window: list[Message],
        run_id: str,
        runs: int,
        schema_failure: bool,
    ) -> bool:
        """Record a failed window; return True when the window was skipped."""

        code = REASON_SCHEMA_ERROR if schema_failure else REASON_LLM_ERROR
        key = (session_id, seq)
        attempt = self._window_failures.get(key, 0) + 1
        if attempt >= SKIP_AFTER_FAILURES:
            self._window_failures.pop(key, None)
            self.store.apply_curator_window(
                session_id=session_id,
                run_id=run_id,
                model=self.model,
                last_message_seq=seq + len(window),
                writes=[],
                runs=runs,
                rejected_schema=1 if schema_failure else 0,
                llm_errors=0 if schema_failure else 1,
                error_code=code,
            )
            self._trace(
                session_id,
                "curator_window_skipped",
                {
                    "window_start_seq": seq,
                    "window_size": len(window),
                    "attempts": attempt,
                    "reason_code": code,
                },
            )
            return True
        self._window_failures[key] = attempt
        self.store.bump_curator_state(
            session_id=session_id,
            runs=runs,
            rejected_schema=1 if schema_failure else 0,
            llm_errors=0 if schema_failure else 1,
            error_code=code,
        )
        self._trace(
            session_id,
            code,
            {
                "window_start_seq": seq,
                "window_size": len(window),
                "attempt": attempt,
            },
        )
        return False

    def _trace(self, session_id: str, event_type: str, payload: dict[str, object]) -> None:
        self.store.add_trace(
            TraceEvent(
                session_id=session_id,
                event_type=event_type,
                payload={**current_observability_context(), **payload},
            )
        )


def _curate_activity(message: Message, info: _MessageInfo) -> CurateActivity:
    from memoryos_lite.curator.curate import ACTIVITY_TYPES, CurateActivity
    from memoryos_lite.curator.prompt import speaker_label

    label, speaker_kind = speaker_label(message)
    activity_type = info.activity_type if info.activity_type in ACTIVITY_TYPES else "message"
    return CurateActivity(
        id=message.id,
        seq=info.version,
        type=activity_type,  # type: ignore[arg-type]
        speaker=f"{label}, {speaker_kind}"[:128],
        text=message.content or " ",
    )


def _curate_memory(row: CuratedMemoryRow) -> CurateMemory:
    from memoryos_lite.curator.curate import CurateMemory, CurateSource

    return CurateMemory(
        id=row.id,
        kind=row.kind if row.kind in MEMORY_KINDS else "fact",  # type: ignore[arg-type]
        topic_key=row.topic_key,
        statement=row.statement,
        version=max(0, row.version),
        occurrences=max(1, row.occurrences),
        sources=[
            CurateSource(activity_id=source["message_id"], quote=source["quote"])
            for source in row.sources
            if source.get("message_id") and source.get("quote")
        ],
    )


def _window_writes(response: CurateResponse, active: dict[str, CuratedMemoryRow]) -> _WindowCounts:
    """Map new memory versions to store writes; other same-topic rows retire too."""

    diagnostics = response.diagnostics
    counts = _WindowCounts(
        noop=diagnostics.noop_memories,
        stale=diagnostics.stale_memories,
        rejected=diagnostics.rejected_memories,
    )
    for version in response.memories:
        also: tuple[str, ...] = ()
        if version.supersedes_id is not None:
            is_lesson = version.kind == "lesson"
            also = tuple(
                row.id
                for row in active.values()
                if row.topic_key == version.topic_key
                and (row.kind == "lesson") == is_lesson
                and row.id != version.supersedes_id
            )
            counts.superseded += 1
        else:
            counts.added += 1
        counts.writes.append(
            CuratedMemoryWrite(
                kind=version.kind,
                topic_key=version.topic_key,
                statement=version.statement,
                sources=[
                    {"message_id": source.activity_id, "quote": source.quote}
                    for source in version.sources
                ],
                supersedes_id=version.supersedes_id,
                version=version.version,
                occurrences=version.occurrences,
                also_supersedes=also,
            )
        )
    counts.proposals = len(counts.writes) + counts.noop + counts.stale + counts.rejected
    return counts


__all__ = [
    "Curator",
    "CuratorRunResult",
]
