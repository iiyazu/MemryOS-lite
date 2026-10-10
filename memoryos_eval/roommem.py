"""RoomMem evaluation harness.

RoomMem measures a memory curator that reads multi-agent chat-room
transcripts (a human plus 2-3 AI agents collaborating on a project) and must
store the right long-term memories, merge duplicates, supersede outdated ones
and ignore noise, then answer probe questions from memory.

This module replays the dataset through an in-process :class:`SessionMemoryService`
using the calls xmuse v1 made over HTTP (sessions, ingest, archive ingest and
attachments, and build-context with the ``source_evidence/v2`` projection);
those routes were removed in 0.5.0, the service methods remain.

Arms
----
``raw``
    Mirrors the xmuse Room host today: session messages plus one archive
    document per message (the document outbox) and archive-only retrieval.
``raw_project``
    Like ``raw``, but every probe session also gets the per-message archive
    documents of all rooms in the same project attached (own-room documents
    for new-room sessions included).  Documents are ingested once per project
    per repeat in a shared per-project service; other projects are never
    visible.  ``stale@8`` and the judge's ``stale`` label use the same
    superseded-source-without-successor rule as every other arm.
``oracle``
    Upper bound used by tests and CI: the curated memories ARE the room's gold
    memories, mapped onto the ingested MemoryOS message ids.
``curated``
    Runs a :class:`CuratedMemorySource` registered by name through
    :func:`register_curated_source`.  The built-in ``default`` source runs the
    real :class:`memoryos_lite.curator.Curator` on the room session (one window
    of ``--curator-window`` messages,
    ``force=True`` for the tail) and maps its rows to
    :class:`CuratedMemoryView`.  With ``--fake-llm`` it uses a deterministic
    fake curator LLM; otherwise it requires ``MEMORYOS_LLM_PROVIDER`` set to
    ``deepseek`` or ``opencode`` and routes every call through the same
    on-disk cache as the answerer and judge.  The CLI fails with a clear
    message when an unregistered name is requested.

Reports written by :func:`run_roommem`: ``results.jsonl`` (one row per probe,
carrying the full, untruncated evidence texts and the exact answerer output),
``memories.jsonl`` (one row per oracle/curated memory with dataset-mapped
sources, the matched gold id and the judge label for unmatched memories),
``write_side.json``, ``summary.json`` and ``summary.md``.  When provider
clients are used, per-role token usage and latency are aggregated into the
summary; ``--price-in-per-mtok``/``--price-out-per-mtok`` turn them into an
estimated cost (prices are never guessed in code).

Known limitations (fixed paragraph, repeated in every report): the dataset is
LLM-authored with a single reviewer; the curated arm's cross-room delivery
(rule -> project, preference -> user) assumes operator approval; the answerer
and the curator share one model family (the configured provider's model).
"""

from __future__ import annotations

import inspect
import json
import math
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memoryos_eval.ask import AskRequest, AskResponse, ask_with, render_ask_item
from memoryos_eval.memory.service import SessionMemoryService
from memoryos_lite.chat_models import build_chat_openai, message_text
from memoryos_lite.config import Settings, get_settings
from memoryos_lite.curator import Curator, CuratorLLM, build_curator_llm
from memoryos_lite.curator.curate import normalize_topic_key
from memoryos_lite.curator.grounding import MIN_QUOTE_CHARS
from memoryos_lite.retrieval.supersede import SupersededQuote, superseded_quotes
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveDocumentIngestRequest,
    ArchiveIdentityArchive,
    ArchiveSourceRefPayload,
    MessageCreate,
    Role,
    deterministic_ids,
)
from memoryos_lite.source_evidence import build_source_evidence

ROOM_KINDS: tuple[str, ...] = ("fact", "decision", "rule", "preference", "lesson")
ROOM_SCOPES: tuple[str, ...] = ("room", "project", "user")
FIXED_SCOPE_BY_KIND: dict[str, str] = {"rule": "project", "preference": "user"}
NOISE_TYPES: tuple[str, ...] = (
    "rejected_proposal",
    "hypothetical",
    "question",
    "chitchat",
    "agent_instruction",
    "restatement",
    "tentative",
    "plan_step",
)
ASKED_IN_VALUES: tuple[str, ...] = ("same_room", "new_room_same_project")
ARM_VALUES: tuple[str, ...] = ("raw", "raw_project", "oracle", "curated", "full_context")
#: Arms that carry raw per-message activity documents instead of curated
#: memory documents (no curated memory id can ever appear in their evidence).
RAW_LIKE_ARMS: tuple[str, ...] = ("raw", "raw_project", "full_context")
#: How the curated arm builds evidence: ``plain`` source_evidence/v2, ``demote``
#: with superseded-source demotion, ``agentic`` through the ask graph. Each mode
#: answers from the same curated memories (the curator runs once).
EVIDENCE_MODES: tuple[str, ...] = ("plain", "demote", "agentic")
#: Arms whose evidence is the whole project transcript, not a retrieval result.
FULL_CONTEXT_LAYER = "full_history"
EMBEDDING_VALUES: tuple[str, ...] = ("none", "fastembed")

SPLIT_PRESETS: dict[str, tuple[str, ...]] = {
    "dev": tuple(f"rm{index:02d}" for index in range(1, 7)),
    "test": tuple(f"rm{index:02d}" for index in range(7, 13)),
    # Old values are mentioned again after they changed ("we used to use X").
    "trap": tuple(f"rm{index:02d}" for index in range(13, 17)),
}
#: Cosine thresholds reported for FastEmbed "possible conflict" flags.
CONFLICT_THRESHOLDS: tuple[float, ...] = (0.75, 0.8, 0.85, 0.9)

#: Curator run counters recorded per room for the curated arm.
CURATOR_COUNTER_KEYS: tuple[str, ...] = (
    "windows",
    "added",
    "superseded",
    "noop",
    "rejected_grounding",
    "rejected_schema",
    "llm_errors",
)

#: Task text and retrieval parameters xmuse sends to ``/build-context``.
XMUSE_TASK = "Recall prior source-backed Room evidence relevant to this observation."
XMUSE_EVIDENCE_BUDGET = 800
MAX_SOURCE_EVIDENCE_ITEMS = 8

XMUSE_MESSAGE_ID_PREFIX = "xmuse-room-message-"
XMUSE_ACTIVITY_DOC_PREFIX = "xmuse-room-activity-"
XMUSE_MEMORY_DOC_PREFIX = "xmuse-room-memory-candidate-"

CITATION_RE = re.compile(r"\[(\d{1,4})\]")
_TOPIC_KEY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
_MESSAGE_ID_RE = re.compile(r"^m(\d{2,4})$")

JUDGE_LABELS: tuple[str, ...] = ("correct", "stale", "missing", "wrong")
UNMATCHED_LABELS: tuple[str, ...] = ("legit_unannotated", "noise")

LIMITATIONS_ZH = (
    "数据由 LLM 起草，只有单一审阅者；curated arm 的跨 Room 部分假设操作员批准；"
    "answerer、judge 与 curator 使用同一模型家族（见 summary 中的 llm）。"
)
LIMITATIONS_EN = (
    "The dataset is LLM-authored with a single reviewer; the curated arm's "
    "cross-room delivery assumes operator approval; the answerer, judge and "
    "curator share one model family (see the summary's llm)."
)
#: Providers the non-fake LLM roles can use.
REMOTE_LLM_PROVIDERS: tuple[str, ...] = ("deepseek", "opencode")
_MODEL_FIELD_BY_PROVIDER = {"deepseek": "deepseek_model", "opencode": "opencode_model"}


def settings_for_llm_spec(base: Settings, spec: str | None) -> Settings:
    """Apply a ``provider:model[@wire]`` role spec on top of ``base``.

    ``None`` keeps ``base``.  Example specs: ``deepseek:deepseek-v4-flash``,
    ``opencode:muse-spark-1.2-contributor@responses``,
    ``opencode:glm-5.3-flash@chat``.  Keys still come from the environment.
    """

    if spec is None or not spec.strip():
        return base
    provider, sep, rest = spec.strip().partition(":")
    model, _, wire = rest.partition("@")
    provider = provider.strip().lower()
    if not sep or provider not in REMOTE_LLM_PROVIDERS or not model.strip():
        raise RoomMemConfigError(
            f"invalid LLM spec {spec!r}; expected provider:model[@wire] with provider in "
            + ", ".join(REMOTE_LLM_PROVIDERS)
        )
    update: dict[str, Any] = {
        "memoryos_llm_provider": provider,
        _MODEL_FIELD_BY_PROVIDER[provider]: model.strip(),
    }
    if wire.strip():
        if provider != "opencode":
            raise RoomMemConfigError(f"LLM spec {spec!r}: a wire API applies only to opencode")
        update["opencode_wire_api"] = wire.strip()
    resolved = base.model_copy(update=update)
    try:
        _ = resolved.chat_wire_api
    except ValueError as exc:
        raise RoomMemConfigError(f"LLM spec {spec!r}: {exc}") from exc
    return resolved


def llm_spec_label(settings: Settings) -> str:
    label = f"{settings.resolved_llm_provider}:{settings.chat_model}"
    return f"{label}@{settings.chat_wire_api}" if settings.chat_wire_api != "chat" else label


class RoomMemError(ValueError):
    """Base error for RoomMem configuration and runtime problems."""


class RoomMemDataError(RoomMemError):
    """Raised when a RoomMem dataset file is malformed."""


class RoomMemConfigError(RoomMemError):
    """Raised when a RoomMem run is misconfigured (LLM, embedding, curator)."""


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class RoomParticipant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    kind: Literal["human", "agent"]
    name: str = Field(min_length=1)
    vendor: str | None = None


class RoomMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    text: str = Field(min_length=1)


class GoldMemorySource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    message_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class GoldMemory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    kind: str
    scope: str
    topic_key: str
    statement: str = Field(min_length=1)
    sources: list[GoldMemorySource] = Field(min_length=1)
    superseded_by: str | None = None


class NoiseEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    message_id: str = Field(min_length=1)
    type: str
    note: str = Field(min_length=1)


class RoomProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    asked_in: str
    answer_memory_ids: list[str] = Field(min_length=1)
    must_contain: list[str] = Field(min_length=1)
    must_not_contain: list[str] = Field(default_factory=list)


class Room(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    room_id: str = Field(min_length=1)
    title: str = ""
    language: str = "en"
    project: str = ""
    participants: list[RoomParticipant] = Field(min_length=1)
    messages: list[RoomMessage] = Field(min_length=1)
    gold_memories: list[GoldMemory] = Field(min_length=1)
    noise: list[NoiseEntry] = Field(default_factory=list)
    probes: list[RoomProbe] = Field(min_length=1)

    def message(self, message_id: str) -> RoomMessage | None:
        for message in self.messages:
            if message.id == message_id:
                return message
        return None

    def gold_memory(self, memory_id: str) -> GoldMemory | None:
        for memory in self.gold_memories:
            if memory.id == memory_id:
                return memory
        return None

    def participant(self, participant_id: str) -> RoomParticipant | None:
        for participant in self.participants:
            if participant.id == participant_id:
                return participant
        return None

    def noise_message_ids(self) -> frozenset[str]:
        return frozenset(entry.message_id for entry in self.noise)

    def noise_type_by_message(self) -> dict[str, str]:
        types: dict[str, str] = {}
        for entry in self.noise:
            types.setdefault(entry.message_id, entry.type)
        return types

    def has_new_room_probes(self) -> bool:
        return any(probe.asked_in == "new_room_same_project" for probe in self.probes)


def _earliest_message_number(memory: GoldMemory) -> int | None:
    numbers = [
        int(match.group(1))
        for source in memory.sources
        if (match := _MESSAGE_ID_RE.match(source.message_id)) is not None
    ]
    return min(numbers) if numbers else None


def _validate_room(room: Room, *, source: object) -> None:
    errors: list[str] = []
    participants = {participant.id for participant in room.participants}
    if len(participants) != len(room.participants):
        errors.append("duplicate participant ids")
    humans = [p for p in room.participants if p.kind == "human"]
    agents = [p for p in room.participants if p.kind == "agent"]
    if len(humans) != 1:
        errors.append(f"expected exactly 1 human participant, found {len(humans)}")
    if not 1 <= len(agents) <= 3:
        errors.append(f"expected 1-3 agent participants, found {len(agents)}")

    message_ids: list[str] = []
    for index, message in enumerate(room.messages):
        expected = f"m{index + 1:02d}"
        if message.id != expected:
            errors.append(f"message {index} id {message.id!r} should be {expected!r}")
        if message.id in message_ids:
            errors.append(f"duplicate message id {message.id!r}")
        message_ids.append(message.id)
        if message.speaker not in participants:
            errors.append(f"message {message.id}: speaker {message.speaker!r} is not a participant")

    gold_ids: list[str] = []
    for memory in room.gold_memories:
        tag = memory.id
        if memory.id in gold_ids:
            errors.append(f"{tag}: duplicate gold memory id")
        gold_ids.append(memory.id)
        if memory.kind not in ROOM_KINDS:
            errors.append(f"{tag}: kind {memory.kind!r} invalid")
        if memory.scope not in ROOM_SCOPES:
            errors.append(f"{tag}: scope {memory.scope!r} invalid")
        if memory.kind in FIXED_SCOPE_BY_KIND and memory.scope != FIXED_SCOPE_BY_KIND[memory.kind]:
            errors.append(
                f"{tag}: kind {memory.kind!r} requires scope {FIXED_SCOPE_BY_KIND[memory.kind]!r}"
            )
        if not _TOPIC_KEY_RE.match(memory.topic_key):
            errors.append(f"{tag}: topic_key {memory.topic_key!r} must be dotted lowercase")
        for src in memory.sources:
            src_message = room.message(src.message_id)
            if src_message is None:
                errors.append(f"{tag}: source message {src.message_id!r} does not exist")
            elif src.quote not in src_message.text:
                excerpt = src.quote[:60]
                errors.append(
                    f"{tag}: quote is not an exact substring of {src.message_id}: {excerpt!r}"
                )

    gold_by_id = {memory.id: memory for memory in room.gold_memories}
    for memory in room.gold_memories:
        if memory.superseded_by is None:
            continue
        target = gold_by_id.get(memory.superseded_by)
        if target is None:
            errors.append(f"{memory.id}: superseded_by {memory.superseded_by!r} not found")
            continue
        if target is memory:
            errors.append(f"{memory.id}: superseded_by points to itself")
        if target.topic_key != memory.topic_key:
            errors.append(f"{memory.id}: superseded_by target has a different topic_key")
        own = _earliest_message_number(memory)
        other = _earliest_message_number(target)
        if own is not None and other is not None and other <= own:
            errors.append(
                f"{memory.id}: earliest source of superseding memory "
                f"{target.id} (m{other:02d}) does not come later than its own (m{own:02d})"
            )

    for entry in room.noise:
        if room.message(entry.message_id) is None:
            errors.append(f"noise: message {entry.message_id!r} does not exist")
        if entry.type not in NOISE_TYPES:
            errors.append(f"noise: type {entry.type!r} invalid")

    probe_ids: list[str] = []
    superseding_ids = {
        memory.superseded_by for memory in room.gold_memories if memory.superseded_by
    }
    for probe in room.probes:
        tag = probe.id
        if probe.id in probe_ids:
            errors.append(f"{tag}: duplicate probe id")
        probe_ids.append(probe.id)
        if probe.asked_in not in ASKED_IN_VALUES:
            errors.append(f"{tag}: asked_in {probe.asked_in!r} invalid")
        resolved: list[GoldMemory] = []
        for answer_id in probe.answer_memory_ids:
            answer_memory = gold_by_id.get(answer_id)
            if answer_memory is None:
                errors.append(f"{tag}: answer memory {answer_id!r} does not exist")
                continue
            if answer_memory.superseded_by is not None:
                errors.append(f"{tag}: answer memory {answer_id!r} is superseded")
            resolved.append(answer_memory)
        if probe.asked_in == "new_room_same_project":
            for memory in resolved:
                if memory.scope not in {"project", "user"}:
                    errors.append(
                        f"{tag}: new_room_same_project probe references {memory.id} "
                        f"with scope {memory.scope!r}; only project/user scope allowed"
                    )
        lowered = {value.casefold() for value in probe.must_not_contain}
        for value in probe.must_contain:
            if value.casefold() in lowered:
                errors.append(f"{tag}: {value!r} appears in both must_contain and must_not_contain")
        if any(answer_id in superseding_ids for answer_id in probe.answer_memory_ids) and (
            not probe.must_not_contain
        ):
            errors.append(f"{tag}: answer supersedes another memory, must_not_contain required")

    if errors:
        detail = "; ".join(errors)
        raise RoomMemDataError(f"{source}: invalid RoomMem room: {detail}")


def load_room(path: str | Path) -> Room:
    """Load and validate one RoomMem room JSON file."""

    room_path = Path(path)
    try:
        raw = json.loads(room_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RoomMemDataError(f"{room_path}: cannot read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RoomMemDataError(f"{room_path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise RoomMemDataError(f"{room_path}: room file must contain a JSON object")
    try:
        room = Room.model_validate(raw)
    except ValidationError as exc:
        raise RoomMemDataError(f"{room_path}: schema error: {exc}") from exc
    _validate_room(room, source=room_path)
    return room


def load_rooms(
    data_dir: str | Path,
    *,
    room_ids: Sequence[str] | None = None,
) -> list[Room]:
    """Load every ``rm*.json`` room in ``data_dir``, optionally filtered."""

    root = Path(data_dir)
    if not root.is_dir():
        raise RoomMemDataError(f"RoomMem data directory not found: {root}")
    paths = sorted(root.glob("rm*.json"))
    if room_ids:
        wanted = list(room_ids)
        selected = [path for path in paths if path.stem in set(wanted)]
        missing = sorted(set(wanted) - {path.stem for path in selected})
        if missing:
            available = ", ".join(path.stem for path in paths) or "(none)"
            raise RoomMemDataError(
                f"unknown room ids: {', '.join(missing)}; available rooms: {available}"
            )
        paths = selected
    if not paths:
        raise RoomMemDataError(f"no room JSON files (rm*.json) found in {root}")
    rooms = [load_room(path) for path in paths]
    seen: set[str] = set()
    for room in rooms:
        if room.room_id in seen:
            raise RoomMemDataError(f"duplicate room_id {room.room_id!r}")
        seen.add(room.room_id)
    return rooms


def resolve_split(name: str) -> list[str]:
    """Expand a dataset split preset (``dev``/``test``) into room ids."""

    preset = SPLIT_PRESETS.get(name.strip().lower())
    if preset is None:
        valid = ", ".join(sorted(SPLIT_PRESETS))
        raise RoomMemConfigError(f"unknown split {name!r}; valid splits: {valid}")
    return list(preset)


# ---------------------------------------------------------------------------
# Curated memories: protocol, registry, oracle
# ---------------------------------------------------------------------------


class CuratedMemoryView(BaseModel):
    """One long-term memory produced by a curator.

    ``sources`` use the dataset message ids (``mNN``); the harness maps them to
    the ingested MemoryOS messages.  ``status='superseded'`` memories are not
    written into MemoryOS (matching the xmuse supersede filter).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    kind: str
    topic_key: str = ""
    statement: str = Field(min_length=1)
    sources: list[GoldMemorySource] = Field(min_length=1)
    status: Literal["active", "superseded"] = "active"
    supersedes_id: str | None = None


@dataclass(frozen=True)
class CuratedSourceContext:
    """Run-scoped configuration for sources that declare a factory argument.

    The default factory accepts one positional argument of this type so it can
    honour ``--curator-window``, the fake-LLM switch, the per-repeat disk cache
    and an injected curator LLM.  Registered factories with a zero-argument
    signature are called without it.
    """

    window: int
    fake_llm: bool
    repeat: int
    cache_dir: Path | None = None
    llm_factory: Callable[[Settings], CuratorLLM] | None = None
    usage: LLMUsageTracker | None = None
    llm_spec: str | None = None


class CuratedMemorySource(Protocol):
    """Adapter boundary for a real Curator.

    The harness calls :meth:`curate` once per room session, after the room
    transcript has been ingested, and treats the returned views as the
    curator's full memory output for that room.  An optional ``last_counts``
    attribute (mapping or zero-argument callable) may report the curator run
    counters: ``windows``, ``added``, ``superseded``, ``noop``,
    ``rejected_grounding``, ``rejected_schema`` and ``llm_errors``.
    """

    def curate(
        self,
        service: SessionMemoryService,
        session_id: str,
    ) -> list[CuratedMemoryView]: ...


_curated_sources: dict[str, Callable[..., CuratedMemorySource]] = {}


def register_curated_source(name: str, factory: Callable[..., CuratedMemorySource]) -> None:
    """Register a curated-memory source factory under ``name``.

    This is the hook a Curator adapter uses; ``factory()`` must return a fresh
    :class:`CuratedMemorySource` per run.  A factory may declare one positional
    parameter to receive a :class:`CuratedSourceContext`.
    """

    if not name:
        raise RoomMemConfigError("curated source name must not be empty")
    _curated_sources[name] = factory


def unregister_curated_source(name: str) -> None:
    _curated_sources.pop(name, None)


def registered_curated_sources() -> list[str]:
    return sorted(_curated_sources)


def _factory_accepts_context(factory: Callable[..., CuratedMemorySource]) -> bool:
    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    return any(parameter.kind in positional for parameter in parameters)


def build_curated_source(
    name: str,
    *,
    context: CuratedSourceContext | None = None,
) -> CuratedMemorySource:
    factory = _curated_sources.get(name)
    if factory is None:
        available = ", ".join(registered_curated_sources()) or "(none registered)"
        raise RoomMemConfigError(
            f"no curated memory source is registered under {name!r}; "
            f"registered sources: {available}. "
            "A Curator adapter must call "
            "memoryos_eval.roommem.register_curated_source(name, factory) "
            "before running --arm curated."
        )
    if context is not None and _factory_accepts_context(factory):
        return factory(context)
    return factory()


def oracle_curated_memories(room: Room) -> list[CuratedMemoryView]:
    """Upper bound: the room's gold memories as curated views."""

    supersedes: dict[str, str] = {}
    for memory in room.gold_memories:
        if memory.superseded_by is not None:
            supersedes.setdefault(memory.superseded_by, memory.id)
    return [
        CuratedMemoryView(
            id=memory.id,
            kind=memory.kind,
            topic_key=memory.topic_key,
            statement=memory.statement,
            sources=list(memory.sources),
            status="superseded" if memory.superseded_by is not None else "active",
            supersedes_id=supersedes.get(memory.id),
        )
        for memory in room.gold_memories
    ]


def _validate_curated_views(views: Sequence[CuratedMemoryView], *, room: Room) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    for view in views:
        tag = view.id
        if view.id in seen:
            errors.append(f"{tag}: duplicate curated memory id")
        seen.add(view.id)
        if view.kind not in ROOM_KINDS:
            errors.append(f"{tag}: kind {view.kind!r} invalid")
        for source in view.sources:
            message = room.message(source.message_id)
            if message is None:
                errors.append(f"{tag}: source message {source.message_id!r} does not exist")
            elif source.quote not in message.text:
                errors.append(f"{tag}: quote is not an exact substring of {source.message_id}")
    if errors:
        raise RoomMemDataError(
            f"curated source output for room {room.room_id} is invalid: " + "; ".join(errors)
        )


def _curator_counts(source: object) -> dict[str, int]:
    getter = getattr(source, "last_counts", None)
    if callable(getter):
        try:
            raw = getter()
        except Exception:
            return {}
    else:
        raw = getter
    if not isinstance(raw, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key in CURATOR_COUNTER_KEYS:
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            counts[key] = value
    return counts


def _scope_for_kind(kind: str) -> str:
    return FIXED_SCOPE_BY_KIND.get(kind, "room")


# ---------------------------------------------------------------------------
# Built-in curated source: the real Curator on the room session
# ---------------------------------------------------------------------------

_SENTENCE_END_CHARS = ".!?;。！？；\n"


def _first_sentence(text: str) -> str:
    stripped = text.strip()
    for index, char in enumerate(stripped):
        if char in _SENTENCE_END_CHARS:
            return stripped[: index + 1]
    return stripped


class FakeCuratorLLM:
    """Deterministic curator LLM for ``--fake-llm``: one fact per human message.

    Each memory quotes the first sentence of a human message (skipping
    messages whose first sentence is shorter than the curator's minimum quote
    length), so CI exercises the full Curator run without a provider.
    """

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        window = user.split("Messages to curate:\n", 1)[-1]
        memories: list[dict[str, Any]] = []
        for line in window.splitlines():
            match = re.match(r"\[([^\]]+)\] (.+?), (human|agent) \([a-z_]+\): (.*)$", line)
            if match is None or match.group(3) != "human":
                continue
            message_id = match.group(1)
            quote = _first_sentence(match.group(4))
            if len(quote) < MIN_QUOTE_CHARS:
                continue
            memories.append(
                {
                    "kind": "fact",
                    "topic_key": f"roommem.{message_id}",
                    "statement": quote,
                    "sources": [{"activity_id": message_id, "quote": quote}],
                }
            )
        return {"memories": memories}


class FakeRewriteLLM:
    """Deterministic ask rewriter for ``--fake-llm``: never proposes a new query."""

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        return {"query": ""}


class DiskCachedCuratorLLM:
    """Disk cache for curator JSON calls keyed by role/model/prompt/repeat.

    Mirrors :class:`DiskCachedChatClient` and shares its cache directory; the
    ``role`` field keeps curator entries distinct from answerer/judge entries.
    """

    def __init__(
        self,
        inner: CuratorLLM,
        *,
        model: str,
        cache_dir: Path,
        repeat: int = 0,
        usage: LLMUsageTracker | None = None,
        role: str = "curator",
    ) -> None:
        if repeat < 0:
            raise ValueError("repeat index must be non-negative")
        self._inner = inner
        self._model = model
        self._cache_dir = Path(cache_dir)
        self._repeat = repeat
        self._usage = usage
        self._role = role

    def cache_key(self, *, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "role": self._role,
                "model": self._model,
                "system": system,
                "user": user,
                "repeat": self._repeat,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        key = self.cache_key(system=system, user=user)
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            started = time.perf_counter()
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                response = payload.get("response")
                if isinstance(response, dict):
                    self._record(cached=True, started=started)
                    return response
            except (OSError, ValueError):
                pass
        started = time.perf_counter()
        response = self._inner.complete_json(system=system, user=user)
        self._record(cached=False, started=started)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"role": self._role, "model": self._model, "response": response},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return response

    def _record(self, *, cached: bool, started: float) -> None:
        if self._usage is None:
            return
        latency = time.perf_counter() - started
        usage = None if cached else _extract_usage(getattr(self._inner, "last_usage", None))
        self._usage.record(self._role, cached=cached, latency_s=latency, usage=usage)


def _session_dataset_message_ids(service: SessionMemoryService, session_id: str) -> dict[str, str]:
    """Map ingested MemoryOS message ids back to dataset message ids."""

    total = service.store.count_session_messages(session_id)
    messages = service.store.list_messages_for_curation(
        session_id, after_seq=0, limit=max(1, total)
    )
    mapping: dict[str, str] = {}
    for message in messages:
        external_id = message.external_id or ""
        if external_id.startswith(XMUSE_MESSAGE_ID_PREFIX):
            mapping[message.id] = external_id[len(XMUSE_MESSAGE_ID_PREFIX) :]
    return mapping


class CuratorMemorySource:
    """The built-in ``default`` curated source: the real Curator, per room.

    Constructed through :class:`CuratedSourceContext` (one instance per repeat
    so the disk cache sees the right repeat index).  Curator LLM calls go
    through :class:`DiskCachedCuratorLLM`; with ``fake_llm`` a deterministic
    :class:`FakeCuratorLLM` runs uncached.
    """

    def __init__(
        self,
        *,
        window: int,
        fake_llm: bool,
        repeat: int = 0,
        cache_dir: Path | None = None,
        llm_factory: Callable[[Settings], CuratorLLM] | None = None,
        usage: LLMUsageTracker | None = None,
        llm_spec: str | None = None,
    ) -> None:
        self._window = window
        self._fake_llm = fake_llm
        self._repeat = repeat
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._llm_factory = llm_factory
        self._usage = usage
        self._llm_spec = llm_spec
        self._last_counts: dict[str, int] = {}

    @property
    def last_counts(self) -> dict[str, int]:
        return dict(self._last_counts)

    def _curator_settings(self, base: Settings) -> Settings:
        overrides: dict[str, Any] = {
            "data_dir": base.data_dir,
            "memoryos_curator_window_messages": self._window,
        }
        if not self._fake_llm:
            overrides["memoryos_llm_provider"] = base.memoryos_llm_provider
        settings = Settings(**overrides)
        return settings if self._fake_llm else settings_for_llm_spec(settings, self._llm_spec)

    def _build_llm(self, settings: Settings) -> CuratorLLM:
        inner: CuratorLLM
        if self._llm_factory is not None:
            inner = self._llm_factory(settings)
        elif self._fake_llm:
            return FakeCuratorLLM()
        else:
            built = build_curator_llm(settings)
            if built is None:
                raise RoomMemConfigError(
                    f"the curated arm needs {settings.chat_api_key_name} (or run with --fake-llm)"
                )
            inner = built
        if self._cache_dir is None:
            return inner
        return DiskCachedCuratorLLM(
            inner,
            model=settings.chat_model,
            cache_dir=self._cache_dir,
            repeat=self._repeat,
            usage=self._usage,
        )

    def curate(self, service: SessionMemoryService, session_id: str) -> list[CuratedMemoryView]:
        settings = self._curator_settings(service.settings)
        curator = Curator(store=service.store, settings=settings, llm=self._build_llm(settings))
        result = curator.run_session(session_id, force=True)
        self._last_counts = {
            "windows": result.windows,
            "added": result.added,
            "superseded": result.superseded,
            "noop": result.noop,
            "rejected_grounding": result.rejected_grounding,
            "rejected_schema": result.rejected_schema,
            "llm_errors": result.llm_errors,
        }
        dataset_ids = _session_dataset_message_ids(service, session_id)
        views: list[CuratedMemoryView] = []
        for row in service.store.list_curated_memories(session_id, limit=64):
            sources: list[GoldMemorySource] = []
            for source in row.sources:
                memoryos_id = source.get("message_id", "")
                dataset_id = dataset_ids.get(memoryos_id)
                if dataset_id is None:
                    raise RoomMemDataError(
                        f"curated memory {row.id} cites unknown message {memoryos_id!r}"
                    )
                sources.append(
                    GoldMemorySource(message_id=dataset_id, quote=str(source.get("quote", "")))
                )
            views.append(
                CuratedMemoryView(
                    id=row.id,
                    kind=row.kind,
                    topic_key=row.topic_key,
                    statement=row.statement,
                    sources=sources,
                    status="superseded" if row.status == "superseded" else "active",
                    supersedes_id=row.supersedes_id,
                )
            )
        return views


def _default_curated_source(
    context: CuratedSourceContext | None = None,
) -> CuratedMemorySource:
    if context is None:
        return CuratorMemorySource(window=12, fake_llm=False)
    return CuratorMemorySource(
        window=context.window,
        fake_llm=context.fake_llm,
        repeat=context.repeat,
        cache_dir=context.cache_dir,
        llm_factory=context.llm_factory,
        usage=context.usage,
        llm_spec=context.llm_spec,
    )


register_curated_source("default", _default_curated_source)


# ---------------------------------------------------------------------------
# LLM roles: answerer and judge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    rank: int
    item_id: str
    layer: str
    text: str
    estimated_tokens: int
    document_id: str | None
    source_refs: tuple[dict[str, str], ...]


class RoomMemAnswerer(Protocol):
    """Answers a probe from numbered evidence items only."""

    def answer(self, *, question: str, evidence: Sequence[EvidenceItem]) -> str: ...


class RoomMemJudge(Protocol):
    """Labels answers and unmatched curated memories."""

    def judge_answer(
        self,
        *,
        question: str,
        current_statements: Sequence[str],
        superseded_statements: Sequence[str],
        answer: str,
    ) -> str: ...

    def judge_unmatched_memory(
        self,
        *,
        memory: CuratedMemoryView,
        message_texts: Mapping[str, str],
    ) -> str: ...


class ChatCompletionClient(Protocol):
    @property
    def model(self) -> str: ...

    def complete(self, *, system: str, user: str) -> str: ...


@dataclass(frozen=True)
class LLMUsage:
    """Normalized provider token usage for one LLM call (fields may be None)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


def _extract_usage(payload: Any) -> LLMUsage | None:
    """Normalize a usage payload (LangChain keys or OpenAI token_usage keys)."""

    if isinstance(payload, LLMUsage):
        return payload
    if not isinstance(payload, Mapping):
        return None

    def as_int(*keys: str) -> int | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    usage = LLMUsage(
        prompt_tokens=as_int("prompt_tokens", "input_tokens"),
        completion_tokens=as_int("completion_tokens", "output_tokens"),
        total_tokens=as_int("total_tokens"),
    )
    if (
        usage.prompt_tokens is None
        and usage.completion_tokens is None
        and usage.total_tokens is None
    ):
        return None
    return usage


def _response_usage(response: object) -> LLMUsage | None:
    """Read usage off a LangChain response (usage_metadata or token_usage)."""

    usage = _extract_usage(getattr(response, "usage_metadata", None))
    if usage is not None:
        return usage
    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, Mapping):
        return _extract_usage(response_metadata.get("token_usage"))
    return None


@dataclass(frozen=True)
class _UsageCall:
    role: str
    cached: bool
    latency_s: float
    usage: LLMUsage | None = None


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted, non-empty sequence."""

    index = max(0, math.ceil(fraction * len(sorted_values)) - 1)
    return sorted_values[min(index, len(sorted_values) - 1)]


class LLMUsageTracker:
    """Per-role provider-call accounting: tokens, cache hits and latency.

    Provider calls record their wall-clock latency and token usage; cache-hit
    calls are recorded with ``cached=True`` and count separately so cached
    responses never dilute provider token or latency statistics.
    """

    def __init__(self) -> None:
        self._calls: list[_UsageCall] = []

    def record(
        self,
        role: str,
        *,
        cached: bool,
        latency_s: float,
        usage: LLMUsage | None = None,
    ) -> None:
        self._calls.append(_UsageCall(role=role, cached=cached, latency_s=latency_s, usage=usage))

    def aggregate(self) -> dict[str, Any]:
        by_role: dict[str, list[_UsageCall]] = {}
        for call in self._calls:
            by_role.setdefault(call.role, []).append(call)
        roles: dict[str, dict[str, Any]] = {}
        for role in sorted(by_role):
            calls = by_role[role]
            provider = [call for call in calls if not call.cached]
            tokens_in = _sum_tokens(provider, "prompt_tokens")
            tokens_out = _sum_tokens(provider, "completion_tokens")
            latencies = sorted(call.latency_s for call in provider)
            latency: dict[str, float] | None = None
            if latencies:
                latency = {
                    "mean": sum(latencies) / len(latencies),
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                    "total": sum(latencies),
                }
            roles[role] = {
                "calls": len(calls),
                "cached": len(calls) - len(provider),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_s": latency,
            }
        return {"roles": roles}


def _sum_tokens(calls: Sequence[_UsageCall], field: str) -> int | None:
    values = [
        getattr(call.usage, field)
        for call in calls
        if call.usage is not None and getattr(call.usage, field) is not None
    ]
    if not values:
        return None
    return sum(values)


def _curator_usage_extras(
    usage_payload: Mapping[str, Any],
    *,
    rooms: Sequence[Room],
    repeats: int,
    write_side: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Curator-specific usage rates: tokens per 100 messages, seconds per window."""

    roles = usage_payload.get("roles")
    curator_role = roles.get("curator") if isinstance(roles, Mapping) else None
    if not isinstance(curator_role, Mapping):
        return None
    messages = sum(len(room.messages) for room in rooms) * repeats
    windows = 0
    curated = write_side.get("curated")
    if isinstance(curated, Mapping):
        counts = curated.get("curator_counts")
        if isinstance(counts, Mapping) and isinstance(counts.get("windows"), int):
            windows = counts["windows"]
    tokens_in = curator_role.get("tokens_in")
    tokens_out = curator_role.get("tokens_out")
    tokens_total: int | None = None
    if isinstance(tokens_in, int) or isinstance(tokens_out, int):
        tokens_total = (tokens_in if isinstance(tokens_in, int) else 0) + (
            tokens_out if isinstance(tokens_out, int) else 0
        )
    seconds_per_window: float | None = None
    latency = curator_role.get("latency_s")
    if isinstance(latency, Mapping) and windows > 0:
        total = latency.get("total")
        if isinstance(total, (int, float)):
            seconds_per_window = float(total) / windows
    return {
        "messages": messages,
        "windows": windows,
        "tokens_per_100_messages": (
            (tokens_total * 100 / messages) if tokens_total is not None and messages else None
        ),
        "seconds_per_window": seconds_per_window,
    }


def _estimated_cost(
    usage_payload: Mapping[str, Any],
    *,
    price_in_per_mtok: float | None,
    price_out_per_mtok: float | None,
) -> dict[str, Any] | None:
    """Estimated provider cost from reported tokens and caller-supplied prices.

    Prices are never guessed: the result is only produced when the caller
    supplies at least one price and at least one role reported tokens.  Cache
    hits are not billed and an unpriced side counts as zero.
    """

    if price_in_per_mtok is None and price_out_per_mtok is None:
        return None
    tokens_in = 0
    tokens_out = 0
    have_tokens = False
    roles = usage_payload.get("roles")
    if isinstance(roles, Mapping):
        for payload in roles.values():
            if not isinstance(payload, Mapping):
                continue
            if isinstance(payload.get("tokens_in"), int):
                tokens_in += payload["tokens_in"]
                have_tokens = True
            if isinstance(payload.get("tokens_out"), int):
                tokens_out += payload["tokens_out"]
                have_tokens = True
    if not have_tokens:
        return None
    cost = (
        tokens_in * (price_in_per_mtok or 0.0) + tokens_out * (price_out_per_mtok or 0.0)
    ) / 1_000_000
    return {
        "price_in_per_mtok": price_in_per_mtok,
        "price_out_per_mtok": price_out_per_mtok,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
        "note": (
            "Estimated from provider-reported tokens of non-cached calls only; "
            "sides without a price count as 0."
        ),
    }


ANSWERER_SYSTEM_PROMPT = """\
You answer questions about a software project room.

Use ONLY the numbered evidence items provided; never use outside knowledge.
Cite every item you rely on with its number in square brackets, e.g. [2].
Answer the question directly and concisely, in the question's language.
If the evidence is insufficient to answer, reply with exactly: NO_EVIDENCE
"""

JUDGE_SYSTEM_PROMPT = """\
You are a strict evaluation judge for a memory benchmark.

You receive a question, the CURRENT correct statements, SUPERSEDED (outdated)
statements, and a candidate answer.  Label the answer with exactly one of:
- "correct": it answers the question with the current statements.
- "stale": it presents a superseded/outdated value as if it were current.
- "missing": it states that there is no evidence / does not answer.
- "wrong": anything else that is incorrect.

Respond ONLY with valid JSON:
{"label": "correct" | "stale" | "missing" | "wrong", "reason": "brief"}
"""

UNMATCHED_JUDGE_SYSTEM_PROMPT = """\
You are a strict evaluation judge for a memory benchmark.

A memory curator produced a memory that does not match any annotated gold
memory.  Given the memory and the room messages it cites, label it with
exactly one of:
- "legit_unannotated": a legitimate long-term memory the gold annotation
  simply missed (grounded in the cited messages).
- "noise": should not have been stored (chitchat, hypotheticals, tentative
  statements, rejected proposals, process chatter, ungrounded claims).

Respond ONLY with valid JSON:
{"label": "legit_unannotated" | "noise", "reason": "brief"}
"""


def _normalize_match_text(text: str) -> str:
    """Casefold and drop punctuation so quote-ish substrings compare cleanly."""

    lowered = text.casefold()
    cleaned = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", lowered)
    return " ".join(cleaned.split())


class FakeAnswerer:
    """Deterministic answerer: echoes the top evidence item."""

    def answer(self, *, question: str, evidence: Sequence[EvidenceItem]) -> str:
        return evidence[0].text if evidence else "NO_EVIDENCE"


class FakeJudge:
    """Deterministic judge using substring rules over normalized text."""

    def judge_answer(
        self,
        *,
        question: str,
        current_statements: Sequence[str],
        superseded_statements: Sequence[str],
        answer: str,
    ) -> str:
        normalized = _normalize_match_text(answer)
        if not normalized or normalized == _normalize_match_text("NO_EVIDENCE"):
            return "missing"
        if any(
            (candidate := _normalize_match_text(statement)) and candidate in normalized
            for statement in current_statements
        ):
            return "correct"
        if any(
            (candidate := _normalize_match_text(statement)) and candidate in normalized
            for statement in superseded_statements
        ):
            return "stale"
        return "wrong"

    def judge_unmatched_memory(
        self,
        *,
        memory: CuratedMemoryView,
        message_texts: Mapping[str, str],
    ) -> str:
        for source in memory.sources:
            text = message_texts.get(source.message_id)
            if text is None or source.quote not in text:
                return "noise"
        return "legit_unannotated"


class RemoteChatClient:
    """Chat client for the configured remote provider (DeepSeek or OpenCode Go)."""

    def __init__(self, settings: Settings) -> None:
        if settings.resolved_llm_provider not in REMOTE_LLM_PROVIDERS:
            raise RoomMemConfigError(
                "RoomMem LLM roles require MEMORYOS_LLM_PROVIDER="
                + " or ".join(REMOTE_LLM_PROVIDERS)
                + " (or run with --fake-llm)"
            )
        if not settings.chat_api_key:
            raise RoomMemConfigError(
                f"{settings.chat_api_key_name} is required for non-fake RoomMem runs "
                "(or run with --fake-llm)"
            )
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            raise RoomMemConfigError(
                "RoomMem LLM roles require the remote extra: "
                "install memoryos-lite[remote] (or run with --fake-llm)"
            ) from exc
        self._model = settings.chat_model
        self._system_message = SystemMessage
        self._human_message = HumanMessage
        self.last_usage: LLMUsage | None = None
        try:
            self._llm = build_chat_openai(settings)
        except ImportError as exc:
            raise RoomMemConfigError(
                "RoomMem LLM roles require the remote extra: "
                "install memoryos-lite[remote] (or run with --fake-llm)"
            ) from exc

    @property
    def model(self) -> str:
        return self._model

    def complete(self, *, system: str, user: str) -> str:
        response = self._llm.invoke(
            [
                self._system_message(content=system),
                self._human_message(content=user),
            ]
        )
        self.last_usage = _response_usage(response)
        return message_text(response)


class DiskCachedChatClient:
    """Disk cache keyed by sha256(role, model, prompt, repeat index).

    The repeat index is part of the key so ``--repeats N`` never reuses one
    repeat's response for another; rerunning the same configuration is cheap
    because every repeat hits its own cached entries.
    """

    def __init__(
        self,
        inner: ChatCompletionClient,
        *,
        role: str,
        cache_dir: Path,
        repeat: int = 0,
        usage: LLMUsageTracker | None = None,
    ) -> None:
        if repeat < 0:
            raise ValueError("repeat index must be non-negative")
        self._inner = inner
        self._role = role
        self._cache_dir = Path(cache_dir)
        self._repeat = repeat
        self._usage = usage

    @property
    def model(self) -> str:
        return self._inner.model

    def cache_key(self, *, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "role": self._role,
                "model": self._inner.model,
                "system": system,
                "user": user,
                "repeat": self._repeat,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def complete(self, *, system: str, user: str) -> str:
        key = self.cache_key(system=system, user=user)
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            started = time.perf_counter()
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                response = payload["response"]
                if isinstance(response, str):
                    self._record(cached=True, started=started)
                    return response
            except (OSError, ValueError, KeyError):
                pass
        started = time.perf_counter()
        response = self._inner.complete(system=system, user=user)
        self._record(cached=False, started=started)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"role": self._role, "model": self._inner.model, "response": response},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return response

    def _record(self, *, cached: bool, started: float) -> None:
        if self._usage is None:
            return
        latency = time.perf_counter() - started
        usage = None if cached else _extract_usage(getattr(self._inner, "last_usage", None))
        self._usage.record(self._role, cached=cached, latency_s=latency, usage=usage)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start == -1:
            return None
        try:
            data, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


class ChatAnswerer:
    """Chat-backed answerer; wired to the configured provider by the CLI."""

    def __init__(self, chat: ChatCompletionClient) -> None:
        self._chat = chat

    def answer(self, *, question: str, evidence: Sequence[EvidenceItem]) -> str:
        if not evidence:
            return "NO_EVIDENCE"
        lines = [f"[{item.rank}] ({item.layer}) {' '.join(item.text.split())}" for item in evidence]
        user = f"Question: {question}\n\nEvidence:\n" + "\n".join(lines) + "\n\nAnswer:"
        response = self._chat.complete(system=ANSWERER_SYSTEM_PROMPT, user=user)
        return response.strip()


class ChatJudge:
    """Chat-backed judge; wired to the configured provider by the CLI."""

    def __init__(self, chat: ChatCompletionClient) -> None:
        self._chat = chat

    def judge_answer(
        self,
        *,
        question: str,
        current_statements: Sequence[str],
        superseded_statements: Sequence[str],
        answer: str,
    ) -> str:
        user = json.dumps(
            {
                "question": question,
                "current_statements": list(current_statements),
                "superseded_statements": list(superseded_statements),
                "answer": answer,
            },
            ensure_ascii=False,
        )
        response = self._chat.complete(system=JUDGE_SYSTEM_PROMPT, user=user)
        data = _extract_json_object(response) or {}
        label = str(data.get("label", "")).strip().lower()
        return label if label in JUDGE_LABELS else "wrong"

    def judge_unmatched_memory(
        self,
        *,
        memory: CuratedMemoryView,
        message_texts: Mapping[str, str],
    ) -> str:
        user = json.dumps(
            {
                "statement": memory.statement,
                "kind": memory.kind,
                "sources": [
                    {
                        "message_id": source.message_id,
                        "quote": source.quote,
                        "message_text": message_texts.get(source.message_id, ""),
                    }
                    for source in memory.sources
                ],
            },
            ensure_ascii=False,
        )
        response = self._chat.complete(system=UNMATCHED_JUDGE_SYSTEM_PROMPT, user=user)
        data = _extract_json_object(response) or {}
        label = str(data.get("label", "")).strip().lower()
        return label if label in UNMATCHED_LABELS else "noise"


LLMFactory = Callable[[int], tuple[RoomMemAnswerer, RoomMemJudge]]


def build_llm_factory(
    *,
    out_dir: Path,
    fake_llm: bool,
    settings: Settings | None = None,
    usage: LLMUsageTracker | None = None,
    answerer_llm: str | None = None,
    judge_llm: str | None = None,
) -> LLMFactory:
    """Create the per-repeat answerer/judge factory.

    Non-fake runs use remote chat clients behind per-role, per-repeat disk
    caches under ``out_dir/llm_cache``.  ``answerer_llm``/``judge_llm`` are
    ``provider:model[@wire]`` specs (default: the configured provider), so the
    judge can come from a different model family than the curator.  Clients
    are built eagerly so missing credentials fail before any room is
    ingested.  When ``usage`` is given, every provider call and cache hit is
    recorded per role.
    """

    if fake_llm:
        return lambda repeat: (FakeAnswerer(), FakeJudge())
    resolved = settings or get_settings()
    answerer_client = RemoteChatClient(settings_for_llm_spec(resolved, answerer_llm))
    judge_client = RemoteChatClient(settings_for_llm_spec(resolved, judge_llm))
    cache_dir = out_dir / "llm_cache"

    def factory(repeat: int) -> tuple[RoomMemAnswerer, RoomMemJudge]:
        answerer_chat = DiskCachedChatClient(
            answerer_client, role="answerer", cache_dir=cache_dir, repeat=repeat, usage=usage
        )
        judge_chat = DiskCachedChatClient(
            judge_client, role="judge", cache_dir=cache_dir, repeat=repeat, usage=usage
        )
        return ChatAnswerer(answerer_chat), ChatJudge(judge_chat)

    return factory


# ---------------------------------------------------------------------------
# Write-side scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CuratedGoldMatch:
    curated_id: str
    gold_id: str
    overlap: int
    statement_overlap: int = 0


def _statement_token_overlap(left: str, right: str) -> int:
    left_tokens = set(_normalize_match_text(left).split())
    right_tokens = set(_normalize_match_text(right).split())
    return len(left_tokens & right_tokens)


def curated_candidate_pairs(
    curated: Sequence[CuratedMemoryView],
    gold: Sequence[GoldMemory],
) -> list[CuratedGoldMatch]:
    """All curated/gold pairs with non-empty source-message overlap."""

    pairs: list[CuratedGoldMatch] = []
    for view in curated:
        view_messages = {source.message_id for source in view.sources}
        for memory in gold:
            overlap = len(view_messages & {source.message_id for source in memory.sources})
            if overlap:
                pairs.append(
                    CuratedGoldMatch(
                        view.id,
                        memory.id,
                        overlap,
                        _statement_token_overlap(view.statement, memory.statement),
                    )
                )
    return pairs


def match_curated_to_gold(
    curated: Sequence[CuratedMemoryView],
    gold: Sequence[GoldMemory],
) -> list[CuratedGoldMatch]:
    """One-to-one greedy matching by source overlap, then statement tokens."""

    pairs = curated_candidate_pairs(curated, gold)
    ordered = sorted(
        pairs,
        key=lambda pair: (-pair.overlap, -pair.statement_overlap, pair.curated_id, pair.gold_id),
    )
    used_curated: set[str] = set()
    used_gold: set[str] = set()
    matches: list[CuratedGoldMatch] = []
    for pair in ordered:
        if pair.curated_id in used_curated or pair.gold_id in used_gold:
            continue
        used_curated.add(pair.curated_id)
        used_gold.add(pair.gold_id)
        matches.append(pair)
    return matches


def score_write_side(
    room: Room,
    curated: Sequence[CuratedMemoryView],
    judge: RoomMemJudge,
) -> tuple[dict[str, Any], dict[str, CuratedMemoryView]]:
    """Compute curated-arm write-side metrics.

    Curated memories match gold memories by source-message overlap only; kind
    and xmuse-scope agreement are reported as separate metrics.  Returns the
    metrics payload and the gold-id -> curated view map used by the read side
    for evidence-hit checks.
    """

    gold = room.gold_memories
    view_by_id = {view.id: view for view in curated}
    gold_by_id = {memory.id: memory for memory in gold}
    matches = match_curated_to_gold(curated, gold)
    matched_view_ids = {match.curated_id for match in matches}
    matched_by_gold: dict[str, CuratedMemoryView] = {}
    for match in matches:
        matched_by_gold.setdefault(match.gold_id, view_by_id[match.curated_id])

    candidates_by_gold: dict[str, list[str]] = {}
    for pair in curated_candidate_pairs(curated, gold):
        candidates_by_gold.setdefault(pair.gold_id, []).append(pair.curated_id)

    unmatched = [view for view in curated if view.id not in matched_view_ids]

    judged = {label: 0 for label in UNMATCHED_LABELS}
    unmatched_labels: dict[str, str] = {}
    for view in unmatched:
        message_texts = {
            source.message_id: room.message(source.message_id).text  # type: ignore[union-attr]
            for source in view.sources
        }
        label = judge.judge_unmatched_memory(memory=view, message_texts=message_texts)
        if label not in UNMATCHED_LABELS:
            label = "noise"
        judged[label] += 1
        unmatched_labels[view.id] = label

    noise_type_stats: dict[str, dict[str, int]] = {}
    for entry in room.noise:
        stats = noise_type_stats.setdefault(
            entry.type, {"messages": 0, "cited_as_source": 0, "in_unmatched_memory": 0}
        )
        stats["messages"] += 1
        unmatched_ids = {view.id for view in unmatched}
        for view in curated:
            if entry.message_id not in {source.message_id for source in view.sources}:
                continue
            stats["cited_as_source"] += 1
            if view.id in unmatched_ids:
                stats["in_unmatched_memory"] += 1
            break

    kind_matches = sum(
        1
        for match in matches
        if view_by_id[match.curated_id].kind == gold_by_id[match.gold_id].kind
    )
    scope_matches = sum(
        1
        for match in matches
        if _scope_for_kind(view_by_id[match.curated_id].kind)
        == _scope_for_kind(gold_by_id[match.gold_id].kind)
    )
    superseded_gold = [memory for memory in gold if memory.superseded_by is not None]
    supersede_correct = 0
    stale_active = 0
    for memory in superseded_gold:
        matched_view = matched_by_gold.get(memory.id)
        if matched_view is None:
            continue
        if matched_view.status == "superseded":
            supersede_correct += 1
        else:
            stale_active += 1
    duplicate_golds = sum(
        1
        for view_ids in candidates_by_gold.values()
        if sum(1 for view_id in view_ids if view_by_id[view_id].status == "active") > 1
    )
    # Chain key consistency: both ends of a gold supersede chain matched, and
    # the curator gave them the same (normalized) topic key.
    chain_pairs = 0
    chain_key_consistent = 0
    for memory in superseded_gold:
        old_view = matched_by_gold.get(memory.id)
        new_view = matched_by_gold.get(memory.superseded_by or "")
        if old_view is None or new_view is None:
            continue
        chain_pairs += 1
        if _comparable_key(old_view.topic_key) == _comparable_key(new_view.topic_key):
            chain_key_consistent += 1

    memories = len(curated)
    matched = len(matches)
    gold_total = len(gold)
    with_matches = len(candidates_by_gold)
    metrics: dict[str, Any] = {
        "memories": memories,
        "matched": matched,
        "gold": gold_total,
        "unmatched": len(unmatched),
        "unmatched_judged": dict(judged),
        "unmatched_labels": dict(unmatched_labels),
        "noise_types": {name: dict(stats) for name, stats in sorted(noise_type_stats.items())},
        "kind_matches": kind_matches,
        "scope_matches": scope_matches,
        "superseded_gold": len(superseded_gold),
        "supersede_correct": supersede_correct,
        "stale_active": stale_active,
        "golds_with_matches": with_matches,
        "duplicate_golds": duplicate_golds,
        "chain_pairs": chain_pairs,
        "chain_key_consistent": chain_key_consistent,
        "rates": {
            "chain_key_consistency": (chain_key_consistent / chain_pairs if chain_pairs else None),
            "precision": (matched / memories) if memories else None,
            "recall": matched / gold_total,
            "unmatched_rate": (len(unmatched) / memories) if memories else None,
            "noise_rate": (judged["noise"] / memories) if memories else None,
            "supersede_rate": (
                supersede_correct / len(superseded_gold) if superseded_gold else None
            ),
            "stale_active_rate": (
                (stale_active / len(superseded_gold)) if superseded_gold else None
            ),
            "duplicate_rate": (duplicate_golds / with_matches) if with_matches else None,
            "kind_agreement": (kind_matches / matched) if matched else None,
            "scope_agreement": (scope_matches / matched) if matched else None,
        },
    }
    return metrics, matched_by_gold


def _comparable_key(topic_key: str) -> str:
    return normalize_topic_key(topic_key) or topic_key.strip().casefold()


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def conflict_flag_stats(
    room: Room,
    views: Sequence[CuratedMemoryView],
    matched_by_gold: Mapping[str, CuratedMemoryView],
    embed_batch: Callable[[list[str]], list[list[float]]],
    thresholds: Sequence[float] = CONFLICT_THRESHOLDS,
) -> dict[str, Any]:
    """Score FastEmbed "possible conflict" flags between active memories.

    A pair of active memories with different topic keys is flagged at a
    threshold when their statement cosine is at least that threshold.  Pairs
    whose two memories both matched gold are classified by the gold topic
    keys: ``same_topic`` (a real conflict the keys missed) or
    ``different_topic`` (a false positive).  Pairs with an unmatched memory are
    ``unknown`` and excluded from the false-positive rate.
    """

    active = [view for view in views if view.status == "active"]
    gold_topic_by_view = {
        view.id: memory.topic_key
        for gold_id, view in matched_by_gold.items()
        if (memory := room.gold_memory(gold_id)) is not None
    }
    pairs: list[tuple[float, str]] = []
    if len(active) >= 2:
        vectors = embed_batch([view.statement for view in active])
        for i, left in enumerate(active):
            for j in range(i + 1, len(active)):
                right = active[j]
                if _comparable_key(left.topic_key) == _comparable_key(right.topic_key):
                    continue
                left_gold = gold_topic_by_view.get(left.id)
                right_gold = gold_topic_by_view.get(right.id)
                if left_gold is None or right_gold is None:
                    label = "unknown"
                elif left_gold == right_gold:
                    label = "same_topic"
                else:
                    label = "different_topic"
                pairs.append((_cosine(vectors[i], vectors[j]), label))
    by_threshold: dict[str, dict[str, int]] = {}
    for threshold in thresholds:
        counts = {"same_topic": 0, "different_topic": 0, "unknown": 0}
        for score, label in pairs:
            if score >= threshold:
                counts[label] += 1
        by_threshold[f"{threshold:.2f}"] = counts
    totals = {"same_topic": 0, "different_topic": 0, "unknown": 0}
    for _score, label in pairs:
        totals[label] += 1
    return {"pairs": totals, "flagged": by_threshold}


def _pool_conflicts(per_room: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    payloads = [payload["conflicts"] for payload in per_room if payload.get("conflicts")]
    if not payloads:
        return None
    pairs = {"same_topic": 0, "different_topic": 0, "unknown": 0}
    flagged: dict[str, dict[str, int]] = {}
    for payload in payloads:
        for label, count in payload.get("pairs", {}).items():
            pairs[label] = pairs.get(label, 0) + int(count)
        for threshold, counts in payload.get("flagged", {}).items():
            target = flagged.setdefault(
                threshold, {"same_topic": 0, "different_topic": 0, "unknown": 0}
            )
            for label, count in counts.items():
                target[label] = target.get(label, 0) + int(count)
    rates: dict[str, dict[str, float | None]] = {}
    for threshold, counts in sorted(flagged.items()):
        known = counts["same_topic"] + counts["different_topic"]
        rates[threshold] = {
            "false_positive_rate": counts["different_topic"] / known if known else None,
            "same_topic_recall": (
                counts["same_topic"] / pairs["same_topic"] if pairs["same_topic"] else None
            ),
        }
    return {"pairs": pairs, "flagged": dict(sorted(flagged.items())), "rates": rates}


def _memory_dump_rows(
    *,
    arm: str,
    room: Room,
    repeat: int,
    views: Sequence[CuratedMemoryView],
    matched_by_gold: Mapping[str, CuratedMemoryView],
    write_side: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """One audit row per curated/oracle memory for ``memories.jsonl``.

    Sources are dataset message ids; ``matched_gold`` is the matched gold
    memory id or ``None``, and unmatched memories carry the judge label so an
    external re-judge can compare labels without re-running the harness.
    """

    gold_by_view = {view.id: gold_id for gold_id, view in matched_by_gold.items()}
    unmatched_labels = write_side.get("unmatched_labels")
    if not isinstance(unmatched_labels, Mapping):
        unmatched_labels = {}
    rows: list[dict[str, Any]] = []
    for view in views:
        gold_id = gold_by_view.get(view.id)
        label = unmatched_labels.get(view.id)
        rows.append(
            {
                "arm": arm,
                "room": room.room_id,
                "repeat": repeat,
                "id": view.id,
                "kind": view.kind,
                "topic_key": view.topic_key,
                "statement": view.statement,
                "status": view.status,
                "supersedes_id": view.supersedes_id,
                "sources": [
                    {"message_id": source.message_id, "quote": source.quote}
                    for source in view.sources
                ],
                "matched_gold": gold_id,
                "judge": label if gold_id is None and isinstance(label, str) else None,
            }
        )
    return rows


def pool_write_side(per_room: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pool per-room curated write-side payloads into an arm-level aggregate."""

    if not per_room:
        return {}
    totals: dict[str, int] = {
        "memories": 0,
        "matched": 0,
        "gold": 0,
        "unmatched": 0,
        "kind_matches": 0,
        "scope_matches": 0,
        "superseded_gold": 0,
        "supersede_correct": 0,
        "stale_active": 0,
        "golds_with_matches": 0,
        "duplicate_golds": 0,
        "chain_pairs": 0,
        "chain_key_consistent": 0,
    }
    judged = {label: 0 for label in UNMATCHED_LABELS}
    noise_types: dict[str, dict[str, int]] = {}
    curator_counts: dict[str, int] = {}
    for payload in per_room:
        for key in totals:
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
        for label, count in (payload.get("unmatched_judged") or {}).items():
            if label in judged and isinstance(count, int):
                judged[label] += count
        for name, stats in (payload.get("noise_types") or {}).items():
            if not isinstance(stats, dict):
                continue
            merged = noise_types.setdefault(
                name, {"messages": 0, "cited_as_source": 0, "in_unmatched_memory": 0}
            )
            for key in merged:
                value = stats.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    merged[key] += value
        for key, value in (payload.get("curator_counts") or {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                curator_counts[key] = curator_counts.get(key, 0) + value
    pooled = {
        **totals,
        "unmatched_judged": judged,
        "noise_types": {name: noise_types[name] for name in sorted(noise_types)},
        "curator_counts": curator_counts,
    }
    conflicts = _pool_conflicts(per_room)
    if conflicts is not None:
        pooled["conflicts"] = conflicts
    pooled["rates"] = {
        "chain_key_consistency": (
            (totals["chain_key_consistent"] / totals["chain_pairs"])
            if totals["chain_pairs"]
            else None
        ),
        "precision": (totals["matched"] / totals["memories"]) if totals["memories"] else None,
        "recall": totals["matched"] / totals["gold"] if totals["gold"] else None,
        "unmatched_rate": (
            (totals["unmatched"] / totals["memories"]) if totals["memories"] else None
        ),
        "noise_rate": (judged["noise"] / totals["memories"]) if totals["memories"] else None,
        "supersede_rate": (
            (totals["supersede_correct"] / totals["superseded_gold"])
            if totals["superseded_gold"]
            else None
        ),
        "stale_active_rate": (
            (totals["stale_active"] / totals["superseded_gold"])
            if totals["superseded_gold"]
            else None
        ),
        "duplicate_rate": (
            (totals["duplicate_golds"] / totals["golds_with_matches"])
            if totals["golds_with_matches"]
            else None
        ),
        "kind_agreement": (
            (totals["kind_matches"] / totals["matched"]) if totals["matched"] else None
        ),
        "scope_agreement": (
            (totals["scope_matches"] / totals["matched"]) if totals["matched"] else None
        ),
    }
    return pooled


def _curator_counters_by_room(per_room: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Sum curator run counters per room id across repeats."""

    by_room: dict[str, dict[str, int]] = {}
    for payload in per_room:
        room_id = payload.get("room")
        if not isinstance(room_id, str):
            continue
        target = by_room.setdefault(room_id, {})
        for key, value in (payload.get("curator_counts") or {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                target[key] = target.get(key, 0) + value
    return by_room


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------


def _evidence_items(envelope: dict[str, Any]) -> list[EvidenceItem]:
    raw_items = envelope.get("items")
    if not isinstance(raw_items, list):
        return []
    items: list[EvidenceItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        refs: list[dict[str, str]] = []
        raw_refs = raw.get("source_refs")
        if isinstance(raw_refs, list):
            for ref in raw_refs:
                if not isinstance(ref, dict):
                    continue
                mapped = {
                    key: value
                    for key, value in ref.items()
                    if key in {"source_type", "source_id", "session_id"} and isinstance(value, str)
                }
                if mapped:
                    refs.append(mapped)
        document_id = raw.get("document_id")
        items.append(
            EvidenceItem(
                rank=int(raw.get("rank", 0)),
                item_id=str(raw.get("item_id", "")),
                layer=str(raw.get("layer", "")),
                text=str(raw.get("text", "")),
                estimated_tokens=int(raw.get("estimated_tokens", 0)),
                document_id=document_id if isinstance(document_id, str) else None,
                source_refs=tuple(refs),
            )
        )
    return items


def _item_document_ids(item: EvidenceItem) -> list[str]:
    ids: list[str] = []
    if item.document_id:
        ids.append(item.document_id)
    for ref in item.source_refs:
        source_id = ref.get("source_id")
        if source_id and source_id not in ids:
            ids.append(source_id)
    return ids


def _activity_dataset_message_id(suffix: str, room_id: str) -> str | None:
    """Map an activity document id suffix to a dataset message id of ``room_id``.

    The ``raw`` arm names documents with the bare dataset id (``mNN``); the
    ``raw_project`` arm qualifies them as ``<room_id>.mNN`` because its archive
    is shared across a whole project.  Qualified ids of other rooms return
    ``None`` so cross-attached documents never count as this room's messages.
    """

    prefix = f"{room_id}."
    if suffix.startswith(prefix):
        return suffix[len(prefix) :]
    if "." not in suffix:
        return suffix
    return None


def _evidence_presence(
    evidence: Sequence[EvidenceItem],
    message_id_map: Mapping[str, str],
    *,
    room_id: str,
) -> tuple[set[str], set[str]]:
    """Return (dataset message ids, curated memory ids) visible in evidence."""

    reverse = {memoryos_id: dataset_id for dataset_id, memoryos_id in message_id_map.items()}
    message_ids: set[str] = set()
    memory_ids: set[str] = set()
    for item in evidence:
        for ref in item.source_refs:
            source_id = ref.get("source_id", "")
            if ref.get("source_type") == "message" and source_id in reverse:
                message_ids.add(reverse[source_id])
        for candidate in _item_document_ids(item):
            if candidate.startswith(XMUSE_ACTIVITY_DOC_PREFIX):
                dataset_id = _activity_dataset_message_id(
                    candidate[len(XMUSE_ACTIVITY_DOC_PREFIX) :], room_id
                )
                if dataset_id is not None:
                    message_ids.add(dataset_id)
            elif candidate.startswith(XMUSE_MEMORY_DOC_PREFIX):
                memory_ids.add(candidate[len(XMUSE_MEMORY_DOC_PREFIX) :])
    return message_ids, memory_ids


def _substring_verdict(probe: RoomProbe, answer: str) -> bool:
    lowered = answer.casefold()
    if any(value.casefold() not in lowered for value in probe.must_contain):
        return False
    return not any(value.casefold() in lowered for value in probe.must_not_contain)


def _citation_correctness(
    answer: str,
    evidence: Sequence[EvidenceItem],
    *,
    arm: str,
    room_id: str,
    message_id_map: Mapping[str, str],
    answer_source_messages: set[str],
    answer_view_ids: set[str],
) -> tuple[list[dict[str, Any]], float | None]:
    message_reverse = {
        memoryos_id: dataset_id for dataset_id, memoryos_id in message_id_map.items()
    }
    by_rank = {item.rank: item for item in evidence}
    cited_ranks = sorted({int(match) for match in CITATION_RE.findall(answer)})
    citations: list[dict[str, Any]] = []
    for rank in cited_ranks:
        item = by_rank.get(rank)
        if item is None:
            citations.append({"rank": rank, "item_id": None, "document_id": None, "correct": False})
            continue
        correct = False
        for candidate in _item_document_ids(item):
            if candidate.startswith(XMUSE_ACTIVITY_DOC_PREFIX):
                dataset_id = _activity_dataset_message_id(
                    candidate[len(XMUSE_ACTIVITY_DOC_PREFIX) :], room_id
                )
                if dataset_id is not None and dataset_id in answer_source_messages:
                    correct = True
            elif candidate.startswith(XMUSE_MEMORY_DOC_PREFIX):
                if (
                    arm not in RAW_LIKE_ARMS
                    and candidate[len(XMUSE_MEMORY_DOC_PREFIX) :] in answer_view_ids
                ):
                    correct = True
            elif candidate in message_reverse:
                if message_reverse[candidate] in answer_source_messages:
                    correct = True
        citations.append(
            {
                "rank": rank,
                "item_id": item.item_id,
                "document_id": item.document_id,
                "correct": correct,
            }
        )
    if not citations:
        return citations, None
    return citations, sum(1 for citation in citations if citation["correct"]) / len(citations)


# ---------------------------------------------------------------------------
# Room/arm execution
# ---------------------------------------------------------------------------


def _room_settings(
    data_dir: Path,
    *,
    embedding: str,
) -> Settings:
    kwargs: dict[str, Any] = {
        "data_dir": data_dir,
        "memoryos_embedding_provider": "fastembed" if embedding == "fastembed" else "none",
    }
    return Settings(**kwargs)


def _require_fastembed() -> None:
    from importlib.util import find_spec

    if find_spec("fastembed") is None:
        raise RoomMemConfigError(
            "--embedding fastembed requires the full-local extra: install memoryos-lite[full-local]"
        )


def _attach_document(service: SessionMemoryService, session_id: str, document_id: str) -> None:
    ref = ArchiveSourceRefPayload(source_type="document", source_id=document_id)
    service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id=document_id,
            scope_type="session",
            scope_id=session_id,
            source_refs=[ref],
        )
    )


def _ingest_and_attach(
    service: SessionMemoryService,
    session_id: str,
    *,
    document_id: str,
    title: str,
    content: str,
    metadata: Mapping[str, Any] | None = None,
    tags: Sequence[str] = (),
) -> None:
    ref = ArchiveSourceRefPayload(source_type="document", source_id=document_id)
    service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id=document_id,
            title=title,
            content=content,
            source_refs=[ref],
            identity=ArchiveIdentityArchive(kind="archive", archive_id=document_id),
            tags=list(tags),
            metadata=dict(metadata or {}),
        )
    )
    _attach_document(service, session_id, document_id)


def _ingest_room(
    service: SessionMemoryService,
    room: Room,
    session_id: str,
    *,
    document_id_for: Callable[[RoomMessage], str] | None = None,
) -> dict[str, str]:
    """Ingest the transcript and the per-message document outbox.

    Returns the dataset-message-id -> MemoryOS-message-id map.  The
    ``document_id_for`` override names the per-message activity documents; the
    ``raw_project`` arm qualifies them by room so a shared project service
    never collides two rooms' ``mNN`` documents.
    """

    message_id_map: dict[str, str] = {}
    for message in room.messages:
        participant = room.participant(message.speaker)
        response = service.ingest(
            session_id,
            MessageCreate(
                role=Role.USER
                if participant is not None and participant.kind == "human"
                else Role.ASSISTANT,
                content=message.text,
                external_id=f"{XMUSE_MESSAGE_ID_PREFIX}{message.id}",
                metadata={
                    "participant_id": message.speaker,
                    "speaker_name": participant.name
                    if participant is not None
                    else message.speaker,
                },
            ),
        )
        message_id_map[message.id] = response.message.id
    for message in room.messages:
        document_id = (
            document_id_for(message)
            if document_id_for is not None
            else f"{XMUSE_ACTIVITY_DOC_PREFIX}{message.id}"
        )
        _ingest_and_attach(
            service,
            session_id,
            document_id=document_id,
            title=f"{room.room_id} message {message.id}",
            content=message.text,
            metadata={"participant_id": message.speaker},
        )
    return message_id_map


def _raw_project_document_id(room: Room, message: RoomMessage) -> str:
    """Room-qualified activity document id for the shared project service."""

    return f"{XMUSE_ACTIVITY_DOC_PREFIX}{room.room_id}.{message.id}"


def _raw_project_id_selector(room: Room) -> Callable[[RoomMessage], str]:
    return lambda message: _raw_project_document_id(room, message)


@dataclass(frozen=True)
class _RawProject:
    """Shared raw-archive state for one project, built once per repeat.

    One :class:`SessionMemoryService` holds every selected room of the project (each
    with its own session and room-qualified activity documents); probe sessions
    only see other rooms through explicit document attachments.
    """

    service: SessionMemoryService
    sessions: Mapping[str, str]
    message_maps: Mapping[str, Mapping[str, str]]
    new_room_sessions: Mapping[str, str]


def _rooms_by_project(rooms: Sequence[Room]) -> dict[str, list[Room]]:
    grouped: dict[str, list[Room]] = {}
    for room in rooms:
        grouped.setdefault(room.project, []).append(room)
    return grouped


def _raw_project_document_ids(room: Room) -> list[str]:
    return [_raw_project_document_id(room, message) for message in room.messages]


def _build_raw_project_context(
    *,
    project: str,
    rooms: Sequence[Room],
    repeat: int,
    scratch_dir: Path,
    embedding: str,
) -> _RawProject:
    """Ingest all rooms of one project once per repeat into a shared service.

    Every probe session of a room gets the project's raw per-message documents
    attached: same-room sessions receive the other rooms' documents (the own
    room is attached during ingest) and new-room sessions receive all rooms of
    the project.  Other projects live in separate services and data dirs, so
    they can never leak into evidence.
    """

    service = SessionMemoryService(
        settings=_room_settings(
            scratch_dir / "raw_project" / f"{project or 'default'}-r{repeat}",
            embedding=embedding,
        )
    )
    sessions: dict[str, str] = {}
    message_maps: dict[str, dict[str, str]] = {}
    for room in rooms:
        session_id = service.create_session(f"roommem {room.room_id} (raw_project)").id
        sessions[room.room_id] = session_id
        message_maps[room.room_id] = _ingest_room(
            service,
            room,
            session_id,
            document_id_for=_raw_project_id_selector(room),
        )
    for room in rooms:
        for other in rooms:
            if other.room_id == room.room_id:
                continue
            for document_id in _raw_project_document_ids(other):
                _attach_document(service, sessions[room.room_id], document_id)
    new_room_sessions: dict[str, str] = {}
    for room in rooms:
        if not room.has_new_room_probes():
            continue
        session_id = service.create_session(f"roommem {room.room_id} (new room, same project)").id
        new_room_sessions[room.room_id] = session_id
        for other in rooms:
            for document_id in _raw_project_document_ids(other):
                _attach_document(service, session_id, document_id)
    return _RawProject(
        service=service,
        sessions=sessions,
        message_maps=message_maps,
        new_room_sessions=new_room_sessions,
    )


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 ASCII characters or 1 non-ASCII character per token."""

    ascii_chars = sum(1 for char in text if ord(char) < 128)
    return max(1, ascii_chars // 4 + (len(text) - ascii_chars))


def full_context_evidence(project_rooms: Sequence[Room]) -> list[EvidenceItem]:
    """The whole project transcript as numbered evidence (the ``full_context`` arm).

    Rooms keep their dataset order and every message is one item whose
    document id is the room-qualified activity id used by ``raw_project``, so
    presence and citation scoring work unchanged.  No retrieval is involved:
    this is the "just put all history in the context window" baseline.
    """

    items: list[EvidenceItem] = []
    for room in project_rooms:
        for message in room.messages:
            participant = room.participant(message.speaker)
            speaker = participant.name if participant is not None else message.speaker
            text = f"({room.room_id}: {room.title or room.room_id}) {speaker}: {message.text}"
            items.append(
                EvidenceItem(
                    rank=len(items) + 1,
                    item_id=f"{room.room_id}.{message.id}",
                    layer=FULL_CONTEXT_LAYER,
                    text=text,
                    estimated_tokens=_estimate_tokens(text),
                    document_id=_raw_project_document_id(room, message),
                    source_refs=(),
                )
            )
    return items


@dataclass(frozen=True)
class _SharedMemoryProject:
    """Shared curated/oracle state for one project (``--shared-project``).

    Mirrors xmuse delivery: every room of the project lives in one service
    with its own session; room-scope memories attach to their own room, while
    project/user-scope memories of every room attach to every room session
    and every new-room session of the project.
    """

    service: SessionMemoryService
    sessions: Mapping[str, str]
    message_maps: Mapping[str, Mapping[str, str]]
    new_room_sessions: Mapping[str, str]
    views: Mapping[str, list[CuratedMemoryView]]
    curator_counts: Mapping[str, dict[str, int]]


def _qualified_oracle_views(room: Room) -> list[CuratedMemoryView]:
    """Oracle views with room-qualified ids so rooms never collide in one service."""

    return [
        view.model_copy(
            update={
                "id": f"{room.room_id}.{view.id}",
                "supersedes_id": (
                    f"{room.room_id}.{view.supersedes_id}" if view.supersedes_id else None
                ),
            }
        )
        for view in oracle_curated_memories(room)
    ]


def _build_shared_memory_project(
    *,
    arm: str,
    project: str,
    rooms: Sequence[Room],
    repeat: int,
    scratch_dir: Path,
    embedding: str,
    curated_source: CuratedMemorySource | None,
) -> _SharedMemoryProject:
    service = SessionMemoryService(
        settings=_room_settings(
            scratch_dir / f"{arm}_shared" / f"{project or 'default'}-r{repeat}",
            embedding=embedding,
        )
    )
    sessions: dict[str, str] = {}
    message_maps: dict[str, dict[str, str]] = {}
    views: dict[str, list[CuratedMemoryView]] = {}
    counts: dict[str, dict[str, int]] = {}
    shared_docs: list[str] = []
    for room in rooms:
        session_id = service.create_session(f"roommem {room.room_id} ({arm}, shared)").id
        sessions[room.room_id] = session_id
        message_maps[room.room_id] = _ingest_room(
            service, room, session_id, document_id_for=_raw_project_id_selector(room)
        )
        if arm == "oracle":
            room_views = _qualified_oracle_views(room)
        else:
            if curated_source is None:
                raise RoomMemConfigError("curated arm requires a registered curated memory source")
            room_views = list(curated_source.curate(service, session_id))
            _validate_curated_views(room_views, room=room)
            counts[room.room_id] = _curator_counts(curated_source)
        views[room.room_id] = room_views
        for view in room_views:
            if view.status != "active":
                continue
            scope = _scope_for_kind(view.kind)
            document_id = f"{XMUSE_MEMORY_DOC_PREFIX}{view.id}"
            _ingest_and_attach(
                service,
                session_id,
                document_id=document_id,
                title=f"{room.room_id} memory {view.id}",
                content=view.statement,
                metadata={
                    "kind": view.kind,
                    "scope": scope,
                    "topic_key": view.topic_key,
                    "supersedes_id": view.supersedes_id or "",
                    "room_id": room.room_id,
                },
                tags=["roommem", f"kind:{view.kind}", f"scope:{scope}"],
            )
            if scope in {"project", "user"}:
                shared_docs.append(document_id)
    new_room_sessions: dict[str, str] = {}
    for room in rooms:
        if room.has_new_room_probes():
            new_room_sessions[room.room_id] = service.create_session(
                f"roommem {room.room_id} (new room, same project, shared)"
            ).id
    for room in rooms:
        # A room's own memory documents were attached when they were ingested.
        own = {f"{XMUSE_MEMORY_DOC_PREFIX}{view.id}" for view in views[room.room_id]}
        for document_id in shared_docs:
            if document_id not in own:
                _attach_document(service, sessions[room.room_id], document_id)
            if room.room_id in new_room_sessions:
                _attach_document(service, new_room_sessions[room.room_id], document_id)
    return _SharedMemoryProject(
        service=service,
        sessions=sessions,
        message_maps=message_maps,
        new_room_sessions=new_room_sessions,
        views=views,
        curator_counts=counts,
    )


@dataclass
class _RoomArmResult:
    results: list[dict[str, Any]]
    write_side: dict[str, Any]
    memories: list[dict[str, Any]] = field(default_factory=list)


def _rewrite_llm(
    *,
    fake_llm: bool,
    settings: Settings | None,
    spec: str | None,
    cache_dir: Path,
    repeat: int,
    usage: LLMUsageTracker,
    factory: Callable[[Settings], CuratorLLM] | None,
) -> CuratorLLM:
    """The ask graph's query rewriter: same model spec as the curator, own cache role."""

    resolved = settings_for_llm_spec(settings or get_settings(), spec)
    if factory is not None:
        return factory(resolved)
    if fake_llm:
        return FakeRewriteLLM()
    built = build_curator_llm(resolved)
    if built is None:
        raise RoomMemConfigError(f"agentic evidence needs {resolved.chat_api_key_name}")
    return DiskCachedCuratorLLM(
        built,
        model=resolved.chat_model,
        cache_dir=cache_dir,
        repeat=repeat,
        usage=usage,
        role="rewrite",
    )


def _run_room_arm(
    *,
    arm: str,
    room: Room,
    repeat: int,
    answerer: RoomMemAnswerer,
    judge: RoomMemJudge,
    scratch_dir: Path,
    embedding: str,
    curated_source: CuratedMemorySource | None,
    raw_project: _RawProject | None = None,
    shared_memory: _SharedMemoryProject | None = None,
    project_rooms: Sequence[Room] | None = None,
    evidence_modes: Sequence[str] = ("plain",),
    rewrite_llm: CuratorLLM | None = None,
) -> _RoomArmResult:
    views: list[CuratedMemoryView] = []
    curator_counts: dict[str, int] = {}
    cross_scope_docs: dict[str, str] = {}
    service: SessionMemoryService | None
    full_evidence: list[EvidenceItem] | None = None
    if arm == "full_context":
        service = None
        session_id = ""
        message_id_map: dict[str, str] = {}
        new_session_id: str | None = None
        full_evidence = full_context_evidence(project_rooms or [room])
    elif raw_project is not None:
        service = raw_project.service
        session_id = raw_project.sessions[room.room_id]
        message_id_map = dict(raw_project.message_maps[room.room_id])
        new_session_id = raw_project.new_room_sessions.get(room.room_id)
    elif shared_memory is not None:
        service = shared_memory.service
        session_id = shared_memory.sessions[room.room_id]
        message_id_map = dict(shared_memory.message_maps[room.room_id])
        new_session_id = shared_memory.new_room_sessions.get(room.room_id)
        views = list(shared_memory.views[room.room_id])
        curator_counts = dict(shared_memory.curator_counts.get(room.room_id, {}))
    else:
        service = SessionMemoryService(
            settings=_room_settings(
                scratch_dir / arm / f"{room.room_id}-r{repeat}",
                embedding=embedding,
            )
        )
        session = service.create_session(f"roommem {room.room_id} ({arm})")
        session_id = session.id
        message_id_map = _ingest_room(service, room, session_id)

        if arm == "oracle":
            views = oracle_curated_memories(room)
        elif arm == "curated":
            if curated_source is None:
                raise RoomMemConfigError("curated arm requires a registered curated memory source")
            views = list(curated_source.curate(service, session_id))
            _validate_curated_views(views, room=room)
            curator_counts = _curator_counts(curated_source)

        new_session_id = None
        if room.has_new_room_probes():
            new_session_id = service.create_session(
                f"roommem {room.room_id} (new room, same project)"
            ).id

        for view in views:
            if view.status != "active":
                continue
            scope = _scope_for_kind(view.kind)
            document_id = f"{XMUSE_MEMORY_DOC_PREFIX}{view.id}"
            _ingest_and_attach(
                service,
                session_id,
                document_id=document_id,
                title=f"{room.room_id} memory {view.id}",
                content=view.statement,
                metadata={
                    "kind": view.kind,
                    "scope": scope,
                    "topic_key": view.topic_key,
                    "supersedes_id": view.supersedes_id or "",
                    "room_id": room.room_id,
                },
                tags=["roommem", f"kind:{view.kind}", f"scope:{scope}"],
            )
            if scope in {"project", "user"}:
                cross_scope_docs[view.id] = document_id
        if new_session_id is not None:
            for document_id in cross_scope_docs.values():
                _attach_document(service, new_session_id, document_id)

    matched_by_gold: dict[str, CuratedMemoryView] = {}
    write_side: dict[str, Any] = {}
    memories: list[dict[str, Any]] = []
    if arm in {"oracle", "curated"}:
        write_side, matched_by_gold = score_write_side(room, views, judge)
        write_side["room"] = room.room_id
        if curator_counts:
            write_side["curator_counts"] = curator_counts
        embedder = getattr(service, "embedding_client", None) if service is not None else None
        if arm == "curated" and embedding == "fastembed" and embedder is not None:
            write_side["conflicts"] = conflict_flag_stats(
                room, views, matched_by_gold, embedder.embed_batch
            )
        memories = _memory_dump_rows(
            arm=arm,
            room=room,
            repeat=repeat,
            views=views,
            matched_by_gold=matched_by_gold,
            write_side=write_side,
        )

    # The oracle arm derives marks from the gold supersede chain: the ceiling of
    # demotion/annotation when every supersede is known.
    modes = list(evidence_modes) if arm in {"curated", "oracle"} else ["plain"]
    marks: list[SupersededQuote] = []
    if service is not None and any(mode != "plain" for mode in modes):
        marks = (
            superseded_quotes(views) if arm == "oracle" else service.superseded_marks(session_id)
        )
    results: list[dict[str, Any]] = []
    for probe in room.probes:
        target_session = new_session_id
        if probe.asked_in != "new_room_same_project" or target_session is None:
            target_session = session_id
        variants: list[tuple[str, list[EvidenceItem], dict[str, Any]]] = []
        if full_evidence is not None:
            variants.append(
                (
                    arm,
                    full_evidence,
                    {"estimated_tokens": sum(item.estimated_tokens for item in full_evidence)},
                )
            )
        else:
            assert service is not None
            package = service.build_context(
                session_id=target_session,
                task=XMUSE_TASK,
                budget=XMUSE_EVIDENCE_BUDGET,
                retrieval_query=probe.question,
                include_global_core=False,
            )
            for mode in modes:
                label = arm if mode == "plain" else f"{arm}+{mode}"
                if mode == "agentic":
                    asked = ask_with(
                        service,
                        target_session,
                        AskRequest(
                            question=probe.question,
                            task=XMUSE_TASK,
                            budget=XMUSE_EVIDENCE_BUDGET,
                        ),
                        llm=rewrite_llm,
                        marks=marks,
                    )
                    items = _ask_evidence_items(asked)
                    variants.append(
                        (
                            label,
                            items,
                            {
                                "estimated_tokens": sum(i.estimated_tokens for i in items),
                                "ask": asked.diagnostics.model_dump(),
                                "queries": asked.queries,
                            },
                        )
                    )
                    continue
                envelope = build_source_evidence(
                    package,
                    schema_version="v2",
                    superseded=marks if mode == "demote" else (),
                )
                variants.append((label, _evidence_items(envelope), envelope))

        for label, evidence, envelope in variants:
            results.append(
                _score_probe(
                    label=label,
                    arm=arm,
                    room=room,
                    probe=probe,
                    repeat=repeat,
                    evidence=evidence,
                    envelope=envelope,
                    answerer=answerer,
                    judge=judge,
                    message_id_map=message_id_map,
                    matched_by_gold=matched_by_gold,
                )
            )

    return _RoomArmResult(results=results, write_side=write_side, memories=memories)


def _ask_evidence_items(asked: AskResponse) -> list[EvidenceItem]:
    """Ask items as the answerer sees them: outdated items carry the current value."""

    return [
        EvidenceItem(
            rank=item.rank,
            item_id=item.item_id,
            layer=item.layer,
            text=render_ask_item(item),
            estimated_tokens=item.estimated_tokens,
            document_id=item.document_id,
            source_refs=tuple(
                {k: v for k, v in ref.items() if k in {"source_type", "source_id", "session_id"}}
                for ref in item.source_refs
            ),
        )
        for item in asked.items
    ]


def _score_probe(
    *,
    label: str,
    arm: str,
    room: Room,
    probe: RoomProbe,
    repeat: int,
    evidence: list[EvidenceItem],
    envelope: Mapping[str, Any],
    answerer: RoomMemAnswerer,
    judge: RoomMemJudge,
    message_id_map: Mapping[str, str],
    matched_by_gold: Mapping[str, CuratedMemoryView],
) -> dict[str, Any]:
    answer = answerer.answer(question=probe.question, evidence=evidence)
    answer_golds = [
        memory
        for memory in (room.gold_memory(memory_id) for memory_id in probe.answer_memory_ids)
        if memory is not None
    ]
    topic_keys = {memory.topic_key for memory in answer_golds}
    current_statements = [memory.statement for memory in answer_golds]
    superseded_statements = [
        memory.statement
        for memory in room.gold_memories
        if memory.superseded_by is not None and memory.topic_key in topic_keys
    ]
    judge_label = judge.judge_answer(
        question=probe.question,
        current_statements=current_statements,
        superseded_statements=superseded_statements,
        answer=answer,
    )

    message_presence, memory_presence = _evidence_presence(
        evidence, message_id_map, room_id=room.room_id
    )
    answer_source_messages = {
        source.message_id for memory in answer_golds for source in memory.sources
    }
    source_hit = bool(answer_source_messages & message_presence)
    answer_view_ids = {
        matched_view.id
        for memory in answer_golds
        if (matched_view := matched_by_gold.get(memory.id)) is not None
    }
    if arm in RAW_LIKE_ARMS:
        hit = source_hit
    else:
        hit = bool(answer_view_ids & memory_presence)
    stale = False
    for memory in room.gold_memories:
        if memory.superseded_by is None or memory.topic_key not in topic_keys:
            continue
        stale_sources = {source.message_id for source in memory.sources}
        if not (stale_sources & message_presence):
            continue
        successor = room.gold_memory(memory.superseded_by)
        if successor is None:
            continue
        successor_present = bool(
            {source.message_id for source in successor.sources} & message_presence
        )
        if arm not in RAW_LIKE_ARMS:
            successor_view = matched_by_gold.get(successor.id)
            if successor_view is not None and successor_view.id in memory_presence:
                successor_present = True
        if not successor_present:
            stale = True
    citations, citation_correct = _citation_correctness(
        answer,
        evidence,
        arm=arm,
        room_id=room.room_id,
        message_id_map=message_id_map,
        answer_source_messages=answer_source_messages,
        answer_view_ids=answer_view_ids,
    )
    evidence_tokens = envelope.get("estimated_tokens")
    row: dict[str, Any] = {
        "arm": label,
        "room": room.room_id,
        "probe": probe.id,
        "asked_in": probe.asked_in,
        "repeat": repeat,
        "question": probe.question,
        "answer_memory_ids": list(probe.answer_memory_ids),
        "evidence_tokens": evidence_tokens if isinstance(evidence_tokens, int) else 0,
        "evidence": [
            {
                "rank": item.rank,
                "item_id": item.item_id,
                "layer": item.layer,
                "document_id": item.document_id,
                "text": item.text,
            }
            for item in evidence
        ],
        "hit": hit,
        "source_hit": source_hit,
        "stale": stale,
        "answer": answer,
        "judge": judge_label if judge_label in JUDGE_LABELS else "wrong",
        "substring": _substring_verdict(probe, answer),
        "citations": citations,
        "citation_correct": citation_correct,
    }
    if "ask" in envelope:
        row["ask"] = envelope["ask"]
        row["queries"] = envelope.get("queries")
    return row


# ---------------------------------------------------------------------------
# Aggregation and reports
# ---------------------------------------------------------------------------


def _stat(values: Sequence[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"mean": sum(values) / len(values), "min": min(values), "max": max(values)}


def _rate(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row.get(key) is True) / len(rows)


def _mean_optional(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [
        float(row[key])
        for row in rows
        if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
    ]
    if not values:
        return None
    return sum(values) / len(values)


def aggregate_read_side(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Per-arm, per-asked_in metrics: mean and min/max across repeats."""

    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    repeats_seen: dict[tuple[str, str], set[int]] = {}
    for row in results:
        arm = str(row["arm"])
        asked_in = str(row["asked_in"])
        repeat = int(row["repeat"])
        grouped.setdefault((arm, asked_in, repeat), []).append(row)
        repeats_seen.setdefault((arm, asked_in), set()).add(repeat)

    aggregated: dict[str, Any] = {}
    for (arm, asked_in), repeats in sorted(repeats_seen.items()):
        per_repeat: dict[str, list[float]] = {
            "hit_at_8": [],
            "source_hit_at_8": [],
            "stale_at_8": [],
            "evidence_tokens": [],
            "judge_correct": [],
            "substring_pass": [],
            "citation_correct": [],
        }
        judge_labels = {label: 0 for label in JUDGE_LABELS}
        probes = 0
        for repeat in sorted(repeats):
            rows = grouped[(arm, asked_in, repeat)]
            probes = len(rows)
            for key, row_key in (
                ("hit_at_8", "hit"),
                ("source_hit_at_8", "source_hit"),
                ("stale_at_8", "stale"),
                ("substring_pass", "substring"),
            ):
                rate = _rate(rows, row_key)
                if rate is not None:
                    per_repeat[key].append(rate)
            tokens = _mean_optional(rows, "evidence_tokens")
            if tokens is not None:
                per_repeat["evidence_tokens"].append(tokens)
            judge_correct = _rate(
                [{"ok": row.get("judge") == "correct"} for row in rows],
                "ok",
            )
            if judge_correct is not None:
                per_repeat["judge_correct"].append(judge_correct)
            for row in rows:
                label = str(row.get("judge"))
                if label in judge_labels:
                    judge_labels[label] += 1
            citations = [row for row in rows if row.get("citation_correct") is not None]
            if citations:
                per_repeat["citation_correct"].append(
                    sum(float(row["citation_correct"]) for row in citations) / len(citations)
                )
        aggregated.setdefault(arm, {})[asked_in] = {
            "probes": probes,
            "repeats": len(repeats),
            "judge_labels": judge_labels,
            "hit_at_8": _stat(per_repeat["hit_at_8"]),
            "source_hit_at_8": _stat(per_repeat["source_hit_at_8"]),
            "stale_at_8": _stat(per_repeat["stale_at_8"]),
            "evidence_tokens": _stat(per_repeat["evidence_tokens"]),
            "judge_correct": _stat(per_repeat["judge_correct"]),
            "substring_pass": _stat(per_repeat["substring_pass"]),
            "citation_correct": _stat(per_repeat["citation_correct"]),
        }
    return aggregated


def build_summary(
    *,
    results: Sequence[dict[str, Any]],
    write_side: dict[str, Any],
    run_meta: Mapping[str, Any],
    usage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "run": dict(run_meta),
        "read_side": aggregate_read_side(results),
        "write_side": write_side,
    }
    if usage is not None:
        summary["usage"] = dict(usage)
    summary["limitations"] = [LIMITATIONS_EN, LIMITATIONS_ZH]
    return summary


def _format_stat(stat: Mapping[str, float] | None, *, digits: int = 2) -> str:
    if stat is None:
        return "-"
    mean = float(stat["mean"])
    text = f"{mean:.{digits}f}"
    if not (float(stat["min"]) == mean == float(stat["max"])):
        text += f" [{float(stat['min']):.{digits}f}, {float(stat['max']):.{digits}f}]"
    return text


def _format_number(value: Any, *, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_summary_md(summary: Mapping[str, Any]) -> str:
    run = summary.get("run") or {}
    lines: list[str] = ["# RoomMem evaluation summary", ""]
    lines.append(
        "Run: arms={arms}; rooms={rooms}; repeats={repeats}; embedding={embedding}; "
        "llm={llm}; curator_window={curator_window}.".format(
            arms=",".join(run.get("arms", [])),
            rooms=",".join(run.get("rooms", [])),
            repeats=run.get("repeats"),
            embedding=run.get("embedding"),
            llm=run.get("llm"),
            curator_window=run.get("curator_window", "-"),
        )
    )
    lines.append("")

    lines.append("## Read side")
    lines.append("")
    read_side = summary.get("read_side") or {}
    for arm in sorted(read_side):
        lines.append(f"### {arm}")
        lines.append("")
        lines.append(
            "| asked_in | probes | repeats | hit@8 | stale@8 | evidence tokens | "
            "judge correct | judge stale | judge missing | judge wrong | substring pass | "
            "citation correct |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        asked_groups = read_side[arm]
        for asked_in in sorted(asked_groups):
            metrics = asked_groups[asked_in]
            labels = metrics.get("judge_labels") or {}
            repeats = int(metrics.get("repeats") or 1)
            probes = int(metrics.get("probes") or 0)
            row = (
                "| {asked_in} | {probes} | {repeats} | {hit} | {stale} | {tokens} | "
                "{correct} | {stale_label} | {missing} | {wrong} | {substring} | {citations} |"
            )
            lines.append(
                row.format(
                    asked_in=asked_in,
                    probes=probes,
                    repeats=repeats,
                    hit=_format_stat(metrics.get("hit_at_8")),
                    stale=_format_stat(metrics.get("stale_at_8")),
                    tokens=_format_stat(metrics.get("evidence_tokens"), digits=1),
                    correct=_format_stat(metrics.get("judge_correct")),
                    stale_label=_format_rate(labels.get("stale"), probes, repeats),
                    missing=_format_rate(labels.get("missing"), probes, repeats),
                    wrong=_format_rate(labels.get("wrong"), probes, repeats),
                    substring=_format_stat(metrics.get("substring_pass")),
                    citations=_format_stat(metrics.get("citation_correct")),
                )
            )
        lines.append("")

    lines.append("## Write side")
    lines.append("")
    lines.append(
        "| arm | memories | matched gold | precision | recall | unmatched rate | noise rate | "
        "supersede rate | stale active rate | duplicate rate | kind agreement | "
        "scope agreement | unmatched legit/noise |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    write_side = summary.get("write_side") or {}
    for arm in sorted(write_side):
        payload = write_side[arm]
        rates = payload.get("rates") or {}
        judged = payload.get("unmatched_judged") or {}
        lines.append(
            "| {arm} | {memories} | {matched}/{gold} | {precision} | {recall} | "
            "{unmatched} | {noise} | {supersede} | {stale_active} | {duplicate} | "
            "{kind_agree} | {scope_agree} | {legit}/{noise_n} |".format(
                arm=arm,
                memories=payload.get("memories", 0),
                matched=payload.get("matched", 0),
                gold=payload.get("gold", 0),
                precision=_format_number(rates.get("precision")),
                recall=_format_number(rates.get("recall")),
                unmatched=_format_number(rates.get("unmatched_rate")),
                noise=_format_number(rates.get("noise_rate")),
                supersede=_format_number(rates.get("supersede_rate")),
                stale_active=_format_number(rates.get("stale_active_rate")),
                duplicate=_format_number(rates.get("duplicate_rate")),
                kind_agree=_format_number(rates.get("kind_agreement")),
                scope_agree=_format_number(rates.get("scope_agreement")),
                legit=judged.get("legit_unannotated", 0),
                noise_n=judged.get("noise", 0),
            )
        )
    lines.append("")
    curated = write_side.get("curated")
    if isinstance(curated, dict) and curated.get("chain_pairs"):
        lines.append(
            "Chain key consistency (both ends of a gold supersede chain share one curated "
            "topic_key): {consistent}/{pairs} = {rate}.".format(
                consistent=curated.get("chain_key_consistent", 0),
                pairs=curated.get("chain_pairs", 0),
                rate=_format_number((curated.get("rates") or {}).get("chain_key_consistency")),
            )
        )
        lines.append("")
    conflicts = curated.get("conflicts") if isinstance(curated, dict) else None
    if isinstance(conflicts, dict) and conflicts.get("flagged"):
        pairs = conflicts.get("pairs") or {}
        lines.append("### Possible-conflict flags (FastEmbed, different topic keys)")
        lines.append("")
        lines.append(
            "Active pairs with different keys: same gold topic {same}, different gold topic "
            "{different}, unknown {unknown}.".format(
                same=pairs.get("same_topic", 0),
                different=pairs.get("different_topic", 0),
                unknown=pairs.get("unknown", 0),
            )
        )
        lines.append("")
        lines.append(
            "| threshold | flagged same topic | flagged different topic | flagged unknown | "
            "false positive rate | same-topic recall |"
        )
        lines.append("|---|---|---|---|---|---|")
        rates_by_threshold = conflicts.get("rates") or {}
        for threshold, counts in conflicts["flagged"].items():
            rate = rates_by_threshold.get(threshold) or {}
            lines.append(
                f"| {threshold} | {counts.get('same_topic', 0)} | "
                f"{counts.get('different_topic', 0)} | {counts.get('unknown', 0)} | "
                f"{_format_number(rate.get('false_positive_rate'))} | "
                f"{_format_number(rate.get('same_topic_recall'))} |"
            )
        lines.append("")
    curator_rooms = curated.get("curator_rooms") if isinstance(curated, dict) else None
    if isinstance(curator_rooms, dict) and curator_rooms:
        lines.append("### Curator counters")
        lines.append("")
        lines.append(
            "| room | windows | added | superseded | noop | rejected grounding | "
            "rejected schema | llm errors |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for room_id in sorted(curator_rooms):
            counters = curator_rooms[room_id] or {}
            lines.append(
                "| {room} | {windows} | {added} | {superseded} | {noop} | "
                "{grounding} | {schema} | {llm_errors} |".format(
                    room=room_id,
                    windows=counters.get("windows", 0),
                    added=counters.get("added", 0),
                    superseded=counters.get("superseded", 0),
                    noop=counters.get("noop", 0),
                    grounding=counters.get("rejected_grounding", 0),
                    schema=counters.get("rejected_schema", 0),
                    llm_errors=counters.get("llm_errors", 0),
                )
            )
        lines.append("")
    if isinstance(curated, dict) and curated.get("notes"):
        for note in curated["notes"]:
            lines.append(f"- {note}")
        lines.append("")

    usage = summary.get("usage")
    if isinstance(usage, Mapping) and usage:
        lines.append("## LLM usage")
        lines.append("")
        roles = usage.get("roles") or {}
        if isinstance(roles, Mapping) and roles:
            lines.append(
                "| role | calls | cached | tokens in | tokens out | mean latency s | "
                "p50 latency s | p95 latency s |"
            )
            lines.append("|---|---|---|---|---|---|---|---|")
            for role in sorted(roles):
                payload = roles[role] if isinstance(roles[role], Mapping) else {}
                latency = payload.get("latency_s")
                if not isinstance(latency, Mapping):
                    latency = {}
                lines.append(
                    "| {role} | {calls} | {cached} | {tokens_in} | {tokens_out} | "
                    "{mean} | {p50} | {p95} |".format(
                        role=role,
                        calls=payload.get("calls", 0),
                        cached=payload.get("cached", 0),
                        tokens_in=_format_number(payload.get("tokens_in"), digits=0),
                        tokens_out=_format_number(payload.get("tokens_out"), digits=0),
                        mean=_format_number(latency.get("mean"), digits=3),
                        p50=_format_number(latency.get("p50"), digits=3),
                        p95=_format_number(latency.get("p95"), digits=3),
                    )
                )
            lines.append("")
        curator_usage = usage.get("curator")
        if isinstance(curator_usage, Mapping):
            lines.append(
                "Curator: {messages} messages in {windows} windows; "
                "{tokens} tokens per 100 messages; {seconds} s per window.".format(
                    messages=curator_usage.get("messages", 0),
                    windows=curator_usage.get("windows", 0),
                    tokens=_format_number(curator_usage.get("tokens_per_100_messages"), digits=1),
                    seconds=_format_number(curator_usage.get("seconds_per_window"), digits=3),
                )
            )
            lines.append("")
        cost = usage.get("estimated_cost")
        if isinstance(cost, Mapping) and isinstance(cost.get("cost"), (int, float)):
            lines.append(
                "Estimated cost (provider tokens only): ${cost:.4f} at ${price_in} /Mtok in, "
                "${price_out} /Mtok out.".format(
                    cost=float(cost["cost"]),
                    price_in=_format_number(cost.get("price_in_per_mtok")),
                    price_out=_format_number(cost.get("price_out_per_mtok")),
                )
            )
            lines.append("")

    lines.append("## Limitations")
    lines.append("")
    limitations = summary.get("limitations") or []
    for limitation in limitations:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _format_rate(count: Any, probes: int, repeats: int) -> str:
    if not isinstance(count, int) or probes <= 0 or repeats <= 0:
        return "-"
    return f"{count / (probes * repeats):.2f}"


def write_reports(
    out_dir: Path,
    *,
    results: Sequence[dict[str, Any]],
    write_side: dict[str, Any],
    summary: dict[str, Any],
    memories: Sequence[dict[str, Any]] = (),
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    memories_path = out_dir / "memories.jsonl"
    with memories_path.open("w", encoding="utf-8") as handle:
        for row in memories:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_side_path = out_dir / "write_side.json"
    write_side_path.write_text(
        json.dumps(write_side, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary_md_path = out_dir / "summary.md"
    summary_md_path.write_text(render_summary_md(summary), encoding="utf-8")
    return {
        "results": results_path,
        "memories": memories_path,
        "write_side": write_side_path,
        "summary": summary_path,
        "summary_md": summary_md_path,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_roommem(
    rooms: Sequence[Room],
    *,
    out_dir: str | Path,
    arms: Sequence[str] = ("raw", "oracle"),
    repeats: int = 1,
    embedding: str = "none",
    curated_source_name: str = "default",
    curator_window: int = 12,
    curated_llm_factory: Callable[[Settings], CuratorLLM] | None = None,
    llm_factory: LLMFactory | None = None,
    fake_llm: bool = False,
    llm_label: str | None = None,
    settings: Settings | None = None,
    scratch_root: str | Path | None = None,
    usage: LLMUsageTracker | None = None,
    price_in_per_mtok: float | None = None,
    price_out_per_mtok: float | None = None,
    answerer_llm: str | None = None,
    judge_llm: str | None = None,
    curator_llm: str | None = None,
    merge_project: str | None = None,
    shared_project: bool = False,
    curated_evidence: Sequence[str] = ("plain",),
    rewrite_llm_factory: Callable[[Settings], CuratorLLM] | None = None,
) -> dict[str, Any]:
    """Run the RoomMem harness and write results/summary reports.

    ``curated_evidence`` lists how the curated arm builds evidence (see
    :data:`EVIDENCE_MODES`); every mode after ``plain`` is reported as its own
    arm label, e.g. ``curated+demote``.

    ``answerer_llm``/``judge_llm``/``curator_llm`` are optional
    ``provider:model[@wire]`` role specs (see :func:`settings_for_llm_spec`)
    so one variable can change while the others stay fixed.
    ``merge_project`` puts every selected room into one project (the scale
    experiment); ``shared_project`` makes the curated and oracle arms deliver
    project/user-scope memories of every room to every room of the project,
    as xmuse does, instead of only within the room that produced them.
    Returns the summary payload that was written to ``summary.json``.
    """

    if not rooms:
        raise RoomMemDataError("RoomMem run needs at least one room")
    if merge_project is not None:
        if not merge_project.strip():
            raise RoomMemConfigError("merge project name must not be empty")
        rooms = [room.model_copy(update={"project": merge_project.strip()}) for room in rooms]
    selected_arms = list(arms)
    if not selected_arms:
        raise RoomMemConfigError("at least one arm is required")
    for arm in selected_arms:
        if arm not in ARM_VALUES:
            raise RoomMemConfigError(f"unknown arm {arm!r}; valid arms: {', '.join(ARM_VALUES)}")
    if repeats < 1:
        raise RoomMemConfigError("repeats must be at least 1")
    if curator_window < 1:
        raise RoomMemConfigError("curator window must be at least 1 message")
    if embedding not in EMBEDDING_VALUES:
        raise RoomMemConfigError(
            f"unknown embedding mode {embedding!r}; valid: {', '.join(EMBEDDING_VALUES)}"
        )
    if embedding == "fastembed":
        _require_fastembed()
    evidence_modes = list(dict.fromkeys(curated_evidence)) or ["plain"]
    for mode in evidence_modes:
        if mode not in EVIDENCE_MODES:
            raise RoomMemConfigError(
                f"unknown curated evidence mode {mode!r}; valid: {', '.join(EVIDENCE_MODES)}"
            )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    tracker = usage if usage is not None else LLMUsageTracker()
    factory = llm_factory or build_llm_factory(
        out_dir=out_path,
        fake_llm=fake_llm,
        settings=settings,
        usage=tracker,
        answerer_llm=answerer_llm,
        judge_llm=judge_llm,
    )
    if llm_label is None and llm_factory is None and not fake_llm:
        resolved = settings or get_settings()
        roles = {
            "answerer": settings_for_llm_spec(resolved, answerer_llm),
            "judge": settings_for_llm_spec(resolved, judge_llm),
        }
        if "curated" in selected_arms:
            roles["curator"] = settings_for_llm_spec(resolved, curator_llm)
        labels = {role: llm_spec_label(role_settings) for role, role_settings in roles.items()}
        if len(set(labels.values())) == 1:
            llm_label = next(iter(labels.values()))
        else:
            llm_label = ", ".join(f"{role}={label}" for role, label in labels.items())

    created_scratch = scratch_root is None
    scratch_dir = (
        Path(scratch_root)
        if scratch_root is not None
        else Path(tempfile.mkdtemp(prefix="roommem-"))
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    memories: list[dict[str, Any]] = []
    write_side_per_room: dict[str, list[dict[str, Any]]] = {arm: [] for arm in selected_arms}
    try:
        for arm in selected_arms:
            for repeat in range(repeats):
                answerer, judge = factory(repeat)
                curated_source: CuratedMemorySource | None = None
                if arm == "curated":
                    curated_source = build_curated_source(
                        curated_source_name,
                        context=CuratedSourceContext(
                            window=curator_window,
                            fake_llm=fake_llm,
                            repeat=repeat,
                            cache_dir=out_path / "llm_cache",
                            llm_factory=curated_llm_factory,
                            usage=tracker,
                            llm_spec=curator_llm,
                        ),
                    )
                rewrite_llm: CuratorLLM | None = None
                if arm in {"curated", "oracle"} and "agentic" in evidence_modes:
                    rewrite_llm = _rewrite_llm(
                        fake_llm=fake_llm,
                        settings=settings,
                        spec=curator_llm,
                        cache_dir=out_path / "llm_cache",
                        repeat=repeat,
                        usage=tracker,
                        factory=rewrite_llm_factory,
                    )
                raw_project_contexts: dict[str, _RawProject] = {}
                shared_contexts: dict[str, _SharedMemoryProject] = {}
                rooms_by_project = _rooms_by_project(rooms)
                # Reproducible ids per (arm, repeat, room/project): reruns render the
                # same curator prompts, so the disk cache resumes interrupted runs.
                if arm == "raw_project":
                    for project, project_rooms in rooms_by_project.items():
                        with deterministic_ids(f"{arm}:r{repeat}:project:{project}"):
                            raw_project_contexts[project] = _build_raw_project_context(
                                project=project,
                                rooms=project_rooms,
                                repeat=repeat,
                                scratch_dir=scratch_dir,
                                embedding=embedding,
                            )
                if shared_project and arm in {"curated", "oracle"}:
                    for project, project_rooms in rooms_by_project.items():
                        with deterministic_ids(f"{arm}:r{repeat}:project:{project}"):
                            shared_contexts[project] = _build_shared_memory_project(
                                arm=arm,
                                project=project,
                                rooms=project_rooms,
                                repeat=repeat,
                                scratch_dir=scratch_dir,
                                embedding=embedding,
                                curated_source=curated_source,
                            )
                for room in rooms:
                    with deterministic_ids(f"{arm}:r{repeat}:room:{room.room_id}"):
                        room_result = _run_room_arm(
                            arm=arm,
                            room=room,
                            repeat=repeat,
                            answerer=answerer,
                            judge=judge,
                            scratch_dir=scratch_dir,
                            embedding=embedding,
                            curated_source=curated_source,
                            raw_project=raw_project_contexts.get(room.project),
                            shared_memory=shared_contexts.get(room.project),
                            project_rooms=rooms_by_project.get(room.project),
                            evidence_modes=evidence_modes,
                            rewrite_llm=rewrite_llm,
                        )
                    results.extend(room_result.results)
                    memories.extend(room_result.memories)
                    if room_result.write_side:
                        write_side_per_room[arm].append(room_result.write_side)
    finally:
        if created_scratch:
            shutil.rmtree(scratch_dir, ignore_errors=True)

    write_side: dict[str, Any] = {}
    for arm in selected_arms:
        payloads = write_side_per_room[arm]
        if payloads:
            pooled = pool_write_side(payloads)
            if arm == "curated":
                pooled["curator_rooms"] = _curator_counters_by_room(payloads)
                pooled["notes"] = [
                    "Cross-scope delivery (rule -> project, preference -> user) is simulated "
                    "as operator-approved and attached to the room session and the "
                    "new-room probe session.",
                    "Curated memories match gold by source-message overlap only; kind and "
                    "scope agreement are reported as separate metrics.",
                    "Unmatched memories are judged into legit_unannotated vs noise; "
                    "noise_rate counts judged noise over all memories.",
                ]
            write_side[arm] = pooled

    run_meta: dict[str, Any] = {
        "arms": selected_arms,
        "rooms": [room.room_id for room in rooms],
        "repeats": repeats,
        "embedding": embedding,
        "llm": llm_label or ("fake" if fake_llm else "custom"),
        "curated_source": curated_source_name if "curated" in selected_arms else None,
        "curated_evidence": (
            evidence_modes if {"curated", "oracle"} & set(selected_arms) else None
        ),
        "curator_window": curator_window if "curated" in selected_arms else None,
        "merge_project": merge_project,
        "shared_project": shared_project,
    }
    usage_payload = tracker.aggregate()
    curator_usage = _curator_usage_extras(
        usage_payload, rooms=rooms, repeats=repeats, write_side=write_side
    )
    if curator_usage is not None:
        usage_payload["curator"] = curator_usage
    estimated_cost = _estimated_cost(
        usage_payload,
        price_in_per_mtok=price_in_per_mtok,
        price_out_per_mtok=price_out_per_mtok,
    )
    if estimated_cost is not None:
        usage_payload["estimated_cost"] = estimated_cost
    summary_usage = (
        usage_payload
        if usage_payload.get("roles")
        or usage_payload.get("curator")
        or usage_payload.get("estimated_cost")
        else None
    )
    summary = build_summary(
        results=results, write_side=write_side, run_meta=run_meta, usage=summary_usage
    )
    write_reports(
        out_path, results=results, write_side=write_side, summary=summary, memories=memories
    )
    return summary


__all__ = [
    "ARM_VALUES",
    "ANSWERER_SYSTEM_PROMPT",
    "CURATOR_COUNTER_KEYS",
    "RAW_LIKE_ARMS",
    "SPLIT_PRESETS",
    "ChatAnswerer",
    "ChatJudge",
    "CuratedMemorySource",
    "CuratedMemoryView",
    "CuratedSourceContext",
    "CuratorMemorySource",
    "RemoteChatClient",
    "DiskCachedChatClient",
    "DiskCachedCuratorLLM",
    "EvidenceItem",
    "FakeAnswerer",
    "FakeCuratorLLM",
    "FakeJudge",
    "GoldMemory",
    "GoldMemorySource",
    "LIMITATIONS_EN",
    "LIMITATIONS_ZH",
    "LLMUsage",
    "LLMUsageTracker",
    "Room",
    "RoomMemAnswerer",
    "RoomMemConfigError",
    "RoomMemDataError",
    "RoomMemError",
    "RoomMemJudge",
    "RoomMessage",
    "RoomProbe",
    "aggregate_read_side",
    "build_curated_source",
    "build_llm_factory",
    "build_summary",
    "load_room",
    "load_rooms",
    "match_curated_to_gold",
    "oracle_curated_memories",
    "pool_write_side",
    "register_curated_source",
    "registered_curated_sources",
    "render_summary_md",
    "resolve_split",
    "run_roommem",
    "score_write_side",
    "unregister_curated_source",
    "write_reports",
]
