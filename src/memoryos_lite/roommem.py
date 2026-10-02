"""RoomMem evaluation harness.

RoomMem measures a memory curator that reads multi-agent chat-room
transcripts (a human plus 2-3 AI agents collaborating on a project) and must
store the right long-term memories, merge duplicates, supersede outdated ones
and ignore noise, then answer probe questions from memory.

This module replays the dataset through an in-process :class:`MemoryOSService`
using exactly the calls the HTTP handlers in ``api/app.py`` make for
``/sessions``, ``/ingest``, ``/archives/ingest``, ``/archives/attachments``
and ``/build-context`` with the ``source_evidence/v2`` response profile.

Arms
----
``raw``
    Mirrors the xmuse Room host today: session messages plus one archive
    document per message (the document outbox), archive-only retrieval, and
    optionally ``MEMORYOS_AGENT_KERNEL=external`` advisories as the write-side
    heuristic baseline (``--heuristic-advisories``).
``oracle``
    Upper bound used by tests and CI: the curated memories ARE the room's gold
    memories, mapped onto the ingested MemoryOS message ids.
``curated``
    Uses a :class:`CuratedMemorySource` registered by name through
    :func:`register_curated_source`.  The real Curator adapter is not part of
    this module; the CLI fails with a clear message when ``curated`` is
    requested but no source has been registered.

Known limitations (fixed paragraph, repeated in every report): the dataset is
LLM-authored with a single reviewer; the curated arm's cross-room delivery
(rule -> project, preference -> user) assumes operator approval; the answerer
and the curator share the DeepSeek model family.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveDocumentIngestRequest,
    ArchiveIdentityArchive,
    ArchiveSourceRefPayload,
    MessageCreate,
    Role,
)
from memoryos_lite.source_evidence import build_source_evidence

ROOM_KINDS: tuple[str, ...] = ("fact", "decision", "rule", "preference", "lesson")
FACT_FAMILY = frozenset({"fact", "lesson"})
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
ARM_VALUES: tuple[str, ...] = ("raw", "oracle", "curated")
EMBEDDING_VALUES: tuple[str, ...] = ("none", "fastembed")

#: Task text and retrieval parameters xmuse sends to ``/build-context``.
XMUSE_TASK = "Recall prior source-backed Room evidence relevant to this observation."
XMUSE_EVIDENCE_BUDGET = 800
MAX_SOURCE_EVIDENCE_ITEMS = 8

XMUSE_MESSAGE_ID_PREFIX = "xmuse-room-message-"
XMUSE_ACTIVITY_DOC_PREFIX = "xmuse-room-activity-"
XMUSE_MEMORY_DOC_PREFIX = "xmuse-room-memory-candidate-"

EVIDENCE_TEXT_LIMIT = 200
CITATION_RE = re.compile(r"\[(\d{1,2})\]")
_TOPIC_KEY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
_MESSAGE_ID_RE = re.compile(r"^m(\d{2,4})$")

JUDGE_LABELS: tuple[str, ...] = ("correct", "stale", "missing", "wrong")
UNMATCHED_LABELS: tuple[str, ...] = ("legit_unannotated", "noise")

LIMITATIONS_ZH = (
    "数据由 LLM 起草，只有单一审阅者；curated arm 的跨 Room 部分假设操作员批准；"
    "answerer 与 curator 同属 DeepSeek 家族。"
)
LIMITATIONS_EN = (
    "The dataset is LLM-authored with a single reviewer; the curated arm's "
    "cross-room delivery assumes operator approval; the answerer and the "
    "curator share the DeepSeek model family."
)


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


class CuratedMemorySource(Protocol):
    """Adapter boundary for a real Curator (added outside this module).

    The harness calls :meth:`curate` once per room session, after the room
    transcript has been ingested, and treats the returned views as the
    curator's full memory output for that room.  An optional ``last_counts``
    attribute (mapping or zero-argument callable) may report
    ``grounding_rejects`` and ``schema_failures`` for the run.
    """

    def curate(
        self,
        service: MemoryOSService,
        session_id: str,
    ) -> list[CuratedMemoryView]: ...


_curated_sources: dict[str, Callable[[], CuratedMemorySource]] = {}


def register_curated_source(name: str, factory: Callable[[], CuratedMemorySource]) -> None:
    """Register a curated-memory source factory under ``name``.

    This is the hook a Curator adapter uses; ``factory()`` must return a fresh
    :class:`CuratedMemorySource` per run.
    """

    if not name:
        raise RoomMemConfigError("curated source name must not be empty")
    _curated_sources[name] = factory


def unregister_curated_source(name: str) -> None:
    _curated_sources.pop(name, None)


def registered_curated_sources() -> list[str]:
    return sorted(_curated_sources)


def build_curated_source(name: str) -> CuratedMemorySource:
    factory = _curated_sources.get(name)
    if factory is None:
        available = ", ".join(registered_curated_sources()) or "(none registered)"
        raise RoomMemConfigError(
            f"no curated memory source is registered under {name!r}; "
            f"registered sources: {available}. "
            "A Curator adapter must call "
            "memoryos_lite.roommem.register_curated_source(name, factory) "
            "before running --arm curated."
        )
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
    for key in ("grounding_rejects", "schema_failures"):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            counts[key] = value
    return counts


def _scope_for_kind(kind: str) -> str:
    return FIXED_SCOPE_BY_KIND.get(kind, "room")


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


class DeepSeekChatClient:
    """Chat client built like the repo's existing DeepSeek/OpenAI wiring."""

    def __init__(self, settings: Settings) -> None:
        if settings.resolved_llm_provider != "deepseek":
            raise RoomMemConfigError(
                "RoomMem LLM roles require MEMORYOS_LLM_PROVIDER=deepseek (or run with --fake-llm)"
            )
        api_key = settings.chat_api_key
        if not api_key:
            raise RoomMemConfigError(
                f"{settings.chat_api_key_name} is required for non-fake RoomMem runs "
                "(or run with --fake-llm)"
            )
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI
            from pydantic import SecretStr
        except ImportError as exc:
            raise RoomMemConfigError(
                "RoomMem LLM roles require the remote extra: "
                "install memoryos-lite[remote] (or run with --fake-llm)"
            ) from exc
        kwargs: dict[str, Any] = {}
        if settings.chat_base_url:
            kwargs["base_url"] = settings.chat_base_url
        self._model = settings.chat_model
        self._system_message = SystemMessage
        self._human_message = HumanMessage
        self._llm = ChatOpenAI(
            model=self._model,
            api_key=SecretStr(api_key),
            temperature=0.0,
            timeout=settings.memoryos_llm_timeout_s,
            **kwargs,
        )

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
        content = response.content
        return content if isinstance(content, str) else str(content)


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
    ) -> None:
        if repeat < 0:
            raise ValueError("repeat index must be non-negative")
        self._inner = inner
        self._role = role
        self._cache_dir = Path(cache_dir)
        self._repeat = repeat

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
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                response = payload["response"]
                if isinstance(response, str):
                    return response
            except (OSError, ValueError, KeyError):
                pass
        response = self._inner.complete(system=system, user=user)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"role": self._role, "model": self._inner.model, "response": response},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return response


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
    """Chat-backed answerer; wired to DeepSeek by the CLI."""

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
    """Chat-backed judge; wired to DeepSeek by the CLI."""

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
) -> LLMFactory:
    """Create the per-repeat answerer/judge factory.

    Non-fake runs use one DeepSeek chat client behind per-role, per-repeat disk
    caches under ``out_dir/llm_cache``.  The client is built eagerly so missing
    credentials fail before any room is ingested.
    """

    if fake_llm:
        return lambda repeat: (FakeAnswerer(), FakeJudge())
    resolved = settings or get_settings()
    base = DeepSeekChatClient(resolved)
    cache_dir = out_dir / "llm_cache"

    def factory(repeat: int) -> tuple[RoomMemAnswerer, RoomMemJudge]:
        answerer_chat = DiskCachedChatClient(
            base, role="answerer", cache_dir=cache_dir, repeat=repeat
        )
        judge_chat = DiskCachedChatClient(base, role="judge", cache_dir=cache_dir, repeat=repeat)
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


def _kind_compatible(curated_kind: str, gold_kind: str) -> bool:
    if curated_kind == gold_kind:
        return True
    return curated_kind in FACT_FAMILY and gold_kind in FACT_FAMILY


def curated_candidate_pairs(
    curated: Sequence[CuratedMemoryView],
    gold: Sequence[GoldMemory],
) -> list[CuratedGoldMatch]:
    """All compatible curated/gold pairs with non-empty source overlap."""

    pairs: list[CuratedGoldMatch] = []
    for view in curated:
        view_messages = {source.message_id for source in view.sources}
        for memory in gold:
            if not _kind_compatible(view.kind, memory.kind):
                continue
            overlap = len(view_messages & {source.message_id for source in memory.sources})
            if overlap:
                pairs.append(CuratedGoldMatch(view.id, memory.id, overlap))
    return pairs


def match_curated_to_gold(
    curated: Sequence[CuratedMemoryView],
    gold: Sequence[GoldMemory],
) -> list[CuratedGoldMatch]:
    """One-to-one greedy matching by overlap size (deterministic tie-break)."""

    pairs = curated_candidate_pairs(curated, gold)
    ordered = sorted(pairs, key=lambda pair: (-pair.overlap, pair.curated_id, pair.gold_id))
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

    Returns the metrics payload and the gold-id -> curated view map used by the
    read side for evidence-hit checks.
    """

    gold = room.gold_memories
    view_by_id = {view.id: view for view in curated}
    matches = match_curated_to_gold(curated, gold)
    matched_view_ids = {match.curated_id for match in matches}
    matched_by_gold: dict[str, CuratedMemoryView] = {}
    for match in matches:
        matched_by_gold.setdefault(match.gold_id, view_by_id[match.curated_id])

    candidates_by_gold: dict[str, list[str]] = {}
    for pair in curated_candidate_pairs(curated, gold):
        candidates_by_gold.setdefault(pair.gold_id, []).append(pair.curated_id)

    noise_ids = room.noise_message_ids()
    unmatched = [view for view in curated if view.id not in matched_view_ids]

    judged = {label: 0 for label in UNMATCHED_LABELS}
    for view in unmatched:
        message_texts = {
            source.message_id: room.message(source.message_id).text  # type: ignore[union-attr]
            for source in view.sources
        }
        label = judge.judge_unmatched_memory(memory=view, message_texts=message_texts)
        judged[label if label in UNMATCHED_LABELS else "noise"] += 1

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

    primary_noise = sum(
        1 for view in curated if view.sources and view.sources[0].message_id in noise_ids
    )
    noise_flag = sum(
        1
        for view in curated
        if view.id not in matched_view_ids
        or (view.sources and view.sources[0].message_id in noise_ids)
    )
    superseded_gold = [memory for memory in gold if memory.superseded_by is not None]
    supersede_correct = 0
    for memory in superseded_gold:
        matched_view = matched_by_gold.get(memory.id)
        if matched_view is not None and matched_view.status == "superseded":
            supersede_correct += 1
    duplicate_golds = sum(
        1
        for view_ids in candidates_by_gold.values()
        if sum(1 for view_id in view_ids if view_by_id[view_id].status == "active") > 1
    )

    memories = len(curated)
    matched = len(matches)
    gold_total = len(gold)
    with_matches = len(candidates_by_gold)
    metrics: dict[str, Any] = {
        "memories": memories,
        "matched": matched,
        "gold": gold_total,
        "unmatched": len(unmatched),
        "primary_noise": primary_noise,
        "noise_flag": noise_flag,
        "unmatched_judged": dict(judged),
        "noise_types": {name: dict(stats) for name, stats in sorted(noise_type_stats.items())},
        "superseded_gold": len(superseded_gold),
        "supersede_correct": supersede_correct,
        "golds_with_matches": with_matches,
        "duplicate_golds": duplicate_golds,
        "rates": {
            "precision": (matched / memories) if memories else None,
            "recall": matched / gold_total,
            "noise_rate": (noise_flag / memories) if memories else None,
            "primary_noise_rate": (primary_noise / memories) if memories else None,
            "supersede_rate": (
                supersede_correct / len(superseded_gold) if superseded_gold else None
            ),
            "duplicate_rate": (duplicate_golds / with_matches) if with_matches else None,
        },
    }
    return metrics, matched_by_gold


def pool_write_side(per_room: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pool per-room curated write-side payloads into an arm-level aggregate."""

    if not per_room:
        return {}
    totals: dict[str, int] = {
        "memories": 0,
        "matched": 0,
        "gold": 0,
        "unmatched": 0,
        "primary_noise": 0,
        "noise_flag": 0,
        "superseded_gold": 0,
        "supersede_correct": 0,
        "golds_with_matches": 0,
        "duplicate_golds": 0,
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
    pooled["rates"] = {
        "precision": (totals["matched"] / totals["memories"]) if totals["memories"] else None,
        "recall": totals["matched"] / totals["gold"] if totals["gold"] else None,
        "noise_rate": (totals["noise_flag"] / totals["memories"]) if totals["memories"] else None,
        "primary_noise_rate": (
            (totals["primary_noise"] / totals["memories"]) if totals["memories"] else None
        ),
        "supersede_rate": (
            (totals["supersede_correct"] / totals["superseded_gold"])
            if totals["superseded_gold"]
            else None
        ),
        "duplicate_rate": (
            (totals["duplicate_golds"] / totals["golds_with_matches"])
            if totals["golds_with_matches"]
            else None
        ),
    }
    return pooled


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


def _evidence_presence(
    evidence: Sequence[EvidenceItem],
    message_id_map: Mapping[str, str],
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
                message_ids.add(candidate[len(XMUSE_ACTIVITY_DOC_PREFIX) :])
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
                if candidate[len(XMUSE_ACTIVITY_DOC_PREFIX) :] in answer_source_messages:
                    correct = True
            elif candidate.startswith(XMUSE_MEMORY_DOC_PREFIX):
                if arm != "raw" and candidate[len(XMUSE_MEMORY_DOC_PREFIX) :] in answer_view_ids:
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
    kernel_external: bool,
) -> Settings:
    kwargs: dict[str, Any] = {
        "data_dir": data_dir,
        "memoryos_memory_arch": "v3",
        "memoryos_recall_pipeline": "v2",
        "memoryos_paging_mode": "off",
        "memoryos_agent_kernel": "external" if kernel_external else "off",
        "memoryos_embedding_provider": "fastembed" if embedding == "fastembed" else "none",
    }
    return Settings(**kwargs)


def _require_fastembed() -> None:
    from importlib.util import find_spec

    if find_spec("fastembed") is None:
        raise RoomMemConfigError(
            "--embedding fastembed requires the full-local extra: install memoryos-lite[full-local]"
        )


def _ingest_and_attach(
    service: MemoryOSService,
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
    service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id=document_id,
            scope_type="session",
            scope_id=session_id,
            source_refs=[ref],
        )
    )


def _ingest_room(service: MemoryOSService, room: Room, session_id: str) -> dict[str, str]:
    """Ingest the transcript and the per-message document outbox.

    Returns the dataset-message-id -> MemoryOS-message-id map.
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
        _ingest_and_attach(
            service,
            session_id,
            document_id=f"{XMUSE_ACTIVITY_DOC_PREFIX}{message.id}",
            title=f"{room.room_id} message {message.id}",
            content=message.text,
            metadata={"participant_id": message.speaker},
        )
    return message_id_map


def _advisory_message_ids(
    advisory: Mapping[str, Any],
    message_id_map: Mapping[str, str],
) -> set[str]:
    reverse = {memoryos_id: dataset_id for dataset_id, memoryos_id in message_id_map.items()}
    message_ids: set[str] = set()
    refs = advisory.get("source_refs")
    if not isinstance(refs, list):
        return message_ids
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        source_id = str(ref.get("source_id", ""))
        if ref.get("source_type") == "message" and source_id in reverse:
            message_ids.add(reverse[source_id])
        elif source_id.startswith(XMUSE_ACTIVITY_DOC_PREFIX):
            message_ids.add(source_id[len(XMUSE_ACTIVITY_DOC_PREFIX) :])
    return message_ids


def _score_heuristic_advisories(
    room: Room,
    advisories: Sequence[Mapping[str, Any]],
    message_id_map: Mapping[str, str],
) -> dict[str, Any]:
    gold_with_match: set[str] = set()
    matched_advisories = 0
    cited_noise: dict[str, int] = {}
    noise_ids = room.noise_message_ids()
    noise_types = room.noise_type_by_message()
    for advisory in advisories:
        source_ids = _advisory_message_ids(advisory, message_id_map)
        matched = False
        for memory in room.gold_memories:
            if source_ids & {source.message_id for source in memory.sources}:
                gold_with_match.add(memory.id)
                matched = True
        if matched:
            matched_advisories += 1
        for message_id in source_ids:
            if message_id in noise_ids:
                noise_type = noise_types.get(message_id, "unknown")
                cited_noise[noise_type] = cited_noise.get(noise_type, 0) + 1
    total = len(advisories)
    return {
        "advisories": total,
        "matched": matched_advisories,
        "gold": len(room.gold_memories),
        "golds_with_matches": len(gold_with_match),
        "noise_types": {
            name: {"cited_as_source": cited_noise[name]} for name in sorted(cited_noise)
        },
        "rates": {
            "gold_match_rate": len(gold_with_match) / len(room.gold_memories),
            "noise_rate": ((total - matched_advisories) / total) if total else None,
        },
    }


def _pool_heuristic(per_room: Sequence[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "advisories": 0,
        "matched": 0,
        "gold": 0,
        "golds_with_matches": 0,
    }
    noise_types: dict[str, dict[str, int]] = {}
    for payload in per_room:
        for key in totals:
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
        for name, stats in (payload.get("noise_types") or {}).items():
            if not isinstance(stats, dict):
                continue
            merged = noise_types.setdefault(name, {"cited_as_source": 0})
            value = stats.get("cited_as_source")
            if isinstance(value, int) and not isinstance(value, bool):
                merged["cited_as_source"] += value
    return {
        **totals,
        "noise_types": {name: noise_types[name] for name in sorted(noise_types)},
        "rates": {
            "gold_match_rate": (
                totals["golds_with_matches"] / totals["gold"] if totals["gold"] else None
            ),
            "noise_rate": (
                ((totals["advisories"] - totals["matched"]) / totals["advisories"])
                if totals["advisories"]
                else None
            ),
        },
    }


@dataclass
class _RoomArmResult:
    results: list[dict[str, Any]]
    write_side: dict[str, Any]


def _run_room_arm(
    *,
    arm: str,
    room: Room,
    repeat: int,
    answerer: RoomMemAnswerer,
    judge: RoomMemJudge,
    scratch_dir: Path,
    embedding: str,
    heuristic_advisories: bool,
    curated_source: CuratedMemorySource | None,
) -> _RoomArmResult:
    kernel_external = heuristic_advisories and arm == "raw"
    service = MemoryOSService(
        settings=_room_settings(
            scratch_dir / arm / f"{room.room_id}-r{repeat}",
            embedding=embedding,
            kernel_external=kernel_external,
        )
    )
    session = service.create_session(f"roommem {room.room_id} ({arm})")
    message_id_map = _ingest_room(service, room, session.id)

    views: list[CuratedMemoryView] = []
    curator_counts: dict[str, int] = {}
    if arm == "oracle":
        views = oracle_curated_memories(room)
        curator_counts = {"grounding_rejects": 0, "schema_failures": 0}
    elif arm == "curated":
        if curated_source is None:
            raise RoomMemConfigError("curated arm requires a registered curated memory source")
        views = list(curated_source.curate(service, session.id))
        _validate_curated_views(views, room=room)
        curator_counts = _curator_counts(curated_source)

    new_session_id: str | None = None
    if room.has_new_room_probes():
        new_session_id = service.create_session(
            f"roommem {room.room_id} (new room, same project)"
        ).id

    cross_scope_docs: dict[str, str] = {}
    for view in views:
        if view.status != "active":
            continue
        scope = _scope_for_kind(view.kind)
        document_id = f"{XMUSE_MEMORY_DOC_PREFIX}{view.id}"
        _ingest_and_attach(
            service,
            session.id,
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
            ref = ArchiveSourceRefPayload(source_type="document", source_id=document_id)
            service.attach_archive(
                ArchiveAttachmentRequest(
                    archive_id=document_id,
                    scope_type="session",
                    scope_id=new_session_id,
                    source_refs=[ref],
                )
            )

    matched_by_gold: dict[str, CuratedMemoryView] = {}
    write_side: dict[str, Any] = {}
    if arm in {"oracle", "curated"}:
        write_side, matched_by_gold = score_write_side(room, views, judge)
        if curator_counts:
            write_side["curator_counts"] = curator_counts
    advisories: dict[str, Mapping[str, Any]] = {}

    results: list[dict[str, Any]] = []
    for probe in room.probes:
        target_session = new_session_id
        if probe.asked_in != "new_room_same_project" or target_session is None:
            target_session = session.id
        package = service.build_context(
            session_id=target_session,
            task=XMUSE_TASK,
            budget=XMUSE_EVIDENCE_BUDGET,
            retrieval_query=probe.question,
            include_global_core=False,
        )
        envelope = build_source_evidence(package, schema_version="v2")
        evidence = _evidence_items(envelope)
        if kernel_external:
            for advisory in service.list_external_advisories(target_session):
                advisory_id = str(advisory.get("advisory_id", ""))
                advisories.setdefault(advisory_id, advisory)

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

        message_presence, memory_presence = _evidence_presence(evidence, message_id_map)
        answer_source_messages = {
            source.message_id for memory in answer_golds for source in memory.sources
        }
        source_hit = bool(answer_source_messages & message_presence)
        answer_view_ids = {
            matched_view.id
            for memory in answer_golds
            if (matched_view := matched_by_gold.get(memory.id)) is not None
        }
        if arm == "raw":
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
            if arm != "raw":
                successor_view = matched_by_gold.get(successor.id)
                if successor_view is not None and successor_view.id in memory_presence:
                    successor_present = True
            if not successor_present:
                stale = True
        citations, citation_correct = _citation_correctness(
            answer,
            evidence,
            arm=arm,
            message_id_map=message_id_map,
            answer_source_messages=answer_source_messages,
            answer_view_ids=answer_view_ids,
        )
        evidence_tokens = envelope.get("estimated_tokens")
        results.append(
            {
                "arm": arm,
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
                        "text": item.text[:EVIDENCE_TEXT_LIMIT],
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
        )

    if kernel_external:
        write_side = _score_heuristic_advisories(
            room,
            list(advisories.values()),
            message_id_map,
        )
    return _RoomArmResult(results=results, write_side=write_side)


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
            for key, field in (
                ("hit_at_8", "hit"),
                ("source_hit_at_8", "source_hit"),
                ("stale_at_8", "stale"),
                ("substring_pass", "substring"),
            ):
                rate = _rate(rows, field)
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
) -> dict[str, Any]:
    return {
        "run": dict(run_meta),
        "read_side": aggregate_read_side(results),
        "write_side": write_side,
        "limitations": [LIMITATIONS_EN, LIMITATIONS_ZH],
    }


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
        "llm={llm}; heuristic_advisories={heuristic}.".format(
            arms=",".join(run.get("arms", [])),
            rooms=",".join(run.get("rooms", [])),
            repeats=run.get("repeats"),
            embedding=run.get("embedding"),
            llm=run.get("llm"),
            heuristic=str(bool(run.get("heuristic_advisories"))).lower(),
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
        "| arm | memories | matched gold | precision | recall | noise rate | "
        "supersede rate | duplicate rate | unmatched legit/noise |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    write_side = summary.get("write_side") or {}
    for arm in sorted(write_side):
        payload = write_side[arm]
        if arm == "raw":
            heuristic = payload.get("heuristic") or {}
            rates = heuristic.get("rates") or {}
            lines.append(
                "| raw (heuristic advisories) | {advisories} | {matched} | "
                "gold match rate: {gold_rate} | noise rate: {noise_rate} | - | - | - | - |".format(
                    advisories=heuristic.get("advisories", 0),
                    matched=heuristic.get("matched", 0),
                    gold_rate=_format_number(rates.get("gold_match_rate")),
                    noise_rate=_format_number(rates.get("noise_rate")),
                )
            )
            continue
        rates = payload.get("rates") or {}
        judged = payload.get("unmatched_judged") or {}
        lines.append(
            "| {arm} | {memories} | {matched}/{gold} | {precision} | {recall} | "
            "{noise} | {supersede} | {duplicate} | {legit}/{noise_n} |".format(
                arm=arm,
                memories=payload.get("memories", 0),
                matched=payload.get("matched", 0),
                gold=payload.get("gold", 0),
                precision=_format_number(rates.get("precision")),
                recall=_format_number(rates.get("recall")),
                noise=_format_number(rates.get("noise_rate")),
                supersede=_format_number(rates.get("supersede_rate")),
                duplicate=_format_number(rates.get("duplicate_rate")),
                legit=judged.get("legit_unannotated", 0),
                noise_n=judged.get("noise", 0),
            )
        )
    lines.append("")
    if "curated" in write_side and write_side["curated"].get("notes"):
        for note in write_side["curated"]["notes"]:
            lines.append(f"- {note}")
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
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as handle:
        for row in results:
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
    heuristic_advisories: bool = False,
    curated_source_name: str = "default",
    llm_factory: LLMFactory | None = None,
    fake_llm: bool = False,
    llm_label: str | None = None,
    settings: Settings | None = None,
    scratch_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run the RoomMem harness and write results/summary reports.

    Returns the summary payload that was written to ``summary.json``.
    """

    if not rooms:
        raise RoomMemDataError("RoomMem run needs at least one room")
    selected_arms = list(arms)
    if not selected_arms:
        raise RoomMemConfigError("at least one arm is required")
    for arm in selected_arms:
        if arm not in ARM_VALUES:
            raise RoomMemConfigError(f"unknown arm {arm!r}; valid arms: {', '.join(ARM_VALUES)}")
    if repeats < 1:
        raise RoomMemConfigError("repeats must be at least 1")
    if embedding not in EMBEDDING_VALUES:
        raise RoomMemConfigError(
            f"unknown embedding mode {embedding!r}; valid: {', '.join(EMBEDDING_VALUES)}"
        )
    if embedding == "fastembed":
        _require_fastembed()

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    curated_source = (
        build_curated_source(curated_source_name) if "curated" in selected_arms else None
    )
    factory = llm_factory or build_llm_factory(
        out_dir=out_path, fake_llm=fake_llm, settings=settings
    )

    created_scratch = scratch_root is None
    scratch_dir = (
        Path(scratch_root)
        if scratch_root is not None
        else Path(tempfile.mkdtemp(prefix="roommem-"))
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    write_side_per_room: dict[str, list[dict[str, Any]]] = {arm: [] for arm in selected_arms}
    try:
        for arm in selected_arms:
            for repeat in range(repeats):
                answerer, judge = factory(repeat)
                for room in rooms:
                    room_result = _run_room_arm(
                        arm=arm,
                        room=room,
                        repeat=repeat,
                        answerer=answerer,
                        judge=judge,
                        scratch_dir=scratch_dir,
                        embedding=embedding,
                        heuristic_advisories=heuristic_advisories,
                        curated_source=curated_source,
                    )
                    results.extend(room_result.results)
                    if room_result.write_side:
                        write_side_per_room[arm].append(room_result.write_side)
    finally:
        if created_scratch:
            shutil.rmtree(scratch_dir, ignore_errors=True)

    write_side: dict[str, Any] = {}
    for arm in selected_arms:
        payloads = write_side_per_room[arm]
        if arm == "raw":
            heuristic = _pool_heuristic(
                [payload for payload in payloads if payload.get("advisories") is not None]
            )
            write_side[arm] = {
                "heuristic": heuristic,
                "note": (
                    "Heuristic baseline: MEMORYOS_AGENT_KERNEL=external advisories collected "
                    "after each probe's build-context; only present with "
                    "--heuristic-advisories."
                ),
            }
        elif payloads:
            pooled = pool_write_side(payloads)
            if arm == "curated":
                pooled["notes"] = [
                    "Cross-scope delivery (rule -> project, preference -> user) is simulated "
                    "as operator-approved and attached to the room session and the "
                    "new-room probe session.",
                    "Unmatched curated memories are not counted as noise directly; the judge "
                    "splits them into legit_unannotated vs noise.",
                ]
            write_side[arm] = pooled

    run_meta: dict[str, Any] = {
        "arms": selected_arms,
        "rooms": [room.room_id for room in rooms],
        "repeats": repeats,
        "embedding": embedding,
        "heuristic_advisories": heuristic_advisories,
        "llm": llm_label or ("fake" if fake_llm else "custom"),
        "curated_source": curated_source_name if "curated" in selected_arms else None,
    }
    summary = build_summary(results=results, write_side=write_side, run_meta=run_meta)
    write_reports(out_path, results=results, write_side=write_side, summary=summary)
    return summary


__all__ = [
    "ARM_VALUES",
    "ANSWERER_SYSTEM_PROMPT",
    "ChatAnswerer",
    "ChatJudge",
    "CuratedMemorySource",
    "CuratedMemoryView",
    "DeepSeekChatClient",
    "DiskCachedChatClient",
    "EvidenceItem",
    "FakeAnswerer",
    "FakeJudge",
    "GoldMemory",
    "GoldMemorySource",
    "LIMITATIONS_EN",
    "LIMITATIONS_ZH",
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
    "run_roommem",
    "score_write_side",
    "unregister_curated_source",
    "write_reports",
]
