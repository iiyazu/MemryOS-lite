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

Scoring: the judge labels each answer (correct/stale/missing/wrong) against the
current gold; probes are grouped by what they ask about (contract, decision,
lesson). The ``pack`` arm also reports write-side matching against gold, lesson
occurrence accuracy, failure accounting against the gold lesson clusters
(pairwise precision/recall, dismissals, unaccounted), repair-loop use, and the
gate-failure-to-lesson latency of each curate call.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

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
    CuratedMemoryView,
    DiskCachedCuratorLLM,
    EvidenceItem,
    GoldMemory,
    GoldMemorySource,
    LLMUsageTracker,
    RoomMemAnswerer,
    RoomMemConfigError,
    RoomMemJudge,
    _evidence_items,
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
)
MODULEMEM_SPLITS: dict[str, tuple[str, ...]] = {
    "dev": ("mm01", "mm02", "mm03", "mm04"),
    "test": ("mm05", "mm06", "mm07", "mm08"),
}
RECENT_ACTIVITIES = 8
CONTEXT_ACTIVITIES = 4
FLUSH_ACTIVITY_TYPES = FAILURE_TYPES
JUDGE_LABELS = ("correct", "stale", "missing", "wrong")


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
    if errors:
        raise ModuleMemError(f"{source}: " + "; ".join(errors))


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


def run_modulemem(
    modules: Sequence[Module],
    *,
    out_dir: str | Path,
    config: ModuleMemConfig,
    settings: Settings | None = None,
    curated_llm_factory: Any = None,
    llm_factory: Any = None,
    scratch_root: str | Path | None = None,
) -> dict[str, Any]:
    for arm in config.arms:
        if arm not in MODULEMEM_ARMS:
            raise ModuleMemError(f"unknown arm {arm!r}; valid: {', '.join(MODULEMEM_ARMS)}")
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
    created_scratch = scratch_root is None
    scratch = Path(scratch_root) if scratch_root else Path(tempfile.mkdtemp(prefix="modulemem-"))
    results: list[dict[str, Any]] = []
    packs: list[dict[str, Any]] = []
    write_side: list[dict[str, Any]] = []
    lags: list[float] = []
    try:
        for arm in config.arms:
            for repeat in range(config.repeats):
                answerer, judge = factory(repeat)
                for module in modules:
                    with deterministic_ids(f"modulemem:{arm}:r{repeat}:{module.module_id}"):
                        rows, pack_row, ws, lag = _run_module_arm(
                            module,
                            arm=arm,
                            repeat=repeat,
                            config=config,
                            base=base,
                            answerer=answerer,
                            judge=judge,
                            data_dir=scratch / arm / f"{module.module_id}-r{repeat}",
                            cache_dir=out_path / "llm_cache",
                            usage=tracker,
                            curated_llm_factory=curated_llm_factory,
                        )
                    results.extend(rows)
                    if pack_row is not None:
                        packs.append(pack_row)
                    if ws is not None:
                        write_side.append(ws)
                    lags.extend(lag)
    finally:
        if created_scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    summary = _summarize(results, packs, write_side, lags, config, tracker)
    (out_path / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results), encoding="utf-8"
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
    data_dir: Path,
    cache_dir: Path,
    usage: LLMUsageTracker,
    curated_llm_factory: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None, list[float]]:
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

    rows: list[dict[str, Any]] = []
    for probe in module.probes:
        if service is not None:
            package = service.build_context(
                session_id=session_id,
                task=XMUSE_TASK,
                budget=800,
                retrieval_query=probe.question,
                include_global_core=False,
            )
            evidence = _evidence_items(build_source_evidence(package, schema_version="v2"))
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
    return rows, pack_row, ws, lags


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
