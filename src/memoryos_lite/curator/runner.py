"""Synchronous curator: windowed extraction, grounding, and consolidation.

``Curator.run_session`` is the single entry point used by the background
worker, the eval harness, and tests.  It processes only messages after the
stored watermark, one window of ``memoryos_curator_window_messages`` at a
time, and advances the watermark only for windows whose LLM output was
accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from memoryos_lite.config import Settings
from memoryos_lite.curator.grounding import ground_quote, normalize_text
from memoryos_lite.curator.llm import CuratorLLM, CuratorLLMError, CuratorSchemaError
from memoryos_lite.curator.prompt import (
    ACTIVE_HEADER_DETERMINISTIC,
    ACTIVE_HEADER_LLM_SUPERSEDE,
    CURATOR_SYSTEM_PROMPT,
    CURATOR_SYSTEM_PROMPT_LLM_SUPERSEDE,
    build_user_prompt,
)
from memoryos_lite.observability import current_observability_context
from memoryos_lite.schemas import (
    LESSON_SOURCE_ACTIVITY_TYPES,
    Message,
    TraceEvent,
    new_id,
    utc_now,
)
from memoryos_lite.store import MemoryStore
from memoryos_lite.store_curator import CuratedMemoryRow, CuratedMemoryWrite

MEMORY_KINDS = frozenset({"fact", "decision", "rule", "preference", "lesson"})
CURATOR_OPS = frozenset({"add", "update", "noop"})
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
SCHEMA_ATTEMPTS = 2

REASON_KEY_MISSING = "curator_llm_key_missing"
REASON_INIT_ERROR = "curator_llm_init_error"
REASON_LLM_ERROR = "curator_llm_error"
REASON_SCHEMA_ERROR = "curator_schema_error"


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
class _ValidatedOp:
    status: str
    write: CuratedMemoryWrite | None = None


@dataclass
class _WindowCounts:
    added: int = 0
    superseded: int = 0
    noop: int = 0
    rejected_grounding: int = 0
    rejected_schema: int = 0
    stale: int = 0
    writes: list[CuratedMemoryWrite] = field(default_factory=list)


@dataclass(frozen=True)
class _MessageInfo:
    content: str
    version: int
    created_at: datetime
    activity_type: str | None


def _occurrences_in(fresh: list[dict[str, str]], infos: dict[str, _MessageInfo]) -> int:
    """Occurrences a lesson gains from newly cited sources.

    With typed activities (module sessions) each newly cited review objection or
    gate failure is one occurrence, so a plain message cited alongside adds none.
    Untyped sessions count one occurrence per proposal that cites anything new.
    """

    types = [
        info.activity_type
        for source in fresh
        if (info := infos.get(source["message_id"])) is not None
    ]
    if not any(types):
        return 1
    return sum(1 for activity_type in types if activity_type in LESSON_SOURCE_ACTIVITY_TYPES)


def _nullish(value: object) -> bool:
    return value is None or value == "" or value == "null"


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
        # Set per run_session: the module scope id of a module session.
        self._module_id: str | None = None

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
        session = self.store.get_session(session_id)
        self._module_id = (
            session.scope.id
            if session is not None and session.scope is not None and session.scope.type == "module"
            else None
        )
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

        window_size = self.settings.memoryos_curator_window_messages
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
            context = self.store.list_messages_for_curation(
                session_id,
                after_seq=max(0, seq - CONTEXT_MESSAGES),
                limit=min(CONTEXT_MESSAGES, seq),
            )
            first_position = seq - len(context) + 1
            infos = {
                message.id: _message_info(message, first_position + offset)
                for offset, message in enumerate([*context, *window])
            }
            content_by_id = {message_id: info.content for message_id, info in infos.items()}

            try:
                operations = self._complete_operations(context, window, active)
            except (CuratorSchemaError, CuratorLLMError) as exc:
                skipped = self._register_window_failure(
                    session_id=session_id,
                    seq=seq,
                    window=window,
                    run_id=run_id,
                    runs=0 if run_counted else 1,
                    schema_failure=isinstance(exc, CuratorSchemaError),
                )
                if isinstance(exc, CuratorSchemaError):
                    result.rejected_schema += 1
                else:
                    result.llm_errors += 1
                result.status = "skipped" if skipped else "failed"
                result.error_code = (
                    REASON_SCHEMA_ERROR if isinstance(exc, CuratorSchemaError) else REASON_LLM_ERROR
                )
                return result

            result.windows += 1
            result.operations += len(operations)
            if self.settings.resolved_curator_consolidation == "deterministic":
                counts = self._consolidate(operations, active, infos)
            else:
                counts = self._validate_operations(operations, active, content_by_id, infos)
            created = self.store.apply_curator_window(
                session_id=session_id,
                run_id=run_id,
                model=self.model,
                last_message_seq=seq + len(window),
                writes=counts.writes,
                ops_count=len(operations),
                runs=0 if run_counted else 1,
                rejected_grounding=counts.rejected_grounding,
                rejected_schema=counts.rejected_schema,
                llm_errors=0,
                error_code=None,
            )
            run_counted = True
            result.added += counts.added
            result.superseded += counts.superseded
            result.noop += counts.noop
            result.rejected_grounding += counts.rejected_grounding
            result.rejected_schema += counts.rejected_schema
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
                    "operations": len(operations),
                    "added": counts.added,
                    "superseded": counts.superseded,
                    "noop": counts.noop,
                    "rejected_grounding": counts.rejected_grounding,
                    "rejected_schema": counts.rejected_schema,
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

    def _complete_operations(
        self,
        context: list[Message],
        window: list[Message],
        active: dict[str, CuratedMemoryRow],
    ) -> list[object]:
        llm = self.llm
        if llm is None:
            raise CuratorLLMError("curator LLM unavailable")
        max_active = self.settings.memoryos_curator_max_active_in_prompt
        active_rows = list(active.values())[-max_active:]
        deterministic = self.settings.resolved_curator_consolidation == "deterministic"
        user = build_user_prompt(
            context_messages=context,
            window_messages=window,
            active_memories=active_rows,
            active_header=(
                ACTIVE_HEADER_DETERMINISTIC if deterministic else ACTIVE_HEADER_LLM_SUPERSEDE
            ),
            module_id=self._module_id,
        )
        system = CURATOR_SYSTEM_PROMPT if deterministic else CURATOR_SYSTEM_PROMPT_LLM_SUPERSEDE
        last_schema_error: CuratorSchemaError | None = None
        for _attempt in range(SCHEMA_ATTEMPTS):
            try:
                payload = llm.complete_json(system, user)
            except CuratorSchemaError as exc:
                self._mark_llm_call(False, REASON_SCHEMA_ERROR)
                last_schema_error = exc
                continue
            except CuratorLLMError:
                self._mark_llm_call(False, REASON_LLM_ERROR)
                raise
            except Exception as exc:
                self._mark_llm_call(False, REASON_LLM_ERROR)
                raise CuratorLLMError(f"provider call failed: {type(exc).__name__}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("operations"), list):
                self._mark_llm_call(False, REASON_SCHEMA_ERROR)
                last_schema_error = CuratorSchemaError(
                    "curator response missing an operations list"
                )
                continue
            self._mark_llm_call(True, None)
            return list(payload["operations"])
        if last_schema_error is None:
            last_schema_error = CuratorSchemaError("curator response unusable")
        raise last_schema_error

    def _consolidate(
        self,
        operations: list[object],
        active: dict[str, CuratedMemoryRow],
        infos: dict[str, _MessageInfo],
    ) -> _WindowCounts:
        """Deterministic consolidation: the LLM only proposes; versions decide.

        Every grounded proposal gets ``version`` = the newest cited message's
        order.  Non-lesson proposals sharing a topic_key keep only the newest
        statement: it supersedes every older active row on that key, and a
        proposal older than the active row is stored already superseded.
        Lessons never replace each other: a repeat occurrence (a proposal that
        cites at least one new message) merges into the active lesson and
        increments ``occurrences``.
        """

        counts = _WindowCounts()
        content_by_id = {message_id: info.content for message_id, info in infos.items()}
        groups: dict[tuple[bool, str], list[CuratedMemoryWrite]] = {}
        for raw in operations:
            outcome = self._validate_operation(raw, {}, content_by_id, infos, normalize_keys=True)
            if outcome.status == "rejected_grounding":
                counts.rejected_grounding += 1
            elif outcome.status == "rejected_schema":
                counts.rejected_schema += 1
            elif outcome.status == "noop":
                counts.noop += 1
            elif outcome.write is not None:
                write = outcome.write
                groups.setdefault((write.kind == "lesson", write.topic_key), []).append(write)

        for (is_lesson, topic_key), proposals in groups.items():
            same_topic = [
                row
                for row in active.values()
                if row.topic_key == topic_key and (row.kind == "lesson") == is_lesson
            ]
            if is_lesson:
                self._merge_lessons(proposals, same_topic, counts, infos)
            else:
                self._keep_newest(proposals, same_topic, counts)
        return counts

    @staticmethod
    def _keep_newest(
        proposals: list[CuratedMemoryWrite],
        same_topic: list[CuratedMemoryRow],
        counts: _WindowCounts,
    ) -> None:
        # Within one window only the newest proposal per topic survives; ties
        # go to the later proposal.  Older ones in the same window are noops.
        winner = proposals[0]
        for proposal in proposals[1:]:
            if proposal.version >= winner.version:
                winner = proposal
        counts.noop += len(proposals) - 1
        statement_key = normalize_text(winner.statement)
        if any(normalize_text(row.statement) == statement_key for row in same_topic):
            counts.noop += 1
            return
        if not same_topic:
            counts.writes.append(winner)
            counts.added += 1
            return
        newest = max(same_topic, key=lambda row: (row.version, row.created_at, row.id))
        if winner.version >= newest.version:
            others = tuple(row.id for row in same_topic if row.id != newest.id)
            counts.writes.append(replace(winner, supersedes_id=newest.id, also_supersedes=others))
            counts.superseded += 1
        else:
            counts.writes.append(replace(winner, superseded_by_id=newest.id))
            counts.stale += 1

    @staticmethod
    def _merge_lessons(
        proposals: list[CuratedMemoryWrite],
        same_topic: list[CuratedMemoryRow],
        counts: _WindowCounts,
        infos: dict[str, _MessageInfo],
    ) -> None:
        prior = max(same_topic, key=lambda row: (row.version, row.created_at, row.id), default=None)
        sources = list(prior.sources) if prior is not None else []
        occurrences = prior.occurrences if prior is not None else 0
        version = prior.version if prior is not None else 0
        statement = prior.statement if prior is not None else proposals[0].statement
        kind = proposals[0].kind
        seen = {source["message_id"] for source in sources}
        merged_any = False
        new_occurrences = 0
        for proposal in proposals:
            fresh = [source for source in proposal.sources if source["message_id"] not in seen]
            if not fresh:
                counts.noop += 1
                continue
            sources.extend(fresh)
            seen.update(source["message_id"] for source in fresh)
            merged_any = True
            new_occurrences += _occurrences_in(fresh, infos)
            version = max(version, proposal.version)
            # The newest wording of a repeated lesson is the one shown.
            statement = proposal.statement
        if not merged_any:
            return
        merged = CuratedMemoryWrite(
            kind=kind,
            topic_key=proposals[0].topic_key,
            statement=statement,
            sources=sources[-MAX_LESSON_SOURCES:],
            version=version,
            occurrences=occurrences + new_occurrences,
            supersedes_id=prior.id if prior is not None else None,
            also_supersedes=tuple(
                row.id for row in same_topic if prior is not None and row.id != prior.id
            ),
        )
        counts.writes.append(merged)
        if prior is None:
            counts.added += 1
        else:
            counts.superseded += 1

    def _validate_operations(
        self,
        operations: list[object],
        active: dict[str, CuratedMemoryRow],
        content_by_id: dict[str, str],
        infos: dict[str, _MessageInfo],
    ) -> _WindowCounts:
        counts = _WindowCounts()
        claimed_supersedes: set[str] = set()
        window_statements: set[tuple[str, str]] = set()
        for raw in operations:
            outcome = self._validate_operation(raw, active, content_by_id, infos)
            if outcome.status == "rejected_grounding":
                counts.rejected_grounding += 1
            elif outcome.status == "rejected_schema":
                counts.rejected_schema += 1
            elif outcome.status == "noop":
                counts.noop += 1
            elif outcome.write is not None:
                write = outcome.write
                statement_key = (write.topic_key, normalize_text(write.statement))
                if statement_key in window_statements:
                    # The same memory proposed twice in one window.
                    counts.noop += 1
                    continue
                window_statements.add(statement_key)
                target = write.supersedes_id
                if target is not None:
                    if target in claimed_supersedes:
                        # One active memory can be superseded only once per
                        # window; a second claim is kept as a separate memory.
                        write = replace(write, supersedes_id=None)
                    else:
                        claimed_supersedes.add(target)
                counts.writes.append(write)
                if write.supersedes_id is None:
                    counts.added += 1
                else:
                    counts.superseded += 1
        return counts

    def _validate_operation(
        self,
        raw: object,
        active: dict[str, CuratedMemoryRow],
        content_by_id: dict[str, str],
        infos: dict[str, _MessageInfo],
        *,
        normalize_keys: bool = False,
    ) -> _ValidatedOp:
        """Validate and ground one operation.

        With ``normalize_keys`` (deterministic mode) topic keys are
        canonicalized and any ``supersedes`` field is ignored: consolidation
        happens afterwards, from versions only.
        """

        if not isinstance(raw, dict):
            return _ValidatedOp("rejected_schema")
        op = raw.get("op")
        if op not in CURATOR_OPS:
            return _ValidatedOp("rejected_schema")
        if op == "noop":
            return _ValidatedOp("noop")
        kind = raw.get("kind")
        if kind not in MEMORY_KINDS:
            return _ValidatedOp("rejected_schema")
        raw_topic_key = raw.get("topic_key")
        if not isinstance(raw_topic_key, str):
            return _ValidatedOp("rejected_schema")
        if normalize_keys:
            normalized = normalize_topic_key(raw_topic_key)
            if normalized is None:
                return _ValidatedOp("rejected_schema")
            topic_key = normalized
        else:
            topic_key = raw_topic_key.strip()
            if not topic_key or len(topic_key) > MAX_TOPIC_KEY_CHARS:
                return _ValidatedOp("rejected_schema")
        statement = raw.get("statement")
        if not isinstance(statement, str):
            return _ValidatedOp("rejected_schema")
        statement = statement.strip()
        if not statement or len(statement) > MAX_STATEMENT_CHARS:
            return _ValidatedOp("rejected_schema")
        sources_raw = raw.get("sources")
        if not isinstance(sources_raw, list) or not 1 <= len(sources_raw) <= MAX_SOURCES:
            return _ValidatedOp("rejected_schema")

        sources: list[dict[str, str]] = []
        seen_sources: set[tuple[str, str]] = set()
        for source in sources_raw:
            if not isinstance(source, dict):
                return _ValidatedOp("rejected_schema")
            message_id = source.get("message_id")
            quote = source.get("quote")
            if not isinstance(message_id, str) or not isinstance(quote, str):
                return _ValidatedOp("rejected_schema")
            repaired = ground_quote(content_by_id, message_id, quote)
            if repaired is None:
                return _ValidatedOp("rejected_grounding")
            key = (message_id, repaired)
            if key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({"message_id": message_id, "quote": repaired})
        if not sources:
            return _ValidatedOp("rejected_grounding")
        if (
            kind == "lesson"
            and self._module_id is not None
            and not any(
                infos[source["message_id"]].activity_type in LESSON_SOURCE_ACTIVITY_TYPES
                for source in sources
            )
        ):
            # Module lessons must quote a review objection or a failing gate.
            return _ValidatedOp("rejected_grounding")
        version = max(infos[source["message_id"]].version for source in sources)
        if normalize_keys:
            return _ValidatedOp(
                "write",
                CuratedMemoryWrite(
                    kind=kind,
                    topic_key=topic_key,
                    statement=statement,
                    sources=sources,
                    version=version,
                ),
            )

        supersedes_id: str | None = None
        supersedes = raw.get("supersedes")
        if op == "update":
            if isinstance(supersedes, str) and supersedes in active:
                supersedes_id = supersedes
            # An unknown target downgrades the update to an add.
        elif not _nullish(supersedes):
            return _ValidatedOp("rejected_schema")

        if supersedes_id is None:
            statement_key = normalize_text(statement)
            for existing in active.values():
                if (
                    existing.topic_key == topic_key
                    and normalize_text(existing.statement) == statement_key
                ):
                    return _ValidatedOp("noop")

        return _ValidatedOp(
            "write",
            CuratedMemoryWrite(
                kind=kind,
                topic_key=topic_key,
                statement=statement,
                sources=sources,
                supersedes_id=supersedes_id,
                version=version,
            ),
        )

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


__all__ = [
    "Curator",
    "CuratorRunResult",
]
