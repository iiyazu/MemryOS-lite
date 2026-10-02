"""Behavioural tests for the RoomMem evaluation harness.

Two tiny inline rooms plus deterministic fakes keep these tests offline:
``rm90`` carries a supersession, ``rm91`` carries new-room probes and the
project/user-scope memories that must be delivered across rooms.
"""

from __future__ import annotations

import copy
import json

import pytest
from typer.testing import CliRunner

from memoryos_lite.cli import app
from memoryos_lite.roommem import (
    LIMITATIONS_ZH,
    XMUSE_MEMORY_DOC_PREFIX,
    ChatAnswerer,
    ChatJudge,
    CuratedMemoryView,
    DiskCachedChatClient,
    EvidenceItem,
    FakeJudge,
    GoldMemorySource,
    RoomMemDataError,
    load_rooms,
    oracle_curated_memories,
    register_curated_source,
    run_roommem,
    score_write_side,
    unregister_curated_source,
)

RM90 = {
    "room_id": "rm90",
    "title": "inline supersession room",
    "language": "zh",
    "project": "atlas",
    "participants": [
        {"id": "u1", "kind": "human", "name": "Lin"},
        {"id": "a1", "kind": "agent", "name": "Atlas"},
    ],
    "messages": [
        {"id": "m01", "speaker": "u1", "text": "我们决定用 SQLite 作为开发阶段的存储。"},
        {"id": "m02", "speaker": "a1", "text": "收到，SQLite 已记录到项目档案。"},
        {"id": "m03", "speaker": "u1", "text": "后来我们改用 Postgres 作为主要存储。"},
        {"id": "m04", "speaker": "a1", "text": "明白，存储方案已更新为 Postgres。"},
    ],
    "gold_memories": [
        {
            "id": "g1",
            "kind": "decision",
            "scope": "room",
            "topic_key": "storage.database",
            "statement": "开发阶段最终使用 Postgres 作为主要存储。",
            "sources": [{"message_id": "m03", "quote": "改用 Postgres 作为主要存储"}],
        },
        {
            "id": "g2",
            "kind": "decision",
            "scope": "room",
            "topic_key": "storage.database",
            "statement": "曾计划用 SQLite 作为开发阶段存储。",
            "sources": [{"message_id": "m01", "quote": "决定用 SQLite 作为开发阶段的存储"}],
            "superseded_by": "g1",
        },
    ],
    "noise": [
        {"message_id": "m02", "type": "agent_instruction", "note": "流程确认，不是长期记忆"},
        {"message_id": "m04", "type": "restatement", "note": "重复确认"},
    ],
    "probes": [
        {
            "id": "p1",
            "question": "开发阶段最终使用哪种存储？",
            "asked_in": "same_room",
            "answer_memory_ids": ["g1"],
            "must_contain": ["Postgres"],
            "must_not_contain": ["SQLite"],
        }
    ],
}

RM91 = {
    "room_id": "rm91",
    "title": "inline cross-room room",
    "language": "zh",
    "project": "beacon",
    "participants": [
        {"id": "u1", "kind": "human", "name": "Mo"},
        {"id": "a1", "kind": "agent", "name": "Beacon"},
    ],
    "messages": [
        {"id": "m01", "speaker": "u1", "text": "我们项目统一用 uv 管理依赖。"},
        {"id": "m02", "speaker": "a1", "text": "好的，依赖管理确定用 uv。"},
        {"id": "m03", "speaker": "u1", "text": "我习惯在周五下午做代码评审。"},
        {"id": "m04", "speaker": "a1", "text": "记下了，周五下午评审。"},
        {"id": "m05", "speaker": "u1", "text": "项目代号是 Zebra。"},
        {"id": "m06", "speaker": "a1", "text": "代号 Zebra，收到。"},
    ],
    "gold_memories": [
        {
            "id": "g1",
            "kind": "rule",
            "scope": "project",
            "topic_key": "tooling.dependencies",
            "statement": "项目统一使用 uv 管理依赖。",
            "sources": [{"message_id": "m01", "quote": "统一用 uv 管理依赖"}],
        },
        {
            "id": "g2",
            "kind": "preference",
            "scope": "user",
            "topic_key": "workflow.review_window",
            "statement": "习惯在周五下午做代码评审。",
            "sources": [{"message_id": "m03", "quote": "习惯在周五下午做代码评审"}],
        },
        {
            "id": "g3",
            "kind": "fact",
            "scope": "room",
            "topic_key": "project.codename",
            "statement": "项目代号是 Zebra。",
            "sources": [{"message_id": "m05", "quote": "项目代号是 Zebra。"}],
        },
    ],
    "noise": [
        {"message_id": "m02", "type": "agent_instruction", "note": "流程确认"},
        {"message_id": "m04", "type": "restatement", "note": "重复确认"},
        {"message_id": "m06", "type": "restatement", "note": "重复确认"},
    ],
    "probes": [
        {
            "id": "p1",
            "question": "项目代号是什么？",
            "asked_in": "same_room",
            "answer_memory_ids": ["g3"],
            "must_contain": ["Zebra"],
            "must_not_contain": ["Cobalt"],
        },
        {
            "id": "p2",
            "question": "依赖管理有什么约定？",
            "asked_in": "new_room_same_project",
            "answer_memory_ids": ["g1"],
            "must_contain": ["uv"],
            "must_not_contain": ["poetry"],
        },
        {
            "id": "p3",
            "question": "代码评审有什么偏好？",
            "asked_in": "new_room_same_project",
            "answer_memory_ids": ["g2"],
            "must_contain": ["周五"],
            "must_not_contain": ["周一"],
        },
    ],
}


def _write_room(directory, payload):
    path = directory / f"{payload['room_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def rooms_dir(tmp_path):
    directory = tmp_path / "rooms"
    directory.mkdir()
    _write_room(directory, RM90)
    _write_room(directory, RM91)
    return directory


def _read_results(out_dir):
    text = (out_dir / "results.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _by_probe(rows):
    return {(row["room"], row["probe"]): row for row in rows}


class _GroundedAnswerer:
    """Returns the gold statement plus a citation when the memory is present."""

    def __init__(self, needle, statement):
        self._needle = needle
        self._statement = statement

    def answer(self, *, question, evidence):
        for item in evidence:
            if self._needle in item.text:
                return f"{self._statement} [{item.rank}]"
        return "NO_EVIDENCE"


class _KeywordAnswerer:
    def __init__(self, text):
        self._text = text

    def answer(self, *, question, evidence):
        return self._text


def _answerer_factory(build):
    def factory(repeat):
        return build(), FakeJudge()

    return factory


class _CountingClient:
    def __init__(self):
        self.calls = 0

    @property
    def model(self):
        return "stub-model"

    def complete(self, *, system, user):
        self.calls += 1
        return f"reply-{self.calls}"


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def test_load_rooms_reads_inline_dataset(rooms_dir):
    rooms = load_rooms(rooms_dir)

    assert [room.room_id for room in rooms] == ["rm90", "rm91"]
    assert rooms[0].gold_memory("g2").superseded_by == "g1"
    assert rooms[1].has_new_room_probes() is True
    assert rooms[1].noise_message_ids() == frozenset({"m02", "m04", "m06"})


def test_load_rooms_filters_room_ids(rooms_dir):
    rooms = load_rooms(rooms_dir, room_ids=["rm91"])

    assert [room.room_id for room in rooms] == ["rm91"]


def test_load_rooms_rejects_unknown_room_id(rooms_dir):
    with pytest.raises(RoomMemDataError, match="unknown room ids: rm99"):
        load_rooms(rooms_dir, room_ids=["rm99"])


def test_load_room_rejects_quote_not_in_message(tmp_path):
    payload = copy.deepcopy(RM90)
    payload["gold_memories"][0]["sources"][0]["quote"] = "这句话不在消息里"
    _write_room(tmp_path, payload)

    with pytest.raises(RoomMemDataError, match="quote is not an exact substring"):
        load_rooms(tmp_path)


def test_load_room_rejects_unknown_speaker(tmp_path):
    payload = copy.deepcopy(RM90)
    payload["messages"][0]["speaker"] = "ghost"
    _write_room(tmp_path, payload)

    with pytest.raises(RoomMemDataError, match="is not a participant"):
        load_rooms(tmp_path)


def test_load_room_rejects_dangling_supersede(tmp_path):
    payload = copy.deepcopy(RM90)
    payload["gold_memories"][1]["superseded_by"] = "g99"
    _write_room(tmp_path, payload)

    with pytest.raises(RoomMemDataError, match="superseded_by 'g99' not found"):
        load_rooms(tmp_path)


def test_load_room_rejects_superseded_probe_answer(tmp_path):
    payload = copy.deepcopy(RM90)
    payload["probes"][0]["answer_memory_ids"] = ["g2"]
    _write_room(tmp_path, payload)

    with pytest.raises(RoomMemDataError, match="answer memory 'g2' is superseded"):
        load_rooms(tmp_path)


def test_load_room_rejects_new_room_probe_with_room_scope(tmp_path):
    payload = copy.deepcopy(RM91)
    payload["probes"][1]["answer_memory_ids"] = ["g3"]
    _write_room(tmp_path, payload)

    with pytest.raises(RoomMemDataError, match="only project/user scope allowed"):
        load_rooms(tmp_path)


def test_load_room_rejects_invalid_json(tmp_path):
    (tmp_path / "rm90.json").write_text("{ not json", encoding="utf-8")

    with pytest.raises(RoomMemDataError, match="invalid JSON"):
        load_rooms(tmp_path)


# ---------------------------------------------------------------------------
# Raw arm
# ---------------------------------------------------------------------------


def test_raw_arm_end_to_end_and_new_room_isolation(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    summary = run_roommem(
        rooms,
        out_dir=tmp_path / "out",
        arms=["raw"],
        fake_llm=True,
        heuristic_advisories=True,
        scratch_root=tmp_path / "scratch",
    )
    rows = _read_results(tmp_path / "out")
    by_probe = _by_probe(rows)

    same_room = by_probe[("rm90", "p1")]
    assert same_room["hit"] is True
    assert same_room["answer"] != "NO_EVIDENCE"
    assert same_room["evidence"]

    same_room_b = by_probe[("rm91", "p1")]
    assert same_room_b["hit"] is True

    new_room_rows = [row for row in rows if row["asked_in"] == "new_room_same_project"]
    assert len(new_room_rows) == 2
    for row in new_room_rows:
        assert row["hit"] is False
        assert row["source_hit"] is False
        assert row["evidence"] == []
        assert row["evidence_tokens"] == 0
        assert row["answer"] == "NO_EVIDENCE"
        assert row["judge"] == "missing"
        assert "SQLite" not in json.dumps(row["evidence"], ensure_ascii=False)

    read_side = summary["read_side"]["raw"]
    assert read_side["same_room"]["hit_at_8"]["mean"] == 1.0
    assert read_side["new_room_same_project"]["hit_at_8"]["mean"] == 0.0

    heuristic = summary["write_side"]["raw"]["heuristic"]
    assert heuristic["advisories"] >= 0
    assert "gold_match_rate" in heuristic["rates"]
    assert "noise_rate" in heuristic["rates"]


def test_substring_scoring_uses_probe_constraints(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir, room_ids=["rm91"])
    summary = run_roommem(
        rooms,
        out_dir=tmp_path / "out",
        arms=["raw"],
        llm_factory=_answerer_factory(lambda: _KeywordAnswerer("UV 周五 zebra。")),
        scratch_root=tmp_path / "scratch",
    )
    rows = _by_probe(_read_results(tmp_path / "out"))

    assert all(row["substring"] is True for row in rows.values())

    run_roommem(
        rooms,
        out_dir=tmp_path / "out-negative",
        arms=["raw"],
        llm_factory=_answerer_factory(lambda: _KeywordAnswerer("poetry only")),
        scratch_root=tmp_path / "scratch-negative",
    )
    rows_negative = _by_probe(_read_results(tmp_path / "out-negative"))

    assert all(row["substring"] is False for row in rows_negative.values())
    assert summary["read_side"]["raw"]["same_room"]["substring_pass"]["mean"] == 1.0


# ---------------------------------------------------------------------------
# Oracle arm
# ---------------------------------------------------------------------------


def test_oracle_arm_current_answer_excludes_superseded(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    summary = run_roommem(
        rooms,
        out_dir=tmp_path / "out",
        arms=["oracle"],
        llm_factory=_answerer_factory(
            lambda: _GroundedAnswerer(
                "改用 Postgres 作为主要存储",
                "开发阶段最终使用 Postgres 作为主要存储。",
            )
        ),
        scratch_root=tmp_path / "scratch",
    )
    rows = _by_probe(_read_results(tmp_path / "out"))

    supersede_row = rows[("rm90", "p1")]
    documents = {item["document_id"] for item in supersede_row["evidence"]}
    assert f"{XMUSE_MEMORY_DOC_PREFIX}g1" in documents
    assert f"{XMUSE_MEMORY_DOC_PREFIX}g2" not in documents
    assert supersede_row["hit"] is True
    assert supersede_row["stale"] is False
    assert supersede_row["judge"] == "correct"
    assert supersede_row["substring"] is True
    assert supersede_row["citation_correct"] == 1.0
    assert supersede_row["citations"][0]["correct"] is True

    cross_scope_rows = [rows[("rm91", "p2")], rows[("rm91", "p3")]]
    for row in cross_scope_rows:
        assert row["hit"] is True
        assert row["asked_in"] == "new_room_same_project"

    write_side = summary["write_side"]["oracle"]
    assert write_side["superseded_gold"] >= 1
    assert write_side["supersede_correct"] == write_side["superseded_gold"]
    assert write_side["rates"]["supersede_rate"] == 1.0
    assert write_side["rates"]["precision"] == 1.0
    assert write_side["rates"]["recall"] == 1.0
    assert write_side["rates"]["duplicate_rate"] == 0.0


# ---------------------------------------------------------------------------
# Write-side scoring
# ---------------------------------------------------------------------------


class _FakeSource:
    def __init__(self, views, counts=None):
        self._views = views
        self.last_counts = counts or {}

    def curate(self, service, session_id):
        return list(self._views)


def test_score_write_side_hand_made_curated_list(rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm90"])[0]
    curated = [
        CuratedMemoryView(
            id="c1",
            kind="decision",
            topic_key="storage.database",
            statement="开发阶段最终使用 Postgres 作为主要存储。",
            sources=[GoldMemorySource(message_id="m03", quote="改用 Postgres 作为主要存储")],
        ),
        CuratedMemoryView(
            id="c1-dup",
            kind="decision",
            topic_key="storage.database",
            statement="存储方案已更新为 Postgres。",
            sources=[GoldMemorySource(message_id="m03", quote="改用 Postgres 作为主要存储")],
        ),
        CuratedMemoryView(
            id="c2",
            kind="decision",
            topic_key="storage.database",
            statement="曾计划用 SQLite 作为开发阶段存储。",
            sources=[GoldMemorySource(message_id="m01", quote="决定用 SQLite 作为开发阶段的存储")],
            status="superseded",
        ),
        CuratedMemoryView(
            id="c3",
            kind="fact",
            topic_key="room.smalltalk",
            statement="团队确认过存储方案。",
            sources=[GoldMemorySource(message_id="m04", quote="存储方案已更新")],
        ),
        CuratedMemoryView(
            id="c4",
            kind="fact",
            topic_key="room.unsupported",
            statement="这是一条没有出处的记忆。",
            sources=[GoldMemorySource(message_id="m02", quote="这条引文不在消息里")],
        ),
    ]

    metrics, matched_by_gold = score_write_side(room, curated, FakeJudge())

    assert metrics["memories"] == 5
    assert metrics["gold"] == 2
    assert metrics["matched"] == 2
    assert matched_by_gold["g1"].id == "c1"
    assert matched_by_gold["g2"].id == "c2"
    assert metrics["unmatched"] == 3
    assert metrics["rates"]["precision"] == pytest.approx(2 / 5)
    assert metrics["rates"]["recall"] == pytest.approx(2 / 2)
    assert metrics["rates"]["supersede_rate"] == 1.0
    assert metrics["rates"]["duplicate_rate"] == pytest.approx(1 / 2)
    assert metrics["unmatched_judged"] == {"legit_unannotated": 2, "noise": 1}
    assert metrics["rates"]["noise_rate"] == pytest.approx(3 / 5)
    assert metrics["rates"]["primary_noise_rate"] == pytest.approx(2 / 5)
    restatement = metrics["noise_types"]["restatement"]
    assert restatement["messages"] == 1
    assert restatement["cited_as_source"] == 1
    assert restatement["in_unmatched_memory"] == 1
    instruction = metrics["noise_types"]["agent_instruction"]
    assert instruction["messages"] == 1
    assert instruction["cited_as_source"] == 1
    assert instruction["in_unmatched_memory"] == 1


# ---------------------------------------------------------------------------
# LLM roles, judge rules, and caching
# ---------------------------------------------------------------------------


def test_fake_judge_labels_and_missing_sentinel():
    judge = FakeJudge()
    current = ["开发阶段最终使用 Postgres 作为主要存储。"]
    superseded = ["曾计划用 SQLite 作为开发阶段存储。"]

    assert (
        judge.judge_answer(
            question="q",
            current_statements=current,
            superseded_statements=superseded,
            answer="NO_EVIDENCE",
        )
        == "missing"
    )
    assert (
        judge.judge_answer(
            question="q",
            current_statements=current,
            superseded_statements=superseded,
            answer="结论：开发阶段最终使用 Postgres 作为主要存储。",
        )
        == "correct"
    )
    assert (
        judge.judge_answer(
            question="q",
            current_statements=current,
            superseded_statements=superseded,
            answer="存储方案是 SQLite。曾计划用 SQLite 作为开发阶段存储。",
        )
        == "stale"
    )
    assert (
        judge.judge_answer(
            question="q",
            current_statements=current,
            superseded_statements=superseded,
            answer="我不确定。",
        )
        == "wrong"
    )


def test_llm_roles_with_stub_chat_client():
    class _StubChat:
        @property
        def model(self):
            return "stub"

        def complete(self, *, system, user):
            if "evaluation judge" in system:
                return 'prefix {"label": "STALE", "reason": "old value"}'
            return "  最终使用 Postgres  [2]  "

    answerer = ChatAnswerer(_StubChat())
    judge = ChatJudge(_StubChat())
    evidence = [
        EvidenceItem(
            rank=2,
            item_id="msg_1",
            layer="recall",
            text="storage evidence",
            estimated_tokens=2,
            document_id=None,
            source_refs=(),
        )
    ]

    assert answerer.answer(question="q", evidence=evidence) == "最终使用 Postgres  [2]"
    assert answerer.answer(question="q", evidence=[]) == "NO_EVIDENCE"
    assert (
        judge.judge_answer(
            question="q",
            current_statements=["x"],
            superseded_statements=["y"],
            answer="a",
        )
        == "stale"
    )
    assert (
        judge.judge_unmatched_memory(
            memory=CuratedMemoryView(
                id="c1",
                kind="fact",
                statement="s",
                sources=[GoldMemorySource(message_id="m01", quote="q")],
            ),
            message_texts={"m01": "q"},
        )
        == "noise"
    )


def test_disk_cache_reuses_responses_and_separates_repeats(tmp_path):
    inner = _CountingClient()
    cache_dir = tmp_path / "cache"

    first = DiskCachedChatClient(inner, role="answerer", cache_dir=cache_dir, repeat=0)
    assert first.complete(system="s", user="u") == "reply-1"
    assert first.complete(system="s", user="u") == "reply-1"
    assert inner.calls == 1

    same_key_new_instance = DiskCachedChatClient(
        _CountingClient(), role="answerer", cache_dir=cache_dir, repeat=0
    )
    assert same_key_new_instance.complete(system="s", user="u") == "reply-1"

    repeat_one = DiskCachedChatClient(inner, role="answerer", cache_dir=cache_dir, repeat=1)
    assert repeat_one.complete(system="s", user="u") == "reply-2"
    assert inner.calls == 2

    judge_role = DiskCachedChatClient(inner, role="judge", cache_dir=cache_dir, repeat=0)
    assert judge_role.complete(system="s", user="u") == "reply-3"
    assert inner.calls == 3

    assert len(list(cache_dir.glob("*.json"))) == 3


# ---------------------------------------------------------------------------
# Curated arm and CLI
# ---------------------------------------------------------------------------


def test_curated_arm_with_registered_source_cross_scope(tmp_path, rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm91"])[0]
    views = oracle_curated_memories(room)
    counts = {"grounding_rejects": 1, "schema_failures": 2}
    source = _FakeSource(views, counts=counts)
    register_curated_source("inline-source", lambda: source)
    try:
        summary = run_roommem(
            [room],
            out_dir=tmp_path / "out",
            arms=["curated"],
            fake_llm=True,
            curated_source_name="inline-source",
            scratch_root=tmp_path / "scratch",
        )
    finally:
        unregister_curated_source("inline-source")

    rows = _by_probe(_read_results(tmp_path / "out"))
    assert rows[("rm91", "p2")]["hit"] is True
    assert rows[("rm91", "p3")]["hit"] is True
    project_docs = {item["document_id"] for item in rows[("rm91", "p2")]["evidence"]}
    assert f"{XMUSE_MEMORY_DOC_PREFIX}g1" in project_docs

    write_side = summary["write_side"]["curated"]
    assert write_side["rates"]["precision"] == 1.0
    assert write_side["rates"]["recall"] == 1.0
    assert write_side["curator_counts"] == counts
    assert write_side["notes"]


def test_curated_arm_rejects_ungrounded_view(tmp_path, rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm91"])[0]
    bad_view = CuratedMemoryView(
        id="bad",
        kind="fact",
        statement="没有出处的记忆。",
        sources=[GoldMemorySource(message_id="m01", quote="不存在的引用")],
    )
    register_curated_source("inline-bad", lambda: _FakeSource([bad_view]))
    try:
        with pytest.raises(RoomMemDataError, match="quote is not an exact substring"):
            run_roommem(
                [room],
                out_dir=tmp_path / "out",
                arms=["curated"],
                fake_llm=True,
                curated_source_name="inline-bad",
                scratch_root=tmp_path / "scratch",
            )
    finally:
        unregister_curated_source("inline-bad")


def test_cli_roommem_fake_llm_writes_reports(tmp_path, rooms_dir):
    out_dir = tmp_path / "cli-out"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "eval",
            "roommem",
            "--data",
            str(rooms_dir),
            "--arm",
            "raw",
            "--arm",
            "oracle",
            "--fake-llm",
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "results.jsonl").exists()
    assert (out_dir / "write_side.json").exists()
    assert (out_dir / "summary.json").exists()
    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "## Read side" in summary_md
    assert LIMITATIONS_ZH in summary_md
    rows = _read_results(out_dir)
    assert len(rows) == 8
    assert {row["arm"] for row in rows} == {"raw", "oracle"}


def test_cli_roommem_curated_without_registered_source_fails(tmp_path, rooms_dir):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "eval",
            "roommem",
            "--data",
            str(rooms_dir),
            "--arm",
            "curated",
            "--fake-llm",
            "--out",
            str(tmp_path / "cli-out"),
        ],
    )

    assert result.exit_code == 1
    assert "no curated memory source is registered" in result.output
