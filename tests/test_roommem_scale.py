"""RoomMem scale features: full-context arm, merged projects, shared delivery (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from memoryos_eval.memory.source_evidence import build_source_evidence
from memoryos_eval.roommem import (
    XMUSE_ACTIVITY_DOC_PREFIX,
    XMUSE_MEMORY_DOC_PREFIX,
    _build_shared_memory_project,
    _evidence_items,
    full_context_evidence,
    load_rooms,
    run_roommem,
)

ROOMS = Path(__file__).resolve().parents[1] / "benchmarks" / "roommem" / "rooms"


def _rows(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(out.glob("**/results.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_full_context_evidence_is_the_whole_project_transcript_in_order() -> None:
    rooms = load_rooms(ROOMS, room_ids=["rm01", "rm02"])

    evidence = full_context_evidence(rooms)

    assert len(evidence) == sum(len(room.messages) for room in rooms)
    assert [item.rank for item in evidence] == list(range(1, len(evidence) + 1))
    assert evidence[0].document_id == f"{XMUSE_ACTIVITY_DOC_PREFIX}rm01.m01"
    assert evidence[-1].document_id == f"{XMUSE_ACTIVITY_DOC_PREFIX}rm02.{rooms[1].messages[-1].id}"
    assert rooms[1].messages[-1].text in evidence[-1].text


def test_merged_project_runs_full_context_against_every_room(tmp_path) -> None:
    rooms = load_rooms(ROOMS, room_ids=["rm01", "rm05"])  # atlas and beacon

    summary = run_roommem(
        rooms,
        out_dir=tmp_path / "out",
        arms=["full_context"],
        fake_llm=True,
        merge_project="all",
        scratch_root=tmp_path / "scratch",
    )

    assert summary["run"]["merge_project"] == "all"
    rows = _rows(tmp_path / "out")
    total = sum(len(room.messages) for room in rooms)
    assert rows and all(len(row["evidence"]) == total for row in rows)
    # The answer's own sources are always present in the full transcript.
    assert all(row["source_hit"] for row in rows)


def test_shared_project_delivers_other_rooms_project_memories(tmp_path) -> None:
    rooms = [
        room.model_copy(update={"project": "all"})
        for room in load_rooms(ROOMS, room_ids=["rm01", "rm05"])
    ]
    rm05 = rooms[1]
    shared_gold = next(memory for memory in rm05.gold_memories if memory.scope == "project")
    room_gold = next(memory for memory in rm05.gold_memories if memory.scope == "room")

    project = _build_shared_memory_project(
        arm="oracle",
        project="all",
        rooms=rooms,
        repeat=0,
        scratch_dir=tmp_path,
        embedding="none",
        curated_source=None,
    )

    def documents(session_id: str, query: str) -> set[str]:
        package = project.service.build_context(
            session_id=session_id,
            task="recall",
            budget=4000,
            retrieval_query=query,
            include_global_core=False,
        )
        envelope = build_source_evidence(package, schema_version="v2")
        return {
            item.document_id
            for item in _evidence_items(envelope)
            if item.document_id and item.document_id.startswith(XMUSE_MEMORY_DOC_PREFIX)
        }

    new_room = project.new_room_sessions["rm01"]
    seen = documents(new_room, shared_gold.statement)
    assert f"{XMUSE_MEMORY_DOC_PREFIX}rm05.{shared_gold.id}" in seen
    # Room-scope memories of another room never cross over.
    assert f"{XMUSE_MEMORY_DOC_PREFIX}rm05.{room_gold.id}" not in documents(
        project.sessions["rm01"], room_gold.statement
    )
    assert {view.id for view in project.views["rm05"]} >= {f"rm05.{shared_gold.id}"}
