"""ModuleMem: does a resume pack bring a restarted module owner back up to speed?

Each ``benchmarks/modulemem/modules/mmNN.json`` is one module's activity stream
(owner messages, review objections, failing gate logs, contract revisions) with
gold contracts, decisions and lessons. For every arm the stream is replayed
into a module-scoped MemoryOS session, then the owner "restarts" and answers the
module's probes from that arm's context:

``pack``
    The real path: the curator runs incrementally (full windows, and an
    immediate flush on every gate failure or review objection), its memories
    are delivered back as approved candidate documents (as xmuse would for
    module-scoped memories), contract revisions as activity documents, and the
    owner gets ``module_pack/v1``. Contract pointers are expanded to the
    contract text, as the owner can open ``.xmuse/contracts/``.
``oracle_pack``
    Same pack, built from the gold decisions and lessons (upper bound).
``recent``
    Only the last ``RECENT_ACTIVITIES`` activities (what a compacted session keeps).
``retrieval``
    xmuse-style recall: build-context top-8 over the module's raw activity documents.
``full_history``
    Every activity of the module in the context window.

Scoring: the judge labels each answer (correct/stale/missing/wrong) against the
current gold; probes are grouped by what they ask about (contract, decision,
lesson). The ``pack`` arm also reports write-side matching against gold,
lesson occurrence accuracy, pack size, and the curator's gate-failure-to-lesson
latency from ``curator_memory_written`` traces.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.curator import Curator, CuratorLLM, build_curator_llm
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.module_pack import estimate_tokens
from memoryos_lite.roommem import (
    XMUSE_ACTIVITY_DOC_PREFIX,
    XMUSE_MEMORY_DOC_PREFIX,
    XMUSE_MESSAGE_ID_PREFIX,
    XMUSE_TASK,
    CuratedMemoryView,
    DiskCachedCuratorLLM,
    EvidenceItem,
    FakeCuratorLLM,
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
    SessionScope,
    deterministic_ids,
)
from memoryos_lite.source_evidence import build_source_evidence

MODULEMEM_ARMS: tuple[str, ...] = ("pack", "oracle_pack", "recent", "retrieval", "full_history")
MODULEMEM_SPLITS: dict[str, tuple[str, ...]] = {
    "dev": ("mm01", "mm02", "mm03", "mm04"),
    "test": ("mm05", "mm06", "mm07", "mm08"),
}
RECENT_ACTIVITIES = 8
FLUSH_ACTIVITY_TYPES = ("gate_failure", "review_objection")
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


# ---------------------------------------------------------------------------
# Replay into MemoryOS
# ---------------------------------------------------------------------------


def _external_id(activity: ModuleActivity) -> str:
    return f"{XMUSE_MESSAGE_ID_PREFIX}{activity.id}"


def _archive_id(module: Module) -> str:
    return f"xmuse-module-{module.module_id}"


def _ingest_document(
    service: MemoryOSService,
    module: Module,
    *,
    document_id: str,
    text: str,
    metadata: dict[str, Any],
    source_id: str,
) -> None:
    service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id=document_id,
            title=document_id,
            content=text,
            source_refs=[ArchiveSourceRefPayload(source_type="document", source_id=source_id)],
            identity=ArchiveIdentityArchive(kind="archive", archive_id=_archive_id(module)),
            metadata=metadata,
        )
    )


@dataclass
class _Replay:
    service: MemoryOSService
    session_id: str
    message_ids: dict[str, str]
    curator_counts: dict[str, int] = field(default_factory=dict)
    curator_seconds: list[float] = field(default_factory=list)


def _replay(
    module: Module,
    *,
    service: MemoryOSService,
    curator: Curator | None,
) -> _Replay:
    session = service.create_session(
        f"modulemem {module.module_id}", scope=SessionScope(type="module", id=module.module_id)
    )
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
    replay = _Replay(service=service, session_id=session.id, message_ids={})
    counts = {
        "windows": 0,
        "added": 0,
        "superseded": 0,
        "noop": 0,
        "stale": 0,
        "rejected_grounding": 0,
        "rejected_schema": 0,
        "llm_errors": 0,
    }
    for seq, activity in enumerate(module.activities, start=1):
        participant = participants.get(activity.speaker)
        metadata: dict[str, Any] = {
            "activity_type": activity.type,
            "module_id": module.module_id,
            "activity_seq": seq,
            "participant_id": activity.speaker,
            "speaker_name": participant.name if participant else activity.speaker,
        }
        if activity.type == "contract_revision":
            metadata["contract_id"] = activity.contract_id
            metadata["contract_version"] = activity.contract_version
        response = service.ingest(
            session.id,
            MessageCreate(
                role=Role.USER if participant and participant.kind == "human" else Role.ASSISTANT,
                content=activity.text,
                external_id=_external_id(activity),
                metadata=metadata,
            ),
        )
        replay.message_ids[activity.id] = response.message.id
        # xmuse's activity outbox: every activity becomes an archive document.
        _ingest_document(
            service,
            module,
            document_id=f"{XMUSE_ACTIVITY_DOC_PREFIX}{activity.id}",
            text=activity.text,
            metadata={key: value for key, value in metadata.items() if key != "speaker_name"},
            source_id=f"{XMUSE_ACTIVITY_DOC_PREFIX}{activity.id}",
        )
        if curator is not None:
            started = time.perf_counter()
            result = curator.run_session(session.id, force=activity.type in FLUSH_ACTIVITY_TYPES)
            if result.windows:
                replay.curator_seconds.append(time.perf_counter() - started)
            for key in counts:
                counts[key] += int(getattr(result, key, 0) or 0)
    if curator is not None:
        result = curator.run_session(session.id, force=True)
        for key in counts:
            counts[key] += int(getattr(result, key, 0) or 0)
    replay.curator_counts = counts
    return replay


def _deliver_memories(
    replay: _Replay,
    module: Module,
    memories: Sequence[dict[str, Any]],
) -> None:
    """Approved module memories come back as candidate documents (xmuse delivery)."""

    for memory in memories:
        document_id = f"{XMUSE_MEMORY_DOC_PREFIX}{memory['id']}"
        _ingest_document(
            replay.service,
            module,
            document_id=document_id,
            text=memory["statement"],
            metadata={
                "memory_kind": memory["kind"],
                "topic_key": memory["topic_key"],
                "version": memory["version"],
                "occurrences": memory["occurrences"],
                "source_activity_ids": memory["source_activity_ids"],
            },
            source_id=document_id,
        )


def _curated_memories(replay: _Replay) -> list[dict[str, Any]]:
    reverse = {mid: aid for aid, mid in replay.message_ids.items()}
    rows = replay.service.store.list_curated_memories(replay.session_id, limit=64)
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "topic_key": row.topic_key,
            "statement": row.statement,
            "version": row.version,
            "occurrences": row.occurrences,
            "status": row.status,
            "source_activity_ids": sorted(
                {reverse[s["message_id"]] for s in row.sources if s["message_id"] in reverse}
            ),
            "sources": [
                {"activity_id": reverse.get(s["message_id"], ""), "quote": s["quote"]}
                for s in row.sources
            ],
        }
        for row in rows
        if row.kind in {"decision", "fact", "lesson"}
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


def _item(rank: int, item_id: str, layer: str, text: str, document_id: str | None) -> EvidenceItem:
    return EvidenceItem(
        rank=rank,
        item_id=item_id,
        layer=layer,
        text=text,
        estimated_tokens=estimate_tokens(text),
        document_id=document_id,
        source_refs=(),
    )


def _activity_text(module: Module, activity: ModuleActivity) -> str:
    speaker = next(
        (p.name for p in module.participants if p.id == activity.speaker), activity.speaker
    )
    return f"({activity.type}) {speaker}: {activity.text}"


def pack_evidence(module: Module, pack: dict[str, Any]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    sections = pack["sections"]
    for contract in sections["contracts"]:
        activity_id = contract["document_id"].removeprefix(XMUSE_ACTIVITY_DOC_PREFIX)
        activity = module.activity(activity_id)
        body = activity.text if activity is not None else contract["summary"]
        items.append(
            _item(
                len(items) + 1,
                contract["document_id"],
                "contract",
                f"Current contract {contract['contract_id']} v{contract['version']}:\n{body}",
                contract["document_id"],
            )
        )
    for lesson in sections["lessons"]:
        note = (
            f" (failed {lesson['occurrences']} times)" if lesson.get("occurrences", 1) > 1 else ""
        )
        conflict = (
            " [possible conflict with another memory]"
            if lesson.get("possible_conflict_with")
            else ""
        )
        items.append(
            _item(
                len(items) + 1,
                lesson["document_id"],
                "lesson",
                f"Lesson{note}: {lesson['text']}{conflict}",
                lesson["document_id"],
            )
        )
    for decision in sections["decisions"]:
        conflict = (
            " [possible conflict with another memory]"
            if decision.get("possible_conflict_with")
            else ""
        )
        items.append(
            _item(
                len(items) + 1,
                decision["document_id"],
                "decision",
                f"Decision: {decision['text']}{conflict}",
                decision["document_id"],
            )
        )
    return items


def _activities_evidence(
    module: Module, activities: Sequence[ModuleActivity]
) -> list[EvidenceItem]:
    return [
        _item(
            rank,
            activity.id,
            "activity",
            _activity_text(module, activity),
            f"{XMUSE_ACTIVITY_DOC_PREFIX}{activity.id}",
        )
        for rank, activity in enumerate(activities, start=1)
    ]


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
    # Over-counting (a restatement counted as a new failure) is the risk of asking the
    # curator to re-add repeated lessons, so it is reported next to the exact count.
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
        return FakeCuratorLLM()
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
    replay: _Replay | None = None
    if arm in {"pack", "oracle_pack", "retrieval"}:
        service_settings = _room_settings(
            data_dir, embedding=config.embedding, kernel_external=False
        )
        curator: Curator | None = None
        if arm == "pack":
            service_settings = service_settings.model_copy(
                update={
                    "memoryos_curator_enabled": True,
                    "memoryos_curator_window_messages": config.curator_window,
                    "memoryos_curator_consolidation": "deterministic",
                    # Windows close when full or on a gate/review flush, never by idle time.
                    "memoryos_curator_idle_flush_s": 1e9,
                }
            )
        service = MemoryOSService(settings=service_settings)
        if arm == "pack":
            curator = Curator(
                store=service.store,
                settings=service_settings,
                llm=_curator_llm(config, base, repeat, cache_dir, usage, curated_llm_factory),
            )
        replay = _replay(module, service=service, curator=curator)

    pack_row: dict[str, Any] | None = None
    ws: dict[str, Any] | None = None
    lags: list[float] = []
    evidence: list[EvidenceItem] = []
    if arm in {"pack", "oracle_pack"}:
        assert replay is not None
        memories = _curated_memories(replay) if arm == "pack" else _gold_memories(module)
        _deliver_memories(replay, module, memories)
        pack = replay.service.build_module_pack(replay.session_id, budget=config.pack_budget)
        evidence = pack_evidence(module, pack)
        pack_row = {
            "arm": arm,
            "module": module.module_id,
            "repeat": repeat,
            "pack": pack,
            "memories": memories,
            "curator_counts": replay.curator_counts,
        }
        if arm == "pack":
            ws = {"module": module.module_id, "repeat": repeat, **_write_side(module, memories)}
            ws["curator_counts"] = replay.curator_counts
            for event in replay.service.store.list_traces(replay.session_id):
                if event.event_type == "curator_memory_written" and "gate_failure" in (
                    event.payload.get("activity_types") or []
                ):
                    lag = event.payload.get("source_lag_s")
                    if isinstance(lag, (int, float)):
                        lags.append(float(lag))
    elif arm == "recent":
        evidence = _activities_evidence(module, module.activities[-RECENT_ACTIVITIES:])
    elif arm == "full_history":
        evidence = _activities_evidence(module, module.activities)

    rows: list[dict[str, Any]] = []
    for probe in module.probes:
        if arm == "retrieval":
            assert replay is not None
            package = replay.service.build_context(
                session_id=replay.session_id,
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
            "packs": len(rows),
            "mean_tokens": sum(p["pack"]["estimated_tokens"] for p in rows) / len(rows),
            "truncated": sum(1 for p in rows if p["pack"]["truncated"]),
            "mean_items": sum(sum(len(v) for v in p["pack"]["sections"].values()) for p in rows)
            / len(rows),
            "conflict_flags": sum(
                1
                for p in rows
                for section in ("lessons", "decisions")
                for item in p["pack"]["sections"][section]
                if item.get("possible_conflict_with")
            ),
        }
    totals: dict[str, int] = {}
    for ws in write_side:
        for key, value in ws.items():
            if isinstance(value, int) and not isinstance(value, bool) and key != "repeat":
                totals[key] = totals.get(key, 0) + value
    return {
        "run": {
            "arms": list(config.arms),
            "repeats": config.repeats,
            "embedding": config.embedding,
            "curator_llm": config.curator_llm,
            "answerer_llm": config.answerer_llm,
            "judge_llm": config.judge_llm,
            "pack_budget": config.pack_budget,
            "fake_llm": config.fake_llm,
        },
        "read_side": read,
        "packs": pack_stats,
        "write_side": totals,
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
    lines += ["", "## Packs", "", json.dumps(summary["packs"], ensure_ascii=False, indent=1), ""]
    lines += [
        "## Curator write side (pack arm)",
        "",
        json.dumps(summary["write_side"], ensure_ascii=False, indent=1),
        "",
    ]
    lines += [
        "Gate failure to lesson available (curator commit lag, offline replay): "
        + json.dumps(summary["gate_to_lesson_lag_s"]),
        "",
        "Limitations: the dataset is LLM-authored (Muse Spark 1.3) and checked by rules, not by a "
        "human; the replay is offline, so lag is curator processing time, not wall-clock in a live "
        "Workroom; the oracle pack delivers gold memories as if a perfect curator ran.",
    ]
    return "\n".join(lines) + "\n"
