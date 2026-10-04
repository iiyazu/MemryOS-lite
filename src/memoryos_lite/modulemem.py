"""ModuleMem: does curated module memory bring a restarted module owner back up to speed?

Each ``benchmarks/modulemem/modules/mmNN.json`` is one module's activity stream
(owner messages, review objections, failing gate logs, contract revisions) with
gold contracts, decisions and lessons. For every arm the owner "restarts" and
answers the module's probes from that arm's context:

``pack``
    The real path. The harness plays the host (xmuse): it holds the module's
    memories and sends each window of activities to the stateless curate graph
    (``POST /curate``), flushing on every gate failure or review objection and
    otherwise every ``curator_window`` activities. The owner then gets the
    rendered module memory file: current contracts (expanded, as the owner can
    open ``.xmuse/contracts/``), lessons by occurrences, then decisions and
    facts, within ``pack_budget`` tokens.
``oracle_pack``
    The same file rendered from the gold decisions and lessons (upper bound).
``recent``
    Only the last ``RECENT_ACTIVITIES`` activities (what a compacted session keeps).
``raw_log``
    The newest raw activities that fit in ``pack_budget`` tokens: the
    "just put the module log in the file" baseline with the pack's budget.
``retrieval``
    xmuse-style recall: build-context top-8 over the module's raw activity documents.
``full_history``
    Every activity of the module in the context window.
``none``
    No module memory at all (a fresh owner with only the task).

Scoring: the judge labels each answer (correct/stale/missing/wrong) against the
current gold; probes are grouped by what they ask about (contract, decision,
lesson). The ``pack`` arm also reports write-side matching against gold, lesson
occurrence accuracy, failure accounting against the gold lesson clusters
(pairwise precision/recall, dismissals, unaccounted), repair-loop use, and the
gate-failure-to-lesson latency of each curate call.

Behavior (``tasks``): a module may also carry owner tasks. The restarted owner
writes a code change for each task from the same arm context, and a task judge
labels every requirement of the task satisfied, violated or not_addressed.
Requirements reference a gold lesson (does the owner repeat a known mistake?),
a current decision, or a current contract; optional ``violation_patterns`` are
regexes checked deterministically against the code. By default the owner is an
LLM that replies with patch text; with a coder command it is a coding agent that
edits a copy of the module's seed repository with the arm's memory in
``AGENTS.md``, the judge grades its ``git diff``, and patterns are checked on the
added lines only.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.curator import CuratorLLM, build_curator_llm
from memoryos_lite.curator.curate import (
    FAILURE_TYPES,
    CurateActivity,
    CurateAssignment,
    CurateMemory,
    CurateRequest,
)
from memoryos_lite.curator.graph import run_curate
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.roommem import (
    XMUSE_ACTIVITY_DOC_PREFIX,
    XMUSE_MESSAGE_ID_PREFIX,
    XMUSE_TASK,
    ChatCompletionClient,
    CuratedMemoryView,
    DiskCachedChatClient,
    DiskCachedCuratorLLM,
    EvidenceItem,
    GoldMemory,
    GoldMemorySource,
    LLMUsageTracker,
    RemoteChatClient,
    RoomMemAnswerer,
    RoomMemConfigError,
    RoomMemJudge,
    _evidence_items,
    _extract_json_object,
    _normalize_match_text,
    _room_settings,
    build_llm_factory,
    match_curated_to_gold,
    settings_for_llm_spec,
)
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

MODULEMEM_ARMS: tuple[str, ...] = (
    "pack",
    "oracle_pack",
    "recent",
    "raw_log",
    "retrieval",
    "full_history",
    "none",
)
MODULEMEM_SPLITS: dict[str, tuple[str, ...]] = {
    "dev": ("mm01", "mm02", "mm03", "mm04"),
    "test": ("mm05", "mm06", "mm07", "mm08"),
}
RECENT_ACTIVITIES = 8
CONTEXT_ACTIVITIES = 4
FLUSH_ACTIVITY_TYPES = FAILURE_TYPES
JUDGE_LABELS = ("correct", "stale", "missing", "wrong")
TASK_LABELS = ("satisfied", "violated", "not_addressed")
REQUIREMENT_CATEGORIES = ("lesson", "decision", "contract")


class ModuleMemError(ValueError):
    """Invalid ModuleMem data or configuration."""


class ModuleParticipant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    kind: Literal["human", "agent", "infra"]
    name: str


class ModuleActivity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    type: Literal["message", "review_objection", "gate_failure", "contract_revision"]
    speaker: str
    text: str = Field(min_length=1)
    contract_id: str | None = None
    contract_version: int | None = None


class ModuleGoldSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    activity_id: str
    quote: str


class ModuleGoldMemory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    topic_key: str
    statement: str
    sources: list[ModuleGoldSource] = Field(min_length=1)
    superseded_by: str | None = None
    occurrences: int = 1


class ModuleGoldContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    contract_id: str
    version: int
    activity_id: str


class ModuleGold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    contracts: list[ModuleGoldContract] = Field(default_factory=list)
    decisions: list[ModuleGoldMemory] = Field(default_factory=list)
    lessons: list[ModuleGoldMemory] = Field(default_factory=list)


class ModuleProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    question: str
    answer_ids: list[str] = Field(min_length=1)
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)


class ModuleRequirement(BaseModel):
    """One thing a correct solution must do; ``ref`` is the gold it comes from."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    ref: str
    check: str = Field(min_length=1)
    violation_patterns: list[str] = Field(default_factory=list)


class ModuleTask(BaseModel):
    """A task for the restarted owner, written so that memory matters."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    prompt: str = Field(min_length=1)
    requirements: list[ModuleRequirement] = Field(min_length=1, max_length=6)


class Module(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    module_id: str
    project: str = ""
    language: str = "en"
    title: str = ""
    participants: list[ModuleParticipant]
    activities: list[ModuleActivity] = Field(min_length=1)
    gold: ModuleGold
    probes: list[ModuleProbe] = Field(min_length=1)
    tasks: list[ModuleTask] = Field(default_factory=list)

    def activity(self, activity_id: str) -> ModuleActivity | None:
        return next((a for a in self.activities if a.id == activity_id), None)

    def seq(self, activity_id: str) -> int:
        return next(i for i, a in enumerate(self.activities, start=1) if a.id == activity_id)

    def speaker_name(self, activity: ModuleActivity) -> str:
        return next(
            (p.name for p in self.participants if p.id == activity.speaker), activity.speaker
        )


def load_modules(data_dir: str | Path, module_ids: Sequence[str] | None = None) -> list[Module]:
    root = Path(data_dir)
    paths = sorted(root.glob("mm*.json"))
    if module_ids:
        wanted = set(module_ids)
        paths = [path for path in paths if path.stem in wanted]
        missing = wanted - {path.stem for path in paths}
        if missing:
            raise ModuleMemError(f"unknown modules: {', '.join(sorted(missing))}")
    if not paths:
        raise ModuleMemError(f"no ModuleMem files in {root}")
    modules: list[Module] = []
    for path in paths:
        try:
            module = Module.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError) as exc:
            raise ModuleMemError(f"{path}: {exc}") from exc
        _validate_module(module, source=path)
        modules.append(module)
    return modules


def _validate_module(module: Module, *, source: object) -> None:
    errors: list[str] = []
    for index, activity in enumerate(module.activities, start=1):
        if activity.id != f"a{index:02d}":
            errors.append(f"activity {activity.id} should be a{index:02d}")
        if activity.type == "contract_revision" and (
            not activity.contract_id or not activity.contract_version
        ):
            errors.append(f"{activity.id}: contract_revision needs contract_id and version")
    for memory in [*module.gold.decisions, *module.gold.lessons]:
        for src in memory.sources:
            cited = module.activity(src.activity_id)
            if cited is None or src.quote not in cited.text:
                errors.append(f"{memory.id}: quote not found in {src.activity_id}")
    for lesson in module.gold.lessons:
        for src in lesson.sources:
            cited = module.activity(src.activity_id)
            if cited is not None and cited.type not in FLUSH_ACTIVITY_TYPES:
                errors.append(f"{lesson.id}: lesson cites a {cited.type}")
    errors.extend(_task_errors(module))
    if errors:
        raise ModuleMemError(f"{source}: " + "; ".join(errors))


def _task_errors(module: Module) -> list[str]:
    errors: list[str] = []
    current = {d.id for d in module.gold.decisions if d.superseded_by is None}
    current |= {lesson.id for lesson in module.gold.lessons}
    current |= {f"contract:{c.contract_id}" for c in module.gold.contracts}
    task_ids = [task.id for task in module.tasks]
    if len(task_ids) != len(set(task_ids)):
        errors.append("task ids must be unique")
    for task in module.tasks:
        requirement_ids = [r.id for r in task.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            errors.append(f"{task.id}: requirement ids must be unique")
        for requirement in task.requirements:
            if requirement.ref not in current:
                errors.append(
                    f"{task.id}.{requirement.id}: ref {requirement.ref!r} is not a current gold "
                    "decision, a lesson, or contract:<current contract id>"
                )
            for pattern in requirement.violation_patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"{task.id}.{requirement.id}: bad pattern {pattern!r}: {exc}")
    return errors


def requirement_category(module: Module, requirement: ModuleRequirement) -> str:
    if requirement.ref.startswith("contract:"):
        return "contract"
    if any(lesson.id == requirement.ref for lesson in module.gold.lessons):
        return "lesson"
    return "decision"


def requirement_last_seq(module: Module, requirement: ModuleRequirement) -> int:
    """Sequence number of the newest activity the requirement's gold rests on."""

    if requirement.ref.startswith("contract:"):
        contract_id = requirement.ref.removeprefix("contract:")
        gold = next(c for c in module.gold.contracts if c.contract_id == contract_id)
        return module.seq(gold.activity_id)
    memory = next(
        m for m in [*module.gold.decisions, *module.gold.lessons] if m.id == requirement.ref
    )
    return max(module.seq(src.activity_id) for src in memory.sources)


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    return max(1, ascii_chars // 4 + (len(text) - ascii_chars))


# ---------------------------------------------------------------------------
# The host side of /curate: replay activities, hold the module's memories
# ---------------------------------------------------------------------------


class FakeModuleCuratorLLM:
    """Deterministic curate replies for ``--fake-llm``: one lesson per failure.

    Each failure is assigned to its own lesson quoting the first 40 characters
    of the failure text; no decisions are recorded.
    """

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        marker = "Failures to account for (each needs exactly one assignment): "
        line = next((ln for ln in user.splitlines() if ln.startswith(marker)), marker)
        ids = [part.strip() for part in line.removeprefix(marker).split(",") if part.strip()]
        ids = [activity_id for activity_id in ids if activity_id != "(none)"]
        assignments: list[dict[str, Any]] = []
        lessons: list[dict[str, Any]] = []
        for activity_id in ids:
            prefix = f"[{activity_id}] "
            rendered = next((ln for ln in user.splitlines() if ln.startswith(prefix)), "")
            body = rendered.split("): ", 1)[-1]
            quote = body[:40].strip()
            key = f"lesson.{activity_id}"
            assignments.append({"activity_id": activity_id, "lesson": key, "quote": quote})
            lessons.append({"topic_key": key, "statement": f"Avoid: {quote}"})
        return {"assignments": assignments, "lessons": lessons, "memories": []}


@dataclass
class CurateReplay:
    """Everything the host accumulated while curating one module."""

    active: dict[str, CurateMemory] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    assignments: list[CurateAssignment] = field(default_factory=list)
    unaccounted: list[str] = field(default_factory=list)
    calls: int = 0
    llm_calls: int = 0
    repairs: int = 0
    calls_with_initial_violations: int = 0
    final_violations: int = 0
    rejected_memories: int = 0
    gate_lag_s: list[float] = field(default_factory=list)


def _curate_activity(module: Module, seq: int, activity: ModuleActivity) -> CurateActivity:
    return CurateActivity(
        id=activity.id,
        seq=seq,
        type=activity.type,
        speaker=module.speaker_name(activity),
        text=activity.text,
    )


def curate_module(
    module: Module,
    llm: CuratorLLM,
    *,
    window_size: int = 12,
    max_repairs: int = 2,
) -> CurateReplay:
    """Replay a module through the curate graph as a stateful host would."""

    replay = CurateReplay()
    pending: list[CurateActivity] = []
    done: list[CurateActivity] = []
    status: dict[str, dict[str, Any]] = {}

    def flush() -> None:
        if not pending:
            return
        request = CurateRequest(
            scope_id=module.module_id,
            active=list(replay.active.values())[-60:],
            context=done[-CONTEXT_ACTIVITIES:],
            window=pending,
            max_repairs=max_repairs,
        )
        started = time.perf_counter()
        response = run_curate(request, llm)
        elapsed = time.perf_counter() - started
        replay.calls += 1
        replay.llm_calls += response.diagnostics.llm_calls
        replay.repairs += response.diagnostics.repairs
        replay.calls_with_initial_violations += bool(response.diagnostics.initial_violations)
        replay.final_violations += len(response.diagnostics.final_violations)
        replay.rejected_memories += response.diagnostics.rejected_memories
        replay.assignments.extend(response.assignments)
        replay.unaccounted.extend(response.unaccounted)
        if request.failures:
            replay.gate_lag_s.append(elapsed)
        for version in response.memories:
            if version.supersedes_id is not None:
                replay.active.pop(version.supersedes_id, None)
                if version.supersedes_id in status:
                    status[version.supersedes_id]["status"] = "superseded"
            memory = CurateMemory.model_validate(version.model_dump(exclude={"supersedes_id"}))
            replay.active[memory.id] = memory
            row = {**memory.model_dump(), "status": "active"}
            status[memory.id] = row
            replay.history.append(row)
        done.extend(pending)
        pending.clear()

    for seq, activity in enumerate(module.activities, start=1):
        pending.append(_curate_activity(module, seq, activity))
        if activity.type in FLUSH_ACTIVITY_TYPES or len(pending) >= window_size:
            flush()
    flush()
    return replay


def _curated_memories(replay: CurateReplay) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "source_activity_ids": sorted({s["activity_id"] for s in row["sources"]}),
        }
        for row in replay.history
    ]


def _gold_memories(module: Module) -> list[dict[str, Any]]:
    out = []
    for kind, memories in (("decision", module.gold.decisions), ("lesson", module.gold.lessons)):
        for memory in memories:
            source_ids = sorted({src.activity_id for src in memory.sources})
            out.append(
                {
                    "id": f"{module.module_id}.{memory.id}",
                    "kind": kind,
                    "topic_key": memory.topic_key,
                    "statement": memory.statement,
                    "version": max(module.seq(aid) for aid in source_ids),
                    "occurrences": memory.occurrences,
                    "status": "superseded" if memory.superseded_by else "active",
                    "source_activity_ids": source_ids,
                    "sources": [s.model_dump() for s in memory.sources],
                }
            )
    return out


# ---------------------------------------------------------------------------
# Evidence per arm
# ---------------------------------------------------------------------------


def _item(rank: int, item_id: str, layer: str, text: str) -> EvidenceItem:
    return EvidenceItem(
        rank=rank,
        item_id=item_id,
        layer=layer,
        text=text,
        estimated_tokens=estimate_tokens(text),
        document_id=item_id,
        source_refs=(),
    )


def current_contracts(module: Module) -> list[ModuleActivity]:
    newest: dict[str, ModuleActivity] = {}
    for activity in module.activities:
        if activity.type != "contract_revision" or activity.contract_id is None:
            continue
        current = newest.get(activity.contract_id)
        if current is None or (activity.contract_version or 0) > (current.contract_version or 0):
            newest[activity.contract_id] = activity
    return [newest[contract_id] for contract_id in sorted(newest)]


def render_module_memory(
    module: Module,
    memories: Sequence[dict[str, Any]],
    *,
    budget: int,
) -> tuple[list[EvidenceItem], dict[str, Any]]:
    """Reference rendering of the module memory file a host hands to its owner.

    Current contracts come first and are not budgeted (they are files the owner
    opens). Then active lessons, most occurrences first, then decisions and
    facts, newest first, while they fit in ``budget`` estimated tokens.
    """

    items: list[EvidenceItem] = []
    contracts = current_contracts(module)
    for activity in contracts:
        items.append(
            _item(
                len(items) + 1,
                activity.id,
                "contract",
                f"Current contract {activity.contract_id} v{activity.contract_version}:\n"
                f"{activity.text}",
            )
        )
    active = [m for m in memories if m.get("status", "active") == "active"]
    lessons = sorted(
        (m for m in active if m["kind"] == "lesson"),
        key=lambda m: (-int(m.get("occurrences", 1)), -int(m.get("version", 0)), str(m["id"])),
    )
    others = sorted(
        (m for m in active if m["kind"] != "lesson"),
        key=lambda m: (-int(m.get("version", 0)), str(m["id"])),
    )
    spent = 0
    omitted = 0
    for memory in [*lessons, *others]:
        if memory["kind"] == "lesson":
            count = int(memory.get("occurrences", 1))
            note = f" (failed {count} times)" if count > 1 else ""
            text = f"Lesson{note}: {memory['statement']}"
        else:
            text = f"{str(memory['kind']).capitalize()}: {memory['statement']}"
        tokens = estimate_tokens(text)
        if spent + tokens > budget:
            omitted += 1
            continue
        spent += tokens
        items.append(_item(len(items) + 1, str(memory["id"]), str(memory["kind"]), text))
    stats = {
        "contracts": len(contracts),
        "lessons": sum(1 for item in items if item.layer == "lesson"),
        "others": sum(1 for item in items if item.layer not in {"contract", "lesson"}),
        "memory_tokens": spent,
        "omitted": omitted,
        "budget": budget,
    }
    return items, stats


def _activity_text(module: Module, activity: ModuleActivity) -> str:
    return f"({activity.type}) {module.speaker_name(activity)}: {activity.text}"


def _activities_evidence(
    module: Module, activities: Sequence[ModuleActivity]
) -> list[EvidenceItem]:
    return [
        _item(rank, activity.id, "activity", _activity_text(module, activity))
        for rank, activity in enumerate(activities, start=1)
    ]


def _raw_log(module: Module, budget: int) -> list[ModuleActivity]:
    kept: list[ModuleActivity] = []
    spent = 0
    for activity in reversed(module.activities):
        tokens = estimate_tokens(_activity_text(module, activity))
        if spent + tokens > budget:
            break
        spent += tokens
        kept.append(activity)
    return list(reversed(kept))


# ---------------------------------------------------------------------------
# Retrieval arm: raw activities in a MemoryOS session
# ---------------------------------------------------------------------------


def _archive_id(module: Module) -> str:
    return f"xmuse-module-{module.module_id}"


def _retrieval_service(module: Module, service: MemoryOSService) -> str:
    session = service.create_session(f"modulemem {module.module_id}")
    service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id=_archive_id(module),
            scope_type="session",
            scope_id=session.id,
            source_refs=[
                ArchiveSourceRefPayload(
                    source_type="document", source_id=f"binding-{module.module_id}"
                )
            ],
        )
    )
    participants = {p.id: p for p in module.participants}
    for seq, activity in enumerate(module.activities, start=1):
        participant = participants.get(activity.speaker)
        metadata: dict[str, Any] = {
            "activity_type": activity.type,
            "activity_seq": seq,
            "participant_id": activity.speaker,
        }
        service.ingest(
            session.id,
            MessageCreate(
                role=Role.USER if participant and participant.kind == "human" else Role.ASSISTANT,
                content=activity.text,
                external_id=f"{XMUSE_MESSAGE_ID_PREFIX}{activity.id}",
                metadata={**metadata, "speaker_name": module.speaker_name(activity)},
            ),
        )
        document_id = f"{XMUSE_ACTIVITY_DOC_PREFIX}{activity.id}"
        service.ingest_archive_document(
            ArchiveDocumentIngestRequest(
                document_id=document_id,
                title=document_id,
                content=activity.text,
                source_refs=[
                    ArchiveSourceRefPayload(source_type="document", source_id=document_id)
                ],
                identity=ArchiveIdentityArchive(kind="archive", archive_id=_archive_id(module)),
                metadata=metadata,
            )
        )
    return session.id


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _probe_category(module: Module, probe: ModuleProbe) -> str:
    lessons = {lesson.id for lesson in module.gold.lessons}
    if any(answer.startswith("contract:") for answer in probe.answer_ids):
        return "contract"
    if any(answer in lessons for answer in probe.answer_ids):
        return "lesson"
    return "decision"


def _probe_statements(module: Module, probe: ModuleProbe) -> tuple[list[str], list[str]]:
    current: list[str] = []
    superseded: list[str] = []
    decisions = {d.id: d for d in module.gold.decisions}
    lessons = {lesson.id: lesson for lesson in module.gold.lessons}
    for answer in probe.answer_ids:
        if answer.startswith("contract:"):
            contract_id = answer.removeprefix("contract:")
            revisions = [a for a in module.activities if a.contract_id == contract_id]
            newest = max(revisions, key=lambda a: a.contract_version or 0, default=None)
            if newest is not None:
                current.append(newest.text)
                superseded.extend(a.text for a in revisions if a is not newest)
        elif answer in decisions:
            memory = decisions[answer]
            current.append(memory.statement)
            superseded.extend(
                d.statement
                for d in module.gold.decisions
                if d.superseded_by and d.topic_key == memory.topic_key
            )
        elif answer in lessons:
            current.append(lessons[answer].statement)
    return current, superseded


def _write_side(module: Module, memories: list[dict[str, Any]]) -> dict[str, Any]:
    gold = [
        GoldMemory(
            id=memory.id,
            kind=kind,
            scope="room",
            topic_key=memory.topic_key,
            statement=memory.statement,
            sources=[
                GoldMemorySource(message_id=s.activity_id, quote=s.quote) for s in memory.sources
            ],
            superseded_by=memory.superseded_by,
        )
        for kind, group in (("decision", module.gold.decisions), ("lesson", module.gold.lessons))
        for memory in group
    ]
    views = [
        CuratedMemoryView(
            id=memory["id"],
            kind=memory["kind"],
            topic_key=memory["topic_key"],
            statement=memory["statement"],
            sources=[
                GoldMemorySource(message_id=s["activity_id"], quote=s["quote"] or "-")
                for s in memory["sources"]
                if s["activity_id"]
            ]
            or [GoldMemorySource(message_id="a00", quote="-")],
            status=memory["status"],
        )
        for memory in memories
    ]
    active_views = [view for view in views if view.status == "active"]
    matches = match_curated_to_gold(active_views, [g for g in gold if g.superseded_by is None])
    by_gold = {match.gold_id: match.curated_id for match in matches}
    occurrences = {memory["id"]: memory["occurrences"] for memory in memories}
    lesson_gold = {lesson.id: lesson for lesson in module.gold.lessons}
    lesson_matches = [gid for gid in by_gold if gid in lesson_gold]
    occurrence_exact = sum(
        1 for gid in lesson_matches if occurrences.get(by_gold[gid]) == lesson_gold[gid].occurrences
    )
    occurrence_over = sum(
        1
        for gid in lesson_matches
        if occurrences.get(by_gold[gid], 1) > lesson_gold[gid].occurrences
    )
    repeated = [lesson.id for lesson in module.gold.lessons if lesson.occurrences >= 2]
    repeated_seen = sum(
        1 for gid in repeated if gid in by_gold and occurrences.get(by_gold[gid], 1) >= 2
    )
    # An active memory that best matches a superseded gold decision is stale.
    superseded_gold = [d for d in module.gold.decisions if d.superseded_by]
    stale_active = len(
        match_curated_to_gold(active_views, [g for g in gold if g.superseded_by is not None])
    )
    current_gold = [g for g in gold if g.superseded_by is None]
    return {
        "active_memories": len(active_views),
        "current_gold": len(current_gold),
        "matched_current": len(matches),
        "matched_lessons": len(lesson_matches),
        "gold_lessons": len(module.gold.lessons),
        "lesson_occurrences_exact": occurrence_exact,
        "lesson_occurrences_over": occurrence_over,
        "repeated_lessons": len(repeated),
        "repeated_lessons_recognized": repeated_seen,
        "superseded_gold": len(superseded_gold),
        "stale_active": stale_active,
    }


def accounting_metrics(
    module: Module,
    assignments: Sequence[CurateAssignment],
    unaccounted: Sequence[str],
) -> dict[str, int]:
    """Compare failure assignments with the gold lesson clusters.

    Gold: a failure cited by a gold lesson belongs to that lesson; any other
    failure should be dismissed. Pairwise counts are over failure pairs: a
    pair is "together" when both belong to the same lesson.
    """

    failures = [a.id for a in module.activities if a.type in FLUSH_ACTIVITY_TYPES]
    gold_of: dict[str, str | None] = {activity_id: None for activity_id in failures}
    for lesson in module.gold.lessons:
        for src in lesson.sources:
            if src.activity_id in gold_of and gold_of[src.activity_id] is None:
                gold_of[src.activity_id] = lesson.id
    pred_of: dict[str, str | None] = {}
    for assignment in assignments:
        pred_of.setdefault(assignment.activity_id, assignment.lesson)
    tp = fp = fn = 0
    for left, right in combinations(failures, 2):
        gold_together = gold_of[left] is not None and gold_of[left] == gold_of[right]
        pred_together = pred_of.get(left) is not None and pred_of.get(left) == pred_of.get(right)
        tp += gold_together and pred_together
        fp += pred_together and not gold_together
        fn += gold_together and not pred_together
    assigned = [f for f in failures if f in pred_of]
    return {
        "failures": len(failures),
        "unaccounted": len(set(unaccounted) & set(failures)),
        "dismissed": sum(1 for f in assigned if pred_of[f] is None),
        "dismissed_gold_lesson": sum(
            1 for f in assigned if pred_of[f] is None and gold_of[f] is not None
        ),
        "lesson_gold_dismiss": sum(
            1 for f in assigned if pred_of[f] is not None and gold_of[f] is None
        ),
        "pair_tp": tp,
        "pair_fp": fp,
        "pair_fn": fn,
    }


# ---------------------------------------------------------------------------
# Behavior: owner tasks
# ---------------------------------------------------------------------------

CODER_SYSTEM_PROMPT = """You are the owner agent of one software module in a multi-agent \
project. Your previous session ended; the host gives you whatever module memory it has, which \
may be empty. Implement the task as a code change in the module's language and stack. Follow \
the module's current contracts, decisions and conventions, and avoid mistakes the module has \
already made, whenever the memory tells you about them; where it says nothing, use your best \
judgment. Reply with the code (one or more files, each headed by its path) and at most three \
short lines of notes. Do not ask questions."""

TASK_JUDGE_SYSTEM_PROMPT = """You grade a code change against requirements of the module it \
changes. Each requirement has a check, the module's current rule it comes from, and old values \
that are no longer in force. The current rule is authoritative; the check only explains how it \
applies to this task, so do not require details the current rule does not state. Label every \
requirement:
- "satisfied": the code clearly follows the requirement;
- "violated": the code contradicts it, for example a wrong name, value, field or helper, an old \
value, or the mistake the requirement warns about;
- "not_addressed": the code neither follows nor contradicts it.
Judge only from the code and notes shown. Reply with one JSON object mapping each requirement \
id to its label, for example {"r1": "satisfied", "r2": "violated"}."""


class OwnerCoder(Protocol):
    def write(
        self, *, module: Module, task: ModuleTask, evidence: Sequence[EvidenceItem]
    ) -> str: ...


class TaskJudge(Protocol):
    def judge_task(
        self, *, task: ModuleTask, code: str, requirements: Sequence[dict[str, Any]]
    ) -> dict[str, str]: ...


def _memory_block(evidence: Sequence[EvidenceItem]) -> str:
    if not evidence:
        return "(none)"
    return "\n".join(f"[{item.rank}] ({item.layer}) {item.text}" for item in evidence)


class ChatOwnerCoder:
    def __init__(self, chat: ChatCompletionClient) -> None:
        self._chat = chat

    def write(self, *, module: Module, task: ModuleTask, evidence: Sequence[EvidenceItem]) -> str:
        user = (
            f"Module: {module.title or module.module_id} (project {module.project})\n\n"
            f"Module memory from the host:\n{_memory_block(evidence)}\n\n"
            f"Task: {task.prompt}"
        )
        return self._chat.complete(system=CODER_SYSTEM_PROMPT, user=user).strip()


class ChatTaskJudge:
    def __init__(self, chat: ChatCompletionClient) -> None:
        self._chat = chat

    def judge_task(
        self, *, task: ModuleTask, code: str, requirements: Sequence[dict[str, Any]]
    ) -> dict[str, str]:
        user = json.dumps(
            {"task": task.prompt, "requirements": list(requirements), "code": code},
            ensure_ascii=False,
        )
        data = _extract_json_object(self._chat.complete(system=TASK_JUDGE_SYSTEM_PROMPT, user=user))
        data = data or {}
        return {
            str(r["id"]): label
            if (label := str(data.get(r["id"], "")).strip().lower()) in TASK_LABELS
            else "not_addressed"
            for r in requirements
        }


class FakeOwnerCoder:
    """Deterministic coder for ``--fake-llm``: writes the memory it was given as comments."""

    def write(self, *, module: Module, task: ModuleTask, evidence: Sequence[EvidenceItem]) -> str:
        return "\n".join(f"# {item.text}" for item in evidence) or "# NO_MEMORY"


class FakeTaskJudge:
    """Satisfied when the requirement's current rule appears in the code, else not_addressed."""

    def judge_task(
        self, *, task: ModuleTask, code: str, requirements: Sequence[dict[str, Any]]
    ) -> dict[str, str]:
        normalized = _normalize_match_text(code)
        return {
            str(r["id"]): "satisfied"
            if any(
                (rule := _normalize_match_text(text)) and rule in normalized
                for text in r["current"]
            )
            else "not_addressed"
            for r in requirements
        }


AGENT_TASK_PROMPT = """{prompt}

Make this change in the repository in the current directory. AGENTS.md holds whatever module \
memory the host has for you, which may be none. Do not ask questions. When you are done, reply \
with at most three short lines of notes."""

MAX_AGENT_DIFF_CHARS = 60_000
AGENT_GIT_EXCLUDES = ("__pycache__/", "*.pyc", ".pytest_cache/", "node_modules/", ".venv/")


def load_seed(seeds_dir: str | Path, module_id: str) -> dict[str, str]:
    """A module's seed repository: ``<seeds_dir>/<module_id>.json`` = {"files": {path: text}}."""

    path = Path(seeds_dir) / f"{module_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModuleMemError(f"{path}: {exc}") from exc
    files = data.get("files") if isinstance(data, dict) else None
    if (
        not isinstance(files, dict)
        or not files
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items())
    ):
        raise ModuleMemError(f'{path}: needs a non-empty "files" object of path -> text')
    for relative in files:
        parts = Path(relative).parts
        if Path(relative).is_absolute() or ".." in parts or (parts and parts[0] == ".git"):
            raise ModuleMemError(f"{path}: bad seed path {relative!r}")
    return files


def agents_file(module: Module, evidence: Sequence[EvidenceItem]) -> str:
    """The AGENTS.md an owner agent starts with: the module, then the arm's memory if any."""

    title = module.title or module.module_id
    head = f"# {title}\n\nYou own this module of project {module.project}.\n"
    if not evidence:
        return head
    return f"{head}\n## Module memory from the host\n\n{_memory_block(evidence)}\n"


def _git(workspace: Path, *args: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "user.name=modulemem",
            "-c",
            "user.email=modulemem@localhost",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ModuleMemError(f"git {args[0]} failed in {workspace}: {completed.stderr[-500:]}")
    return completed.stdout


class AgentOwnerCoder:
    """Owner coder that runs an external coding agent on a copy of the module's seed repository.

    ``command`` is invoked as ``command --workspace DIR`` with the task on stdin (the interface
    of a sandboxed agent wrapper); its stdout is the agent's notes. The workspace is the seed
    repository committed once together with the arm's memory in ``AGENTS.md``, so the code the
    judge sees is exactly the agent's ``git diff``. Results are cached on disk by module, task,
    repeat and memory, so a rerun after a failure resumes where it stopped.
    """

    def __init__(
        self,
        *,
        command: Sequence[str],
        seeds_dir: str | Path,
        work_root: Path,
        cache_dir: Path,
        repeat: int,
        timeout_s: float = 1800.0,
    ) -> None:
        self._command = list(command)
        self._seeds_dir = Path(seeds_dir)
        self._work_root = work_root
        self._cache_dir = cache_dir
        self._repeat = repeat
        self._timeout_s = timeout_s

    def write(self, *, module: Module, task: ModuleTask, evidence: Sequence[EvidenceItem]) -> str:
        memory = agents_file(module, evidence)
        key = hashlib.sha256(
            json.dumps([module.module_id, task.id, task.prompt, self._repeat, memory]).encode()
        ).hexdigest()[:16]
        name = f"{module.module_id}-{task.id}-r{self._repeat}-{key}"
        cache = self._cache_dir / f"{name}.json"
        if cache.exists():
            return str(json.loads(cache.read_text(encoding="utf-8"))["code"])
        workspace = self._work_root / name
        shutil.rmtree(workspace, ignore_errors=True)
        workspace.mkdir(parents=True)
        for relative, text in load_seed(self._seeds_dir, module.module_id).items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (workspace / "AGENTS.md").write_text(memory, encoding="utf-8")
        _git(workspace, "init", "-q")
        (workspace / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (workspace / ".git" / "info" / "exclude").write_text(
            "\n".join(AGENT_GIT_EXCLUDES) + "\n", encoding="utf-8"
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-q", "-m", "seed")
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [*self._command, "--workspace", str(workspace)],
                input=AGENT_TASK_PROMPT.format(prompt=task.prompt),
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ModuleMemError(f"coding agent timed out on {module.module_id} {task.id}") from exc
        if completed.returncode != 0:
            raise ModuleMemError(
                f"coding agent failed on {module.module_id} {task.id} "
                f"(exit {completed.returncode}): {completed.stderr[-500:]}"
            )
        _git(workspace, "add", "-A")
        diff = _git(workspace, "diff", "--cached", "--no-color")
        code = diff[:MAX_AGENT_DIFF_CHARS]
        if len(diff) > MAX_AGENT_DIFF_CHARS:
            code += "\n[diff truncated]"
        notes = completed.stdout.strip()[-1500:]
        if notes:
            code += f"\n\nNotes:\n{notes}"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "code": code,
                    "diff_chars": len(diff),
                    "files_changed": _git(workspace, "diff", "--cached", "--name-only").split(),
                    "seconds": round(time.monotonic() - started, 1),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return code


def _added_text(code: str) -> str:
    """The lines a unified diff adds; any other code is returned unchanged."""

    if not code.startswith("diff --git"):
        return code
    return "\n".join(
        line[1:]
        for line in code.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


TaskLLMFactory = Callable[[int], tuple[OwnerCoder, TaskJudge]]


def build_task_llm_factory(
    *,
    out_dir: Path,
    fake_llm: bool,
    settings: Settings | None = None,
    usage: LLMUsageTracker | None = None,
    coder_llm: str | None = None,
    judge_llm: str | None = None,
    coder_command: Sequence[str] = (),
    seeds_dir: str | Path | None = None,
    coder_timeout_s: float = 1800.0,
) -> TaskLLMFactory:
    """Per-repeat coder/task-judge factory with the same disk cache as the probe roles.

    With ``coder_command`` the owner is an external coding agent working on the module's
    seed repository (:class:`AgentOwnerCoder`) instead of an LLM writing patch text.
    """

    cache_dir = out_dir / "llm_cache"

    def agent(repeat: int) -> OwnerCoder:
        assert seeds_dir is not None
        return AgentOwnerCoder(
            command=coder_command,
            seeds_dir=seeds_dir,
            work_root=out_dir / "agent_work",
            cache_dir=cache_dir / "agent",
            repeat=repeat,
            timeout_s=coder_timeout_s,
        )

    if fake_llm:
        return lambda repeat: (
            agent(repeat) if coder_command else FakeOwnerCoder(),
            FakeTaskJudge(),
        )
    resolved = settings or get_settings()
    coder_client = (
        None if coder_command else RemoteChatClient(settings_for_llm_spec(resolved, coder_llm))
    )
    judge_client = RemoteChatClient(settings_for_llm_spec(resolved, judge_llm))

    def factory(repeat: int) -> tuple[OwnerCoder, TaskJudge]:
        judge = DiskCachedChatClient(
            judge_client, role="task_judge", cache_dir=cache_dir, repeat=repeat, usage=usage
        )
        if coder_client is None:
            return agent(repeat), ChatTaskJudge(judge)
        coder = DiskCachedChatClient(
            coder_client, role="coder", cache_dir=cache_dir, repeat=repeat, usage=usage
        )
        return ChatOwnerCoder(coder), ChatTaskJudge(judge)

    return factory


def _requirement_payload(module: Module, requirement: ModuleRequirement) -> dict[str, Any]:
    probe = ModuleProbe(id=requirement.id, question=requirement.check, answer_ids=[requirement.ref])
    current, old = _probe_statements(module, probe)
    return {"id": requirement.id, "check": requirement.check, "current": current, "old": old}


def _run_tasks(
    module: Module,
    *,
    arm: str,
    repeat: int,
    coder: OwnerCoder,
    judge: TaskJudge,
    evidence_for: Callable[[str], list[EvidenceItem]],
) -> list[dict[str, Any]]:
    third = len(module.activities) / 3
    rows: list[dict[str, Any]] = []
    for task in module.tasks:
        evidence = evidence_for(task.prompt)
        code = coder.write(module=module, task=task, evidence=evidence)
        payloads = [_requirement_payload(module, r) for r in task.requirements]
        labels = judge.judge_task(task=task, code=code, requirements=payloads)
        scanned = _added_text(code)
        for requirement in task.requirements:
            rows.append(
                {
                    "arm": arm,
                    "module": module.module_id,
                    "repeat": repeat,
                    "task": task.id,
                    "requirement": requirement.id,
                    "ref": requirement.ref,
                    "category": requirement_category(module, requirement),
                    "early": requirement_last_seq(module, requirement) <= third,
                    "label": labels.get(requirement.id, "not_addressed"),
                    "pattern_violation": any(
                        re.search(pattern, scanned) for pattern in requirement.violation_patterns
                    ),
                    "evidence_tokens": sum(item.estimated_tokens for item in evidence),
                    "code": code,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleMemConfig:
    arms: tuple[str, ...]
    repeats: int = 1
    embedding: str = "none"
    fake_llm: bool = False
    curator_llm: str | None = None
    answerer_llm: str | None = None
    judge_llm: str | None = None
    curator_window: int = 12
    pack_budget: int = 1500
    max_repairs: int = 2
    probes: bool = True
    tasks: bool = False
    coder_command: tuple[str, ...] = ()
    seeds_dir: str | None = None
    coder_timeout_s: float = 1800.0


def run_modulemem(
    modules: Sequence[Module],
    *,
    out_dir: str | Path,
    config: ModuleMemConfig,
    settings: Settings | None = None,
    curated_llm_factory: Any = None,
    llm_factory: Any = None,
    task_llm_factory: TaskLLMFactory | None = None,
    scratch_root: str | Path | None = None,
) -> dict[str, Any]:
    for arm in config.arms:
        if arm not in MODULEMEM_ARMS:
            raise ModuleMemError(f"unknown arm {arm!r}; valid: {', '.join(MODULEMEM_ARMS)}")
    if not config.probes and not config.tasks:
        raise ModuleMemError("nothing to run: enable probes, tasks, or both")
    if config.tasks and not any(module.tasks for module in modules):
        raise ModuleMemError("--tasks needs modules that carry tasks")
    if config.coder_command:
        if not config.tasks:
            raise ModuleMemError("a coder command only runs owner tasks; add --tasks")
        if config.seeds_dir is None:
            raise ModuleMemError("a coder command needs --seeds")
        for module in modules:
            if module.tasks:
                load_seed(config.seeds_dir, module.module_id)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    tracker = LLMUsageTracker()
    base = settings or get_settings()
    factory = llm_factory or build_llm_factory(
        out_dir=out_path,
        fake_llm=config.fake_llm,
        settings=base,
        usage=tracker,
        answerer_llm=config.answerer_llm,
        judge_llm=config.judge_llm,
    )
    task_factory: TaskLLMFactory | None = None
    if config.tasks:
        task_factory = task_llm_factory or build_task_llm_factory(
            out_dir=out_path,
            fake_llm=config.fake_llm,
            settings=base,
            usage=tracker,
            coder_llm=config.answerer_llm,
            judge_llm=config.judge_llm,
            coder_command=config.coder_command,
            seeds_dir=config.seeds_dir,
            coder_timeout_s=config.coder_timeout_s,
        )
    created_scratch = scratch_root is None
    scratch = Path(scratch_root) if scratch_root else Path(tempfile.mkdtemp(prefix="modulemem-"))
    results: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []
    packs: list[dict[str, Any]] = []
    write_side: list[dict[str, Any]] = []
    lags: list[float] = []
    try:
        for arm in config.arms:
            for repeat in range(config.repeats):
                answerer, judge = factory(repeat)
                roles = task_factory(repeat) if task_factory is not None else None
                for module in modules:
                    with deterministic_ids(f"modulemem:{arm}:r{repeat}:{module.module_id}"):
                        rows, tasks, pack_row, ws, lag = _run_module_arm(
                            module,
                            arm=arm,
                            repeat=repeat,
                            config=config,
                            base=base,
                            answerer=answerer,
                            judge=judge,
                            task_roles=roles,
                            data_dir=scratch / arm / f"{module.module_id}-r{repeat}",
                            cache_dir=out_path / "llm_cache",
                            usage=tracker,
                            curated_llm_factory=curated_llm_factory,
                        )
                    results.extend(rows)
                    task_rows.extend(tasks)
                    if pack_row is not None:
                        packs.append(pack_row)
                    if ws is not None:
                        write_side.append(ws)
                    lags.extend(lag)
    finally:
        if created_scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    summary = _summarize(results, packs, write_side, lags, config, tracker)
    summary["behavior"] = summarize_tasks(task_rows, config.arms) if config.tasks else {}
    (out_path / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results), encoding="utf-8"
    )
    if config.tasks:
        (out_path / "tasks.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in task_rows),
            encoding="utf-8",
        )
    (out_path / "packs.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in packs), encoding="utf-8"
    )
    (out_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_path / "summary.md").write_text(render_modulemem_md(summary), encoding="utf-8")
    return summary


def _curator_llm(
    config: ModuleMemConfig,
    base: Settings,
    repeat: int,
    cache_dir: Path,
    usage: LLMUsageTracker,
    curated_llm_factory: Any,
) -> CuratorLLM:
    llm_settings = base if config.fake_llm else settings_for_llm_spec(base, config.curator_llm)
    if curated_llm_factory is not None:
        llm: CuratorLLM = curated_llm_factory(llm_settings)
        return llm
    if config.fake_llm:
        return FakeModuleCuratorLLM()
    built = build_curator_llm(llm_settings)
    if built is None:
        raise RoomMemConfigError(f"the pack arm needs {llm_settings.chat_api_key_name}")
    return DiskCachedCuratorLLM(
        built, model=llm_settings.chat_model, cache_dir=cache_dir, repeat=repeat, usage=usage
    )


def _run_module_arm(
    module: Module,
    *,
    arm: str,
    repeat: int,
    config: ModuleMemConfig,
    base: Settings,
    answerer: RoomMemAnswerer,
    judge: RoomMemJudge,
    task_roles: tuple[OwnerCoder, TaskJudge] | None,
    data_dir: Path,
    cache_dir: Path,
    usage: LLMUsageTracker,
    curated_llm_factory: Any,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
    list[float],
]:
    pack_row: dict[str, Any] | None = None
    ws: dict[str, Any] | None = None
    lags: list[float] = []
    evidence: list[EvidenceItem] = []
    service: MemoryOSService | None = None
    session_id = ""
    if arm in {"pack", "oracle_pack"}:
        replay: CurateReplay | None = None
        if arm == "pack":
            llm = _curator_llm(config, base, repeat, cache_dir, usage, curated_llm_factory)
            replay = curate_module(
                module, llm, window_size=config.curator_window, max_repairs=config.max_repairs
            )
            memories = _curated_memories(replay)
        else:
            memories = _gold_memories(module)
        evidence, stats = render_module_memory(module, memories, budget=config.pack_budget)
        pack_row = {
            "arm": arm,
            "module": module.module_id,
            "repeat": repeat,
            "file": stats,
            "evidence": [item.text for item in evidence],
            "memories": memories,
        }
        if replay is not None:
            curate_counts = {
                "calls": replay.calls,
                "llm_calls": replay.llm_calls,
                "repairs": replay.repairs,
                "calls_with_initial_violations": replay.calls_with_initial_violations,
                "final_violations": replay.final_violations,
                "rejected_memories": replay.rejected_memories,
            }
            pack_row["assignments"] = [a.model_dump() for a in replay.assignments]
            pack_row["curate"] = curate_counts
            ws = {
                "module": module.module_id,
                "repeat": repeat,
                **_write_side(module, memories),
                **accounting_metrics(module, replay.assignments, replay.unaccounted),
                **curate_counts,
            }
            lags = replay.gate_lag_s
    elif arm == "recent":
        evidence = _activities_evidence(module, module.activities[-RECENT_ACTIVITIES:])
    elif arm == "raw_log":
        evidence = _activities_evidence(module, _raw_log(module, config.pack_budget))
    elif arm == "full_history":
        evidence = _activities_evidence(module, module.activities)
    elif arm == "retrieval":
        service = MemoryOSService(
            settings=_room_settings(data_dir, embedding=config.embedding, kernel_external=False)
        )
        session_id = _retrieval_service(module, service)

    def evidence_for(query: str) -> list[EvidenceItem]:
        if service is None:
            return evidence
        package = service.build_context(
            session_id=session_id,
            task=XMUSE_TASK,
            budget=800,
            retrieval_query=query,
            include_global_core=False,
        )
        return _evidence_items(build_source_evidence(package, schema_version="v2"))

    task_rows: list[dict[str, Any]] = []
    if task_roles is not None and module.tasks:
        coder, task_judge = task_roles
        task_rows = _run_tasks(
            module,
            arm=arm,
            repeat=repeat,
            coder=coder,
            judge=task_judge,
            evidence_for=evidence_for,
        )

    rows: list[dict[str, Any]] = []
    for probe in module.probes if config.probes else []:
        evidence = evidence_for(probe.question)
        answer = answerer.answer(question=probe.question, evidence=evidence)
        current, superseded = _probe_statements(module, probe)
        label = judge.judge_answer(
            question=probe.question,
            current_statements=current,
            superseded_statements=superseded,
            answer=answer,
        )
        lowered = answer.casefold()
        rows.append(
            {
                "arm": arm,
                "module": module.module_id,
                "repeat": repeat,
                "probe": probe.id,
                "category": _probe_category(module, probe),
                "question": probe.question,
                "answer": answer,
                "judge": label if label in JUDGE_LABELS else "wrong",
                "substring": all(v.casefold() in lowered for v in probe.must_contain)
                and not any(v.casefold() in lowered for v in probe.must_not_contain),
                "evidence_tokens": sum(item.estimated_tokens for item in evidence),
                "evidence_items": len(evidence),
            }
        )
    return rows, task_rows, pack_row, ws, lags


def _rate(rows: Sequence[dict[str, Any]], label: str) -> float | None:
    return sum(1 for row in rows if row["judge"] == label) / len(rows) if rows else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _summarize(
    results: list[dict[str, Any]],
    packs: list[dict[str, Any]],
    write_side: list[dict[str, Any]],
    lags: list[float],
    config: ModuleMemConfig,
    tracker: LLMUsageTracker,
) -> dict[str, Any]:
    read: dict[str, Any] = {}
    for arm in config.arms:
        arm_rows = [row for row in results if row["arm"] == arm]
        by_category: dict[str, Any] = {}
        for category in ("contract", "decision", "lesson", "all"):
            rows = (
                arm_rows
                if category == "all"
                else [r for r in arm_rows if r["category"] == category]
            )
            by_category[category] = {
                "n": len(rows),
                **{label: _rate(rows, label) for label in JUDGE_LABELS},
                "substring": (sum(1 for r in rows if r["substring"]) / len(rows)) if rows else None,
                "evidence_tokens": (sum(r["evidence_tokens"] for r in rows) / len(rows))
                if rows
                else None,
            }
        read[arm] = by_category
    pack_stats: dict[str, Any] = {}
    for arm in ("pack", "oracle_pack"):
        rows = [p for p in packs if p["arm"] == arm]
        if not rows:
            continue
        pack_stats[arm] = {
            "files": len(rows),
            "mean_memory_tokens": sum(p["file"]["memory_tokens"] for p in rows) / len(rows),
            "omitted": sum(p["file"]["omitted"] for p in rows),
            "mean_items": sum(p["file"]["lessons"] + p["file"]["others"] for p in rows) / len(rows),
        }
    totals: dict[str, int] = {}
    for ws in write_side:
        for key, value in ws.items():
            if isinstance(value, int) and not isinstance(value, bool) and key != "repeat":
                totals[key] = totals.get(key, 0) + value
    accounting = {
        "pair_precision": _ratio(
            totals.get("pair_tp", 0), totals.get("pair_tp", 0) + totals.get("pair_fp", 0)
        ),
        "pair_recall": _ratio(
            totals.get("pair_tp", 0), totals.get("pair_tp", 0) + totals.get("pair_fn", 0)
        ),
        "unaccounted_rate": _ratio(totals.get("unaccounted", 0), totals.get("failures", 0)),
        "repair_rate": _ratio(
            totals.get("calls_with_initial_violations", 0), totals.get("calls", 0)
        ),
    }
    return {
        "run": {
            "arms": list(config.arms),
            "repeats": config.repeats,
            "embedding": config.embedding,
            "curator_llm": config.curator_llm,
            "answerer_llm": config.answerer_llm,
            "judge_llm": config.judge_llm,
            "pack_budget": config.pack_budget,
            "max_repairs": config.max_repairs,
            "fake_llm": config.fake_llm,
            "probes": config.probes,
            "tasks": config.tasks,
            "coder_command": list(config.coder_command),
        },
        "read_side": read,
        "files": pack_stats,
        "write_side": totals,
        "accounting": accounting,
        "gate_to_lesson_lag_s": {
            "n": len(lags),
            "mean": (sum(lags) / len(lags)) if lags else None,
            "max": max(lags) if lags else None,
        },
        "usage": tracker.aggregate(),
    }


def _task_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    return {
        "n": n,
        **{
            label: (sum(1 for r in rows if r["label"] == label) / n) if n else None
            for label in TASK_LABELS
        },
        "pattern_violation": (sum(1 for r in rows if r["pattern_violation"]) / n) if n else None,
    }


def summarize_tasks(rows: Sequence[dict[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    """Requirement-level rates per arm, by gold category and for early-only gold.

    ``tasks_all_satisfied`` counts a task once per repeat when every requirement
    is satisfied; ``evidence_tokens`` is the mean per task.
    """

    out: dict[str, Any] = {}
    for arm in arms:
        arm_rows = [r for r in rows if r["arm"] == arm]
        if not arm_rows:
            continue
        tasks: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
        for row in arm_rows:
            tasks.setdefault((row["module"], row["repeat"], row["task"]), []).append(row)
        stats: dict[str, Any] = {
            category: _task_stats([r for r in arm_rows if r["category"] == category])
            for category in REQUIREMENT_CATEGORIES
        }
        stats["early"] = _task_stats([r for r in arm_rows if r["early"]])
        stats["all"] = _task_stats(arm_rows)
        stats["tasks"] = len(tasks)
        stats["tasks_all_satisfied"] = sum(
            all(r["label"] == "satisfied" for r in group) for group in tasks.values()
        ) / len(tasks)
        stats["evidence_tokens"] = sum(
            group[0]["evidence_tokens"] for group in tasks.values()
        ) / len(tasks)
        out[arm] = stats
    return out


def render_modulemem_md(summary: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        return (
            "-" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))
        )

    lines = [
        "# ModuleMem summary",
        "",
        f"Run: {json.dumps(summary['run'], ensure_ascii=False)}",
        "",
    ]
    lines.append(
        "| arm | category | n | correct | stale | missing | wrong | substring | evidence tok |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for arm, categories in summary["read_side"].items():
        for category, stats in categories.items():
            lines.append(
                f"| {arm} | {category} | {stats['n']} | {fmt(stats['correct'])} "
                f"| {fmt(stats['stale'])} "
                f"| {fmt(stats['missing'])} | {fmt(stats['wrong'])} | {fmt(stats['substring'])} "
                f"| {fmt(stats['evidence_tokens'])} |"
            )
    behavior = summary.get("behavior") or {}
    if behavior:
        lines += [
            "",
            "## Behavior: owner tasks (requirement level)",
            "",
            "| arm | gold | n | satisfied | violated | not addressed | pattern violation |",
            "|---|---|---|---|---|---|---|",
        ]
        for arm, stats in behavior.items():
            for category in (*REQUIREMENT_CATEGORIES, "early", "all"):
                row = stats[category]
                lines.append(
                    f"| {arm} | {category} | {row['n']} | {fmt(row['satisfied'])} "
                    f"| {fmt(row['violated'])} | {fmt(row['not_addressed'])} "
                    f"| {fmt(row['pattern_violation'])} |"
                )
        lines += [
            "",
            "| arm | tasks | all requirements satisfied | evidence tok |",
            "|---|---|---|---|",
        ]
        for arm, stats in behavior.items():
            lines.append(
                f"| {arm} | {stats['tasks']} | {fmt(stats['tasks_all_satisfied'])} "
                f"| {fmt(stats['evidence_tokens'])} |"
            )
    lines += ["", "## Memory files", "", json.dumps(summary["files"], indent=1), ""]
    lines += [
        "## Curate write side (pack arm)",
        "",
        "Accounting: "
        + ", ".join(f"{key}={fmt(value)}" for key, value in summary["accounting"].items()),
        "",
        json.dumps(summary["write_side"], ensure_ascii=False, indent=1),
        "",
    ]
    lines += [
        "Gate failure to lesson available (one curate call, offline replay): "
        + json.dumps(summary["gate_to_lesson_lag_s"]),
        "",
        "Limitations: the dataset is LLM-authored (Muse Spark 1.3) and checked by rules, not by a "
        "human; the replay is offline, so lag is curate processing time, not wall-clock in a live "
        "Workroom; the oracle file renders gold memories as if a perfect curator ran.",
    ]
    return "\n".join(lines) + "\n"
