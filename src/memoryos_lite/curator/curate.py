"""Stateless module curation: ``POST /curate`` (``memoryos_curate/v1``).

The caller (for example xmuse) owns all state. Each request carries the
module's active memories, a window of new activities, and a little read-only
context; MemoryOS returns new memory versions to store. Nothing is persisted
here, so a retried request is safe.

The lesson log uses closed-world accounting: every ``review_objection`` and
``gate_failure`` in the window must be either assigned to a lesson (with a
verbatim quote) or dismissed with a reason. A lesson's ``occurrences`` is the
number of failures assigned to it, so repeats are counted by construction and
a missed failure is reported in ``unaccounted`` instead of disappearing.

Two profiles share the loop. ``module`` (the default) is the lesson log above,
with decisions and facts. ``room`` is the session curator behind MemoryOS
sessions (for example an xmuse Room): its activities are plain messages, so it
records facts, decisions, rules, preferences and lessons as proposed memories;
a lesson proposal that cites a new activity adds one occurrence to the active
lesson on its topic_key.

This module is pure: validation (:func:`check_reply`) and consolidation
(:func:`consolidate`) need no LLM. The LLM loop lives in
:mod:`memoryos_lite.curator.graph`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memoryos_lite.curator.grounding import normalize_text, repair_quote

MAX_STATEMENT_CHARS = 600
MAX_TOPIC_KEY_CHARS = 255
MAX_SOURCES = 3
# A lesson accumulates the sources of its repeat occurrences, newest kept.
MAX_LESSON_SOURCES = 8
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


CURATE_SCHEMA = "memoryos_curate/v1"
FAILURE_TYPES: tuple[str, ...] = ("review_objection", "gate_failure")
MAX_WINDOW_ACTIVITIES = 32
MAX_CONTEXT_ACTIVITIES = 8
MAX_ACTIVE_MEMORIES = 60
MAX_REPAIRS = 2
MAX_DISMISS_CHARS = 200

ActivityType = Literal["message", "review_objection", "gate_failure", "contract_revision"]
ACTIVITY_TYPES: tuple[str, ...] = (
    "message",
    "review_objection",
    "gate_failure",
    "contract_revision",
)
#: The xmuse message kind of a ``message`` activity (collab profile).
ActivityKind = Literal["message", "handoff", "review_request", "decision", "assumption", "question"]
MemoryKind = Literal[
    "lesson", "decision", "fact", "rule", "preference", "convention", "assumption", "question"
]
Profile = Literal["module", "room", "collab"]
#: Kinds a profile accepts in "memories" (module lessons come only from assignments).
PROFILE_MEMORY_KINDS: dict[str, tuple[str, ...]] = {
    "module": ("decision", "fact"),
    "room": ("fact", "decision", "rule", "preference", "lesson"),
    "collab": ("decision", "convention", "assumption", "question", "lesson"),
}
MAX_CONFLICT_REASON_CHARS = 200


def _unset(value: object) -> bool:
    """Collab-only response fields are omitted when unset: module and room output is unchanged."""
    return value is None


class CurateActivity(BaseModel):
    """One module activity, identified by the caller's own id and order."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=0)
    type: ActivityType
    kind: ActivityKind | None = None
    speaker: str = Field(default="", max_length=128)
    text: str = Field(min_length=1, max_length=200_000)


class CurateSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=128)
    quote: str = Field(min_length=1)


class CurateMemory(BaseModel):
    """An active memory as the caller stores it (and as MemoryOS returns it)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    kind: MemoryKind
    topic_key: str = Field(min_length=1, max_length=255)
    statement: str = Field(min_length=1)
    version: int = Field(ge=0)
    occurrences: int = Field(default=1, ge=1)
    sources: list[CurateSource] = Field(default_factory=list)


class CurateMemoryVersion(CurateMemory):
    """A new memory version; ``supersedes_id`` names the active memory it replaces.

    ``resolves_ids`` (collab only) names the active questions this version answers.
    """

    supersedes_id: str | None = None
    resolves_ids: list[str] | None = Field(default=None, exclude_if=_unset)


class CurateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(min_length=1, max_length=255)
    profile: Profile = "module"
    active: list[CurateMemory] = Field(default_factory=list, max_length=MAX_ACTIVE_MEMORIES)
    context: list[CurateActivity] = Field(default_factory=list, max_length=MAX_CONTEXT_ACTIVITIES)
    window: list[CurateActivity] = Field(min_length=1, max_length=MAX_WINDOW_ACTIVITIES)
    max_repairs: int = Field(default=MAX_REPAIRS, ge=0, le=MAX_REPAIRS)

    @model_validator(mode="after")
    def _unique_activity_ids(self) -> CurateRequest:
        ids = [activity.id for activity in [*self.context, *self.window]]
        if len(ids) != len(set(ids)):
            raise ValueError("activity ids must be unique across context and window")
        return self

    @property
    def failures(self) -> list[CurateActivity]:
        return [activity for activity in self.window if activity.type in FAILURE_TYPES]


class CurateAssignment(BaseModel):
    """Where one failure went: a lesson (with its quote) or a dismissal reason."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str
    lesson: str | None = None
    quote: str | None = None
    dismiss: str | None = None


class CurateConflict(BaseModel):
    """Two entries that seem to contradict (collab); reported, never resolved."""

    a_id: str
    b_id: str
    reason: str
    sources: list[CurateSource] = Field(default_factory=list)


class CurateAttempt(BaseModel):
    """One provider attempt (collab); a timeout or error reports no tokens."""

    outcome: Literal["ok", "timeout", "error"]
    secs: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class CurateUsage(BaseModel):
    """Token usage summed over every attempt (collab).

    ``unmetered_attempts`` counts attempts the provider reported no usage for
    (timeouts and errors); with any of them the sums are a lower bound.
    """

    attempts: int = 0
    unmetered_attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def total(cls, attempts: Sequence[CurateAttempt]) -> CurateUsage:
        usage = cls(attempts=len(attempts))
        for attempt in attempts:
            if attempt.total_tokens is None and attempt.prompt_tokens is None:
                usage.unmetered_attempts += 1
            usage.prompt_tokens += attempt.prompt_tokens or 0
            usage.completion_tokens += attempt.completion_tokens or 0
            usage.total_tokens += attempt.total_tokens or 0
        return usage


class CurateDiagnostics(BaseModel):
    llm_calls: int = 0
    repairs: int = 0
    initial_violations: list[str] = Field(default_factory=list)
    final_violations: list[str] = Field(default_factory=list)
    rejected_memories: int = 0
    noop_memories: int = 0
    stale_memories: int = 0
    attempts: list[CurateAttempt] | None = Field(default=None, exclude_if=_unset)
    usage: CurateUsage | None = Field(default=None, exclude_if=_unset)


class CurateResponse(BaseModel):
    schema_version: str = CURATE_SCHEMA
    scope_id: str
    memories: list[CurateMemoryVersion] = Field(default_factory=list)
    assignments: list[CurateAssignment] = Field(default_factory=list)
    unaccounted: list[str] = Field(default_factory=list)
    conflicts: list[CurateConflict] | None = Field(default=None, exclude_if=_unset)
    diagnostics: CurateDiagnostics = Field(default_factory=CurateDiagnostics)


# ---------------------------------------------------------------------------
# Validation of one LLM reply
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MemoryProposal:
    kind: str
    topic_key: str
    statement: str
    sources: list[CurateSource]
    version: int
    resolves: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ConflictProposal:
    """``a``/``b`` are ``("active", id)`` or ``("new", topic_key)``."""

    a: tuple[str, str]
    b: tuple[str, str]
    reason: str
    sources: list[CurateSource]


@dataclass
class CheckResult:
    """Everything usable in a reply, plus the rule violations to send back."""

    violations: list[str] = field(default_factory=list)
    assignments: list[CurateAssignment] = field(default_factory=list)
    lessons: dict[str, str] = field(default_factory=dict)
    memories: list[_MemoryProposal] = field(default_factory=list)
    conflicts: list[_ConflictProposal] = field(default_factory=list)
    rejected_memories: int = 0
    unaccounted: list[str] = field(default_factory=list)


def _active_lesson_keys(request: CurateRequest) -> set[str]:
    return {memory.topic_key for memory in request.active if memory.kind == "lesson"}


def _statement(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text if text and len(text) <= MAX_STATEMENT_CHARS else None


def _parse_lessons(raw: object, result: CheckResult) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        result.violations.append('"lessons" must be a list')
        return
    for item in raw:
        if not isinstance(item, dict):
            result.violations.append('every entry of "lessons" must be an object')
            continue
        key = (
            normalize_topic_key(item.get("topic_key", ""))
            if isinstance(item.get("topic_key"), str)
            else None
        )
        statement = _statement(item.get("statement"))
        if key is None or statement is None:
            result.violations.append(
                f"lesson {item.get('topic_key')!r} needs a topic_key and a statement of "
                f"1-{MAX_STATEMENT_CHARS} characters"
            )
            continue
        result.lessons.setdefault(key, statement)


def _parse_assignments(raw: object, request: CurateRequest, result: CheckResult) -> None:
    failures = {activity.id: activity for activity in request.failures}
    other_ids = {activity.id for activity in [*request.context, *request.window]} - set(failures)
    lesson_keys = _active_lesson_keys(request) | set(result.lessons)
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        result.violations.append('"assignments" must be a list')
        raw = []
    assigned: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("activity_id"), str):
            result.violations.append('every assignment needs an "activity_id"')
            continue
        activity_id = item["activity_id"]
        if activity_id not in failures:
            if activity_id in other_ids:
                result.violations.append(
                    f"{activity_id} is not a review_objection or gate_failure to curate; "
                    "only those get assignments"
                )
            else:
                result.violations.append(f"{activity_id} is not an activity id in this request")
            continue
        if activity_id in assigned:
            result.violations.append(f"{activity_id} has more than one assignment")
            continue
        lesson_raw, dismiss_raw = item.get("lesson"), item.get("dismiss")
        if (lesson_raw is None) == (dismiss_raw is None):
            result.violations.append(f'{activity_id} needs exactly one of "lesson" or "dismiss"')
            continue
        if dismiss_raw is not None:
            reason = dismiss_raw.strip() if isinstance(dismiss_raw, str) else ""
            if not reason or len(reason) > MAX_DISMISS_CHARS:
                result.violations.append(
                    f"{activity_id}: a dismissal needs a reason of 1-{MAX_DISMISS_CHARS} characters"
                )
                continue
            assigned.add(activity_id)
            result.assignments.append(CurateAssignment(activity_id=activity_id, dismiss=reason))
            continue
        key = normalize_topic_key(lesson_raw) if isinstance(lesson_raw, str) else None
        if key is None or key not in lesson_keys:
            result.violations.append(
                f"{activity_id} is assigned to lesson {lesson_raw!r}, which is neither an "
                'active lesson nor defined in "lessons"'
            )
            continue
        quote = item.get("quote")
        grounded = (
            repair_quote(failures[activity_id].text, quote) if isinstance(quote, str) else None
        )
        if grounded is None:
            result.violations.append(
                f"the quote for {activity_id} must be an exact substring of {activity_id} "
                "(at least 8 characters)"
            )
            continue
        assigned.add(activity_id)
        result.assignments.append(
            CurateAssignment(activity_id=activity_id, lesson=key, quote=grounded)
        )
    for activity_id, activity in failures.items():
        if activity_id not in assigned:
            result.unaccounted.append(activity_id)
            result.violations.append(f"{activity_id} ({activity.type}) has no assignment")


def _drop_lessons_without_failures(request: CurateRequest, result: CheckResult) -> None:
    assigned_keys = {a.lesson for a in result.assignments if a.lesson is not None}
    for key in list(result.lessons):
        if key not in assigned_keys:
            del result.lessons[key]
            result.violations.append(
                f"lesson {key} has no failure assigned to it in this reply; a lesson is "
                "created or reworded only together with a failure assignment"
            )


def _parse_memories(raw: object, request: CurateRequest, result: CheckResult) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        result.violations.append('"memories" must be a list')
        return
    activities = {activity.id: activity for activity in [*request.context, *request.window]}
    kinds = PROFILE_MEMORY_KINDS[request.profile]
    questions = {memory.id for memory in request.active if memory.kind == "question"}
    for item in raw:
        if not isinstance(item, dict):
            result.violations.append('every entry of "memories" must be an object')
            result.rejected_memories += 1
            continue
        kind = item.get("kind")
        label = item.get("topic_key")
        if kind == "lesson" and kind not in kinds:
            result.violations.append(
                f"memory {label!r}: lessons are recorded through assignments, not memories"
            )
            result.rejected_memories += 1
            continue
        key = normalize_topic_key(label) if isinstance(label, str) else None
        statement = _statement(item.get("statement"))
        sources_raw = item.get("sources")
        if (
            kind not in kinds
            or key is None
            or statement is None
            or not isinstance(sources_raw, list)
            or not 1 <= len(sources_raw) <= MAX_SOURCES
        ):
            result.violations.append(
                f"memory {label!r} needs kind {'|'.join(kinds)}, a topic_key, a statement and "
                f"1-{MAX_SOURCES} sources"
            )
            result.rejected_memories += 1
            continue
        sources, bad_source = _ground_sources(sources_raw, activities)
        if bad_source is not None:
            result.violations.append(
                f"memory {key}: the quote from {bad_source} must be an exact substring of an "
                "activity in this request"
            )
            result.rejected_memories += 1
            continue
        resolves = item.get("resolves") if request.profile == "collab" else None
        if resolves is not None and (
            not isinstance(resolves, list)
            or not all(isinstance(r, str) and r in questions for r in resolves)
        ):
            result.violations.append(
                f'memory {key}: "resolves" must list ids of active questions only'
            )
            result.rejected_memories += 1
            continue
        version = max(activities[s.activity_id].seq for s in sources)
        result.memories.append(
            _MemoryProposal(
                kind=str(kind),
                topic_key=key,
                statement=statement,
                sources=sources,
                version=version,
                resolves=tuple(dict.fromkeys(resolves or [])),
            )
        )


def _ground_sources(
    raw: list[Any], activities: dict[str, CurateActivity]
) -> tuple[list[CurateSource], str | None]:
    """Verbatim-checked sources, or the id of the first source that fails the check."""

    sources: list[CurateSource] = []
    for source in raw:
        activity_id = source.get("activity_id") if isinstance(source, dict) else None
        quote = source.get("quote") if isinstance(source, dict) else None
        activity = activities.get(activity_id) if isinstance(activity_id, str) else None
        grounded = (
            repair_quote(activity.text, quote)
            if activity is not None and isinstance(quote, str)
            else None
        )
        if activity is None or grounded is None:
            return sources, str(activity_id)
        if all(s.activity_id != activity.id or s.quote != grounded for s in sources):
            sources.append(CurateSource(activity_id=activity.id, quote=grounded))
    return sources, None


def _parse_conflicts(raw: object, request: CurateRequest, result: CheckResult) -> None:
    """Collab: suspected contradictions between active entries or with a new proposal."""

    if raw is None:
        return
    if not isinstance(raw, list):
        result.violations.append('"conflicts" must be a list')
        return
    active_ids = {memory.id for memory in request.active}
    proposed = {memory.topic_key for memory in result.memories}
    activities = {activity.id: activity for activity in [*request.context, *request.window]}
    seen: set[frozenset[tuple[str, str]]] = set()
    for item in raw:
        refs: list[tuple[str, str]] = []
        for side in ("a_id", "b_id"):
            value = item.get(side) if isinstance(item, dict) else None
            if not isinstance(value, str):
                continue
            key = normalize_topic_key(value)
            if value in active_ids:
                refs.append(("active", value))
            elif key is not None and key in proposed:
                refs.append(("new", key))
        reason = item.get("reason") if isinstance(item, dict) else None
        reason = reason.strip() if isinstance(reason, str) else ""
        sources_raw = item.get("sources", []) if isinstance(item, dict) else None
        if (
            len(refs) != 2
            or refs[0] == refs[1]
            or refs[0][0] == refs[1][0] == "new"
            or not 1 <= len(reason) <= MAX_CONFLICT_REASON_CHARS
            or not isinstance(sources_raw, list)
            or len(sources_raw) > MAX_SOURCES
        ):
            result.violations.append(
                "every conflict needs a_id and b_id (active ids, or the topic_key of one "
                f"memory proposed in this reply), a reason of 1-{MAX_CONFLICT_REASON_CHARS} "
                f"characters and 0-{MAX_SOURCES} sources"
            )
            continue
        sources, bad_source = _ground_sources(sources_raw, activities)
        if bad_source is not None:
            result.violations.append(
                f"conflict {refs[0][1]}/{refs[1][1]}: the quote from {bad_source} must be an "
                "exact substring of an activity in this request"
            )
            continue
        if frozenset(refs) not in seen:
            seen.add(frozenset(refs))
            result.conflicts.append(_ConflictProposal(refs[0], refs[1], reason, sources))


def check_reply(
    request: CurateRequest,
    reply: dict[str, Any] | None,
    error: str | None = None,
) -> CheckResult:
    """Validate one LLM reply against the request; never raises."""

    result = CheckResult()
    if reply is None:
        result.violations.append(error or "the reply was not a JSON object")
        for activity in request.failures:
            result.unaccounted.append(activity.id)
        return result
    _parse_lessons(reply.get("lessons"), result)
    _parse_assignments(reply.get("assignments"), request, result)
    _drop_lessons_without_failures(request, result)
    _parse_memories(reply.get("memories"), request, result)
    if request.profile == "collab":
        _parse_conflicts(reply.get("conflicts"), request, result)
    return result


# ---------------------------------------------------------------------------
# Deterministic consolidation
# ---------------------------------------------------------------------------


def memory_id(scope_id: str, memory: CurateMemory, resolves: Sequence[str] = ()) -> str:
    """Deterministic id of one memory version (same content, same id)."""

    fields: list[Any] = [
        scope_id,
        memory.kind,
        memory.topic_key,
        memory.version,
        memory.occurrences,
        memory.statement,
        [[s.activity_id, s.quote] for s in memory.sources],
    ]
    if resolves:
        fields.append(list(resolves))
    canonical = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
    return "mem_" + sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _newest(memories: list[CurateMemory]) -> CurateMemory | None:
    return max(memories, key=lambda m: (m.version, m.id), default=None)


def _versioned(
    request: CurateRequest,
    prior: CurateMemory | None,
    resolves: Sequence[str] = (),
    **fields: Any,
) -> CurateMemoryVersion:
    draft = CurateMemory(id="pending", **fields)
    return CurateMemoryVersion(
        **{**draft.model_dump(), "id": memory_id(request.scope_id, draft, resolves)},
        supersedes_id=prior.id if prior is not None else None,
        resolves_ids=list(resolves) if request.profile == "collab" else None,
    )


def _conflicts(
    request: CurateRequest, check: CheckResult, out: list[CurateMemoryVersion]
) -> list[CurateConflict]:
    """Map conflict refs to ids; a new proposal that became a noop maps to its active entry."""

    new_ids = {m.topic_key: m.id for m in sorted(request.active, key=lambda m: (m.version, m.id))}
    new_ids.update((memory.topic_key, memory.id) for memory in out)
    conflicts: list[CurateConflict] = []
    seen: set[frozenset[str]] = set()
    for proposal in check.conflicts:
        ids = [
            ref if kind == "active" else new_ids.get(ref) for kind, ref in (proposal.a, proposal.b)
        ]
        a_id, b_id = ids
        if a_id is None or b_id is None or a_id == b_id or frozenset(ids) in seen:
            continue
        seen.add(frozenset((a_id, b_id)))
        conflicts.append(
            CurateConflict(a_id=a_id, b_id=b_id, reason=proposal.reason, sources=proposal.sources)
        )
    return conflicts


def consolidate(request: CurateRequest, check: CheckResult) -> CurateResponse:
    """Turn a checked reply into new memory versions, without any LLM judgement.

    Lessons: per topic_key, every newly assigned failure adds one occurrence and
    its quote; the version is the newest failure's ``seq``. A failure that the
    active lesson already cites is not counted again (safe replays).
    Decisions and facts: per topic_key the newest proposal wins; a restatement
    of the active memory is a noop and a proposal older than it is stale.
    """

    active_lessons: dict[str, list[CurateMemory]] = {}
    active_other: dict[str, list[CurateMemory]] = {}
    for memory in request.active:
        bucket = active_lessons if memory.kind == "lesson" else active_other
        bucket.setdefault(memory.topic_key, []).append(memory)
    seq = {activity.id: activity.seq for activity in [*request.context, *request.window]}
    diagnostics = CurateDiagnostics(rejected_memories=check.rejected_memories)
    out: list[CurateMemoryVersion] = []

    # Lesson occurrences: an assigned failure, or (room profile) a lesson proposal.
    occurrences_by_key: dict[str, list[tuple[list[CurateSource], int, bool]]] = {}
    statements = dict(check.lessons)
    for assignment in check.assignments:
        if assignment.lesson is not None:
            source = CurateSource(activity_id=assignment.activity_id, quote=assignment.quote or "")
            occurrences_by_key.setdefault(assignment.lesson, []).append(
                ([source], seq[assignment.activity_id], False)
            )
    for proposal in check.memories:
        if proposal.kind == "lesson":
            occurrences_by_key.setdefault(proposal.topic_key, []).append(
                (proposal.sources, proposal.version, True)
            )
            statements[proposal.topic_key] = proposal.statement
    for key, occurrences in occurrences_by_key.items():
        prior = _newest(active_lessons.get(key, []))
        cited = {s.activity_id for s in prior.sources} if prior is not None else set()
        sources = list(prior.sources) if prior is not None else []
        version = prior.version if prior is not None else 0
        added = 0
        for occurrence_sources, occurrence_version, proposed in occurrences:
            fresh = [s for s in occurrence_sources if s.activity_id not in cited]
            if not fresh:
                diagnostics.noop_memories += proposed
                continue
            cited.update(s.activity_id for s in fresh)
            sources.extend(fresh)
            version = max(version, occurrence_version)
            added += 1
        statement = statements.get(key) or (prior.statement if prior is not None else None)
        if not added or statement is None:
            continue
        out.append(
            _versioned(
                request,
                prior,
                kind="lesson",
                topic_key=key,
                statement=statement,
                version=version,
                occurrences=(prior.occurrences if prior is not None else 0) + added,
                sources=sources[-MAX_LESSON_SOURCES:],
            )
        )

    winners: dict[str, _MemoryProposal] = {}
    for proposal in check.memories:
        if proposal.kind == "lesson":
            continue
        current = winners.get(proposal.topic_key)
        if current is not None:
            diagnostics.noop_memories += 1
        if current is None or proposal.version >= current.version:
            winners[proposal.topic_key] = proposal
    # Collab: active entries include ones agents declared themselves, under any key.
    declared = (
        {normalize_text(memory.statement) for memory in request.active}
        if request.profile == "collab"
        else set()
    )
    for key, proposal in winners.items():
        prior = _newest(active_other.get(key, []))
        if (
            prior is not None
            and normalize_text(prior.statement) == normalize_text(proposal.statement)
        ) or normalize_text(proposal.statement) in declared:
            diagnostics.noop_memories += 1
            continue
        if prior is not None and proposal.version < prior.version:
            diagnostics.stale_memories += 1
            continue
        out.append(
            _versioned(
                request,
                prior,
                proposal.resolves,
                kind=proposal.kind,
                topic_key=key,
                statement=proposal.statement,
                version=proposal.version,
                occurrences=1,
                sources=proposal.sources,
            )
        )

    return CurateResponse(
        scope_id=request.scope_id,
        memories=out,
        assignments=check.assignments,
        unaccounted=check.unaccounted,
        conflicts=_conflicts(request, check, out) if request.profile == "collab" else None,
        diagnostics=diagnostics,
    )


__all__ = [
    "CURATE_SCHEMA",
    "FAILURE_TYPES",
    "CheckResult",
    "CurateActivity",
    "CurateAssignment",
    "CurateConflict",
    "CurateDiagnostics",
    "CurateMemory",
    "CurateMemoryVersion",
    "CurateRequest",
    "CurateResponse",
    "CurateSource",
    "check_reply",
    "consolidate",
    "memory_id",
]
