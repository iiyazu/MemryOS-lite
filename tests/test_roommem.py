"""Behavioural tests for the RoomMem evaluation harness.

Small inline rooms plus deterministic fakes keep these tests offline: ``rm90``
(atlas) carries a supersession, ``rm91``/``rm92`` (beacon) carry new-room
probes and the project/user-scope memories that must be delivered across
rooms, and ``rm93`` (cobalt) carries a long message for the evidence dump.
"""

from __future__ import annotations

import copy
import json

import pytest
from typer.testing import CliRunner

from memoryos_eval.cli import app
from memoryos_lite.roommem import (
    LIMITATIONS_ZH,
    SPLIT_PRESETS,
    XMUSE_ACTIVITY_DOC_PREFIX,
    XMUSE_MEMORY_DOC_PREFIX,
    ChatAnswerer,
    ChatJudge,
    CuratedMemoryView,
    DiskCachedChatClient,
    DiskCachedCuratorLLM,
    EvidenceItem,
    FakeAnswerer,
    FakeCuratorLLM,
    FakeJudge,
    GoldMemorySource,
    LLMUsageTracker,
    RoomMemConfigError,
    RoomMemDataError,
    _activity_dataset_message_id,
    _evidence_presence,
    load_rooms,
    match_curated_to_gold,
    oracle_curated_memories,
    register_curated_source,
    resolve_split,
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


RM92 = {
    "room_id": "rm92",
    "title": "inline second beacon room",
    "language": "zh",
    "project": "beacon",
    "participants": [
        {"id": "u1", "kind": "human", "name": "Qiu"},
        {"id": "a1", "kind": "agent", "name": "Beacon"},
    ],
    "messages": [
        {
            "id": "m01",
            "speaker": "u1",
            "text": "补充约定：依赖管理使用 uv 和锁文件，不引入 poetry。",
        },
        {
            "id": "m02",
            "speaker": "a1",
            "text": "评审时间改为周五下午四点，使用 code-review checklist。",
        },
        {"id": "m03", "speaker": "u1", "text": "缓存层最初计划换取 Memcached，方案代号 m-cache。"},
        {
            "id": "m04",
            "speaker": "a1",
            "text": "后来团队推翻了上面那个方案，决定继续沿用既有的键值服务。",
        },
        {"id": "m05", "speaker": "u1", "text": "灯塔二号房间已记录以上约定。"},
        {"id": "m06", "speaker": "a1", "text": "以上记录同步给项目组。"},
    ],
    "gold_memories": [
        {
            "id": "g1",
            "kind": "rule",
            "scope": "project",
            "topic_key": "tooling.lockfiles",
            "statement": "项目依赖管理使用 uv 和锁文件。",
            "sources": [{"message_id": "m01", "quote": "依赖管理使用 uv 和锁文件"}],
        },
        {
            "id": "g2",
            "kind": "preference",
            "scope": "user",
            "topic_key": "workflow.review_time",
            "statement": "代码评审时间改为周五下午四点。",
            "sources": [{"message_id": "m02", "quote": "评审时间改为周五下午四点"}],
        },
        {
            "id": "g4",
            "kind": "decision",
            "scope": "room",
            "topic_key": "cache.layer",
            "statement": "缓存层继续沿用既有的键值服务。",
            "sources": [{"message_id": "m04", "quote": "继续沿用既有的键值服务"}],
        },
        {
            "id": "g3",
            "kind": "decision",
            "scope": "room",
            "topic_key": "cache.layer",
            "statement": "缓存层最初计划换取 Memcached。",
            "sources": [{"message_id": "m03", "quote": "最初计划换取 Memcached"}],
            "superseded_by": "g4",
        },
    ],
    "probes": [
        {
            "id": "p1",
            "question": "缓存层最初计划换取什么？",
            "asked_in": "same_room",
            "answer_memory_ids": ["g4"],
            "must_contain": ["Memcached"],
            "must_not_contain": ["Redis"],
        },
        {
            "id": "p2",
            "question": "依赖管理有什么约定？",
            "asked_in": "same_room",
            "answer_memory_ids": ["g1"],
            "must_contain": ["uv"],
            "must_not_contain": ["npm"],
        },
        {
            "id": "p3",
            "question": "评审时间有什么约定？",
            "asked_in": "new_room_same_project",
            "answer_memory_ids": ["g2"],
            "must_contain": ["周五"],
            "must_not_contain": ["周一"],
        },
    ],
}

RM93_MESSAGE = (
    "钴蓝计划的风险登记表记录着当前所有已知风险：供应链延迟、第三方接口不稳定、"
    "评审排期冲突、跨团队依赖未对齐、数据迁移窗口过窄，以及发布回滚演练尚未完成。"
    "登记表每次评审后更新一次，由项目负责人确认新增条目并标注负责人和缓解措施。"
    "登记表同时保留历史条目，任何关闭的风险都必须写明关闭原因，并在下一次周会上"
    "向项目组说明处理结果与遗留监控项。未按期更新的条目会在周会上被指出，负责人"
    "需要当场补充进度或者说明阻塞原因。登记表的维护状态会直接影响发布评审是否"
    "允许进入下一阶段，周会纪要会链接到对应条目。"
)

RM93 = {
    "room_id": "rm93",
    "title": "inline cobalt room with a long message",
    "language": "zh",
    "project": "cobalt",
    "participants": [
        {"id": "u1", "kind": "human", "name": "He"},
        {"id": "a1", "kind": "agent", "name": "Cobalt"},
    ],
    "messages": [
        {"id": "m01", "speaker": "u1", "text": RM93_MESSAGE},
        {"id": "m02", "speaker": "a1", "text": "以上风险条目已同步到周会纪要。"},
    ],
    "gold_memories": [
        {
            "id": "g1",
            "kind": "fact",
            "scope": "room",
            "topic_key": "risk.register",
            "statement": "钴蓝计划的风险登记表记录了所有已知风险。",
            "sources": [{"message_id": "m01", "quote": "风险登记表记录着当前所有已知风险"}],
        }
    ],
    "probes": [
        {
            "id": "p1",
            "question": "钴蓝计划的风险登记表记录了什么？",
            "asked_in": "same_room",
            "answer_memory_ids": ["g1"],
            "must_contain": ["风险"],
            "must_not_contain": ["Zebra"],
        }
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


@pytest.fixture()
def project_rooms_dir(tmp_path):
    """rm90 (atlas), rm91+rm92 (beacon) and rm93 (cobalt) for cross-project checks."""

    directory = tmp_path / "project-rooms"
    directory.mkdir()
    for payload in (RM90, RM91, RM92, RM93):
        _write_room(directory, payload)
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
    assert "raw" not in summary["write_side"]


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
    assert write_side["rates"]["stale_active_rate"] == 0.0
    assert write_side["rates"]["precision"] == 1.0
    assert write_side["rates"]["recall"] == 1.0
    assert write_side["rates"]["unmatched_rate"] == 0.0
    assert write_side["rates"]["noise_rate"] == 0.0
    assert write_side["rates"]["duplicate_rate"] == 0.0
    assert write_side["rates"]["kind_agreement"] == 1.0
    assert write_side["rates"]["scope_agreement"] == 1.0


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
    # Noise is only what the judge labels noise among unmatched memories.
    assert metrics["rates"]["noise_rate"] == pytest.approx(1 / 5)
    assert metrics["rates"]["unmatched_rate"] == pytest.approx(3 / 5)
    # Both matched pairs are decision-vs-decision on room scope.
    assert metrics["rates"]["kind_agreement"] == 1.0
    assert metrics["rates"]["scope_agreement"] == 1.0
    restatement = metrics["noise_types"]["restatement"]
    assert restatement["messages"] == 1
    assert restatement["cited_as_source"] == 1
    assert restatement["in_unmatched_memory"] == 1
    instruction = metrics["noise_types"]["agent_instruction"]
    assert instruction["messages"] == 1
    assert instruction["cited_as_source"] == 1
    assert instruction["in_unmatched_memory"] == 1


def test_match_by_source_overlap_only_with_statement_tiebreak(rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm90"])[0]
    gold = room.gold_memories
    curated = [
        CuratedMemoryView(
            id="v-kind",
            kind="preference",
            statement="曾计划用 SQLite 作为开发阶段存储。",
            sources=[GoldMemorySource(message_id="m01", quote="决定用 SQLite 作为开发阶段的存储")],
        ),
        CuratedMemoryView(
            id="v-other",
            kind="fact",
            statement="无关的一句话。",
            sources=[GoldMemorySource(message_id="m01", quote="决定用 SQLite 作为开发阶段的存储")],
        ),
    ]

    matches = match_curated_to_gold(curated, gold)

    # Kind is not a matching gate: the preference-shaped view still matches
    # the decision gold; the tie on source overlap is broken by the statement
    # token overlap, so the statement-equal view wins.
    assert [match.curated_id for match in matches] == ["v-kind"]
    assert matches[0].gold_id == "g2"
    assert matches[0].statement_overlap > 0


def test_match_stale_active_view_counts_only_when_matched(rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm90"])[0]
    curated = [
        CuratedMemoryView(
            id="c1",
            kind="decision",
            statement="开发阶段最终使用 Postgres 作为主要存储。",
            sources=[GoldMemorySource(message_id="m03", quote="改用 Postgres 作为主要存储")],
        ),
        CuratedMemoryView(
            id="c2",
            kind="decision",
            statement="曾计划用 SQLite 作为开发阶段存储。",
            sources=[GoldMemorySource(message_id="m01", quote="决定用 SQLite 作为开发阶段的存储")],
        ),
    ]

    metrics, _ = score_write_side(room, curated, FakeJudge())

    # g2 is superseded in the dataset; its matched view is still active, which
    # fails the supersede rate and shows up in the stale-active rate.
    assert metrics["rates"]["supersede_rate"] == 0.0
    assert metrics["rates"]["stale_active_rate"] == 1.0


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


def test_fake_curator_llm_adds_one_grounded_memory_per_human_message():
    fake = FakeCuratorLLM()
    user = (
        "Active memories (reuse a topic_key from this list for the same subject):\n(none)\n\n"
        "Earlier context (read-only; you may quote these messages):\n(none)\n\n"
        "Messages to curate:\n"
        "[msg_1] Lin, human (message): 我们决定用 SQLite 作为开发阶段的存储。\n"
        "[msg_2] Atlas, agent (message): 收到。\n"
        "[msg_3] Mo, human (message): Hi\n"
    )

    payload = fake.complete_json(system="sys", user=user)

    memories = payload["memories"]
    assert len(memories) == 1
    memory = memories[0]
    assert memory["kind"] == "fact"
    assert memory["topic_key"] == "roommem.msg_1"
    assert memory["statement"] == "我们决定用 SQLite 作为开发阶段的存储。"
    assert memory["sources"] == [
        {"activity_id": "msg_1", "quote": "我们决定用 SQLite 作为开发阶段的存储。"}
    ]
    assert fake.complete_json(system="sys", user=user) == payload


class _CountingCuratorLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        return {"memories": []}


def test_curator_llm_cache_reuses_and_separates_repeats(tmp_path):
    inner = _CountingCuratorLLM()
    cache_dir = tmp_path / "cache"

    first = DiskCachedCuratorLLM(inner, model="curator-model", cache_dir=cache_dir, repeat=0)
    assert first.complete_json(system="s", user="u") == {"memories": []}
    assert first.complete_json(system="s", user="u") == {"memories": []}
    assert inner.calls == 1

    second_inner = _CountingCuratorLLM()
    fresh = DiskCachedCuratorLLM(second_inner, model="curator-model", cache_dir=cache_dir, repeat=0)
    assert fresh.complete_json(system="s", user="u") == {"memories": []}
    assert second_inner.calls == 0  # a new run with the same key reuses the entry

    repeat_one = DiskCachedCuratorLLM(inner, model="curator-model", cache_dir=cache_dir, repeat=1)
    assert repeat_one.complete_json(system="s", user="u") == {"memories": []}
    assert inner.calls == 2

    other_model = DiskCachedCuratorLLM(inner, model="other-model", cache_dir=cache_dir, repeat=0)
    assert other_model.complete_json(system="s", user="u") == {"memories": []}
    assert inner.calls == 3
    assert repeat_one.cache_key(system="s", user="u") != first.cache_key(system="s", user="u")

    cached = json.loads(next(cache_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert cached["role"] == "curator"


# ---------------------------------------------------------------------------
# Curated arm and CLI
# ---------------------------------------------------------------------------


def test_curated_arm_with_registered_source_cross_scope(tmp_path, rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm91"])[0]
    views = oracle_curated_memories(room)
    counts = {
        "windows": 1,
        "added": 3,
        "superseded": 0,
        "noop": 0,
        "rejected_grounding": 1,
        "rejected_schema": 2,
        "llm_errors": 0,
    }
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
    assert write_side["curator_rooms"] == {"rm91": counts}
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


def test_default_curated_source_runs_real_curator_with_fake_llm(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    out_dir = tmp_path / "out"
    summary = run_roommem(
        rooms,
        out_dir=out_dir,
        arms=["curated"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch",
    )

    rows = _by_probe(_read_results(out_dir))
    assert set(rows) == {("rm90", "p1"), ("rm91", "p1"), ("rm91", "p2"), ("rm91", "p3")}
    assert rows[("rm90", "p1")]["hit"] is True
    assert rows[("rm91", "p1")]["hit"] is True
    # Fake curator facts map to xmuse scope "room", so new-room probes stay empty.
    assert rows[("rm91", "p2")]["asked_in"] == "new_room_same_project"
    assert rows[("rm91", "p2")]["hit"] is False

    write_side = summary["write_side"]["curated"]
    assert write_side["memories"] == 5
    assert write_side["matched"] == 5
    assert write_side["rates"]["precision"] == 1.0
    assert write_side["rates"]["recall"] == 1.0
    assert write_side["rates"]["unmatched_rate"] == 0.0
    assert write_side["rates"]["noise_rate"] == 0.0
    assert write_side["rates"]["supersede_rate"] == 0.0
    assert write_side["rates"]["stale_active_rate"] == 1.0
    assert write_side["rates"]["kind_agreement"] == pytest.approx(1 / 5)
    assert write_side["rates"]["scope_agreement"] == pytest.approx(3 / 5)

    counters = write_side["curator_counts"]
    assert counters == {
        "windows": 2,
        "added": 5,
        "superseded": 0,
        "noop": 0,
        "rejected_grounding": 0,
        "rejected_schema": 0,
        "llm_errors": 0,
    }
    assert write_side["curator_rooms"]["rm90"]["added"] == 2
    assert write_side["curator_rooms"]["rm91"]["added"] == 3

    on_disk = json.loads((out_dir / "write_side.json").read_text(encoding="utf-8"))
    assert on_disk["curated"]["curator_rooms"]["rm91"]["windows"] == 1
    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "### Curator counters" in summary_md


def test_curator_window_controls_curator_windowing(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    summary = run_roommem(
        rooms,
        out_dir=tmp_path / "out",
        arms=["curated"],
        fake_llm=True,
        curator_window=2,
        scratch_root=tmp_path / "scratch",
    )

    counters = summary["write_side"]["curated"]["curator_counts"]
    assert counters["windows"] == 5  # rm90: 4 messages -> 2 windows; rm91: 6 -> 3
    assert counters["added"] == 5
    assert summary["run"]["curator_window"] == 2


def test_curated_arm_llm_calls_go_through_disk_cache(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    inner = _CountingCuratorLLM()
    out_dir = tmp_path / "out"
    shared_answerer = _answerer_factory(FakeAnswerer)

    def run(scratch, repeats=1):
        return run_roommem(
            rooms,
            out_dir=out_dir,
            arms=["curated"],
            llm_factory=shared_answerer,
            curated_llm_factory=lambda settings: inner,
            repeats=repeats,
            scratch_root=scratch,
        )

    run(tmp_path / "scratch-1")
    assert inner.calls == 2  # one window per inline room
    cache_files = sorted((out_dir / "llm_cache").glob("*.json"))
    assert len(cache_files) == 2
    roles = {json.loads(path.read_text(encoding="utf-8"))["role"] for path in cache_files}
    assert roles == {"curator"}

    # Store ids are deterministic per (arm, repeat, room), so a replay renders
    # identical curator prompts and is served from the cache.
    run(tmp_path / "scratch-2")
    assert inner.calls == 2
    assert len(list((out_dir / "llm_cache").glob("*.json"))) == 2

    run(tmp_path / "scratch-3", repeats=2)
    assert inner.calls == 4  # repeat 1 curates in its own cache namespace
    assert len(list((out_dir / "llm_cache").glob("*.json"))) == 4


# ---------------------------------------------------------------------------
# raw_project arm, audit artifacts and usage accounting
# ---------------------------------------------------------------------------


class _UsageStubClient:
    """Chat stub that reports provider usage on every call."""

    def __init__(self, usage=None):
        self.last_usage = dict(
            usage or {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        )

    @property
    def model(self):
        return "usage-stub"

    def complete(self, *, system, user):
        return "ok"


class _UsageCuratorLLM:
    def __init__(self):
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}

    def complete_json(self, system, user):
        return {"memories": []}


def _doc_ids(row):
    return {item["document_id"] for item in row["evidence"] if item["document_id"]}


def test_activity_dataset_message_id_is_room_aware():
    assert _activity_dataset_message_id("m01", "rm91") == "m01"
    assert _activity_dataset_message_id("rm91.m01", "rm91") == "m01"
    assert _activity_dataset_message_id("rm92.m01", "rm91") is None
    assert _activity_dataset_message_id("rm9.m01", "rm91") is None


def test_evidence_presence_ignores_other_room_documents():
    def item(document_id):
        return EvidenceItem(
            rank=1,
            item_id=document_id,
            layer="archival",
            text="t",
            estimated_tokens=1,
            document_id=document_id,
            source_refs=(),
        )

    presence, memory_ids = _evidence_presence(
        [
            item(f"{XMUSE_ACTIVITY_DOC_PREFIX}rm91.m01"),
            item(f"{XMUSE_ACTIVITY_DOC_PREFIX}rm92.m02"),
        ],
        {"m01": "memoryos-1"},
        room_id="rm91",
    )
    assert presence == {"m01"}
    assert memory_ids == set()

    bare_presence, _ = _evidence_presence(
        [item(f"{XMUSE_ACTIVITY_DOC_PREFIX}m03")],
        {"m03": "memoryos-3"},
        room_id="rm91",
    )
    assert bare_presence == {"m03"}


def test_raw_project_visibility_and_isolation(tmp_path, project_rooms_dir):
    rooms = load_rooms(project_rooms_dir)
    out_dir = tmp_path / "out"
    summary = run_roommem(
        rooms,
        out_dir=out_dir,
        arms=["raw_project"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch",
    )
    by_probe = _by_probe(_read_results(out_dir))

    # same_room: own room plus the other beacon room.
    p2 = by_probe[("rm92", "p2")]
    assert f"{XMUSE_ACTIVITY_DOC_PREFIX}rm92.m01" in _doc_ids(p2)
    assert f"{XMUSE_ACTIVITY_DOC_PREFIX}rm91.m01" in _doc_ids(p2)
    assert p2["source_hit"] is True

    # new_room: all rooms of the project, including the room's own archive.
    p3 = by_probe[("rm92", "p3")]
    assert f"{XMUSE_ACTIVITY_DOC_PREFIX}rm92.m02" in _doc_ids(p3)
    assert f"{XMUSE_ACTIVITY_DOC_PREFIX}rm91.m03" in _doc_ids(p3)
    assert p3["source_hit"] is True

    # rm91's new-room probe sees the other beacon room's raw messages.
    rm91_new = by_probe[("rm91", "p2")]
    assert f"{XMUSE_ACTIVITY_DOC_PREFIX}rm92.m01" in _doc_ids(rm91_new)
    assert rm91_new["source_hit"] is True

    # Stale/source-hit follow the shared rule on whatever evidence was retrieved:
    # stale = superseded source (m03) present without its successor (m04).
    _assert_stale_rule(by_probe[("rm92", "p1")], room_id="rm92")

    # Never another project's rooms.
    beacon_probes = [
        ("rm91", "p1"),
        ("rm91", "p2"),
        ("rm91", "p3"),
        ("rm92", "p1"),
        ("rm92", "p2"),
        ("rm92", "p3"),
    ]
    beacon_evidence = []
    for key in beacon_probes:
        row = by_probe[key]
        ids = _doc_ids(row)
        assert not any(doc.startswith(f"{XMUSE_ACTIVITY_DOC_PREFIX}rm90.") for doc in ids)
        assert not any(doc.startswith(f"{XMUSE_ACTIVITY_DOC_PREFIX}rm93.") for doc in ids)
        beacon_evidence.append(row["evidence"])
    dumped = json.dumps(beacon_evidence, ensure_ascii=False)
    assert "SQLite" not in dumped
    assert "钴蓝计划" not in dumped

    rm90_docs = _doc_ids(by_probe[("rm90", "p1")])
    assert rm90_docs
    assert all(doc.startswith(f"{XMUSE_ACTIVITY_DOC_PREFIX}rm90.") for doc in rm90_docs)
    rm93_docs = _doc_ids(by_probe[("rm93", "p1")])
    assert rm93_docs
    assert all(doc.startswith(f"{XMUSE_ACTIVITY_DOC_PREFIX}rm93.") for doc in rm93_docs)

    new_room = summary["read_side"]["raw_project"]["new_room_same_project"]
    assert new_room["source_hit_at_8"]["mean"] == 1.0
    assert new_room["hit_at_8"]["mean"] == 1.0


def test_raw_project_stale_parity_with_raw_arm(tmp_path, project_rooms_dir):
    rooms = load_rooms(project_rooms_dir, room_ids=["rm92"])
    out_dir = tmp_path / "out"
    run_roommem(
        rooms,
        out_dir=out_dir,
        arms=["raw", "raw_project"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch",
    )
    rows = _read_results(out_dir)

    def row_for(arm):
        return next(row for row in rows if row["arm"] == arm and row["probe"] == "p1")

    # Both arms apply the same stale/source-hit rule to their own evidence.
    for arm in ("raw", "raw_project"):
        _assert_stale_rule(row_for(arm), room_id="rm92")


def _assert_stale_rule(row, *, room_id):
    # A message is visible either as its archive document or, through the recall
    # layer, as the session message itself (item text equals the message text).
    texts = {message["id"]: message["text"] for message in {"rm92": RM92}[room_id]["messages"]}

    def present(message_id):
        doc_ids = _doc_ids(row)
        return (
            f"{XMUSE_ACTIVITY_DOC_PREFIX}{room_id}.{message_id}" in doc_ids
            or f"{XMUSE_ACTIVITY_DOC_PREFIX}{message_id}" in doc_ids
            or any(item["text"] == texts[message_id] for item in row["evidence"])
        )

    old_present, new_present = present("m03"), present("m04")
    assert old_present or new_present
    assert row["stale"] is (old_present and not new_present)
    assert row["source_hit"] is new_present


def test_results_jsonl_keeps_full_evidence_and_exact_answer(tmp_path, project_rooms_dir):
    rooms = load_rooms(project_rooms_dir, room_ids=["rm93"])
    out_dir = tmp_path / "out"
    run_roommem(
        rooms,
        out_dir=out_dir,
        arms=["raw"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch",
    )
    row = _by_probe(_read_results(out_dir))[("rm93", "p1")]

    assert len(RM93_MESSAGE) > 200
    assert any(item["text"] == RM93_MESSAGE for item in row["evidence"])
    assert row["answer"] == row["evidence"][0]["text"]


def test_memories_jsonl_dump_maps_sources_and_labels(tmp_path, rooms_dir):
    room = load_rooms(rooms_dir, room_ids=["rm91"])[0]
    extra = CuratedMemoryView(
        id="c-extra",
        kind="fact",
        topic_key="roommem.extra",
        statement="项目组每周同步一次进展。",
        sources=[GoldMemorySource(message_id="m02", quote="好的，依赖管理确定用 uv。")],
    )
    register_curated_source(
        "inline-audit", lambda: _FakeSource(oracle_curated_memories(room) + [extra])
    )
    out_dir = tmp_path / "out"
    try:
        run_roommem(
            [room],
            out_dir=out_dir,
            arms=["curated"],
            fake_llm=True,
            curated_source_name="inline-audit",
            scratch_root=tmp_path / "scratch",
        )
    finally:
        unregister_curated_source("inline-audit")

    memories_path = out_dir / "memories.jsonl"
    rows = [
        json.loads(line)
        for line in memories_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {row["arm"] for row in rows} == {"curated"}
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {"g1", "g2", "g3", "c-extra"}

    g1 = by_id["g1"]
    assert g1["room"] == "rm91"
    assert g1["repeat"] == 0
    assert g1["kind"] == "rule"
    assert g1["topic_key"] == "tooling.dependencies"
    assert g1["statement"] == "项目统一使用 uv 管理依赖。"
    assert g1["status"] == "active"
    assert g1["supersedes_id"] is None
    assert g1["sources"] == [{"message_id": "m01", "quote": "统一用 uv 管理依赖"}]
    assert g1["matched_gold"] == "g1"
    assert g1["judge"] is None

    extra_row = by_id["c-extra"]
    assert extra_row["matched_gold"] is None
    assert extra_row["judge"] == "legit_unannotated"
    assert extra_row["sources"] == [{"message_id": "m02", "quote": "好的，依赖管理确定用 uv。"}]


def test_usage_tracker_records_provider_calls_and_cache_hits(tmp_path):
    tracker = LLMUsageTracker()
    client = DiskCachedChatClient(
        _UsageStubClient(), role="answerer", cache_dir=tmp_path / "cache", repeat=0, usage=tracker
    )
    assert client.complete(system="s", user="u") == "ok"
    assert client.complete(system="s", user="u") == "ok"

    role = tracker.aggregate()["roles"]["answerer"]
    assert role["calls"] == 2
    assert role["cached"] == 1
    assert role["tokens_in"] == 7
    assert role["tokens_out"] == 3
    assert set(role["latency_s"]) == {"mean", "p50", "p95", "total"}
    assert role["latency_s"]["mean"] == role["latency_s"]["p50"] == role["latency_s"]["p95"]

    openai_tracker = LLMUsageTracker()
    openai_client = DiskCachedChatClient(
        _UsageStubClient({"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}),
        role="judge",
        cache_dir=tmp_path / "cache",
        repeat=0,
        usage=openai_tracker,
    )
    openai_client.complete(system="s", user="u")
    judge = openai_tracker.aggregate()["roles"]["judge"]
    assert judge["tokens_in"] == 2
    assert judge["tokens_out"] == 1
    assert judge["cached"] == 0


def test_run_roommem_reports_usage_and_estimated_cost(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    tracker = LLMUsageTracker()
    out_dir = tmp_path / "out"

    def factory(repeat):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        answerer = ChatAnswerer(
            DiskCachedChatClient(
                _UsageStubClient(usage),
                role="answerer",
                cache_dir=out_dir / "llm_cache",
                repeat=repeat,
                usage=tracker,
            )
        )
        judge = ChatJudge(
            DiskCachedChatClient(
                _UsageStubClient(usage),
                role="judge",
                cache_dir=out_dir / "llm_cache",
                repeat=repeat,
                usage=tracker,
            )
        )
        return answerer, judge

    summary = run_roommem(
        rooms,
        out_dir=out_dir,
        arms=["oracle"],
        llm_factory=factory,
        usage=tracker,
        price_in_per_mtok=1.0,
        price_out_per_mtok=2.0,
        scratch_root=tmp_path / "scratch",
    )

    usage = summary["usage"]
    assert usage["roles"]["answerer"]["calls"] == 4
    assert usage["roles"]["answerer"]["tokens_in"] == 40
    assert usage["roles"]["judge"]["calls"] == 4
    cost = usage["estimated_cost"]
    assert cost["price_in_per_mtok"] == 1.0
    assert cost["price_out_per_mtok"] == 2.0
    assert cost["tokens_in"] == 80
    assert cost["tokens_out"] == 40
    assert cost["cost"] == pytest.approx((80 * 1.0 + 40 * 2.0) / 1_000_000)

    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "## LLM usage" in summary_md
    assert "Estimated cost" in summary_md

    plain = run_roommem(
        rooms,
        out_dir=tmp_path / "plain",
        arms=["oracle"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch-plain",
    )
    assert "usage" not in plain


def test_curated_usage_reports_tokens_per_100_messages(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir)
    tracker = LLMUsageTracker()
    out_dir = tmp_path / "out"
    summary = run_roommem(
        rooms,
        out_dir=out_dir,
        arms=["curated"],
        llm_factory=_answerer_factory(FakeAnswerer),
        curated_llm_factory=lambda settings: _UsageCuratorLLM(),
        usage=tracker,
        scratch_root=tmp_path / "scratch",
    )

    usage = summary["usage"]
    assert usage["roles"]["curator"]["calls"] == 2
    assert usage["roles"]["curator"]["cached"] == 0
    curator = usage["curator"]
    assert curator["messages"] == 10
    assert curator["windows"] == 2
    assert curator["tokens_per_100_messages"] == pytest.approx(2400.0)
    assert curator["seconds_per_window"] is not None
    assert curator["seconds_per_window"] > 0

    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "Curator:" in summary_md


def test_cli_roommem_fake_llm_writes_reports(tmp_path, rooms_dir):
    out_dir = tmp_path / "cli-out"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "roommem",
            "--data",
            str(rooms_dir),
            "--arm",
            "raw",
            "--arm",
            "raw_project",
            "--arm",
            "oracle",
            "--arm",
            "curated",
            "--fake-llm",
            "--curator-window",
            "2",
            "--price-in-per-mtok",
            "1.0",
            "--price-out-per-mtok",
            "2.0",
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "results.jsonl").exists()
    assert (out_dir / "memories.jsonl").exists()
    assert (out_dir / "write_side.json").exists()
    assert (out_dir / "summary.json").exists()
    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "## Read side" in summary_md
    assert "### Curator counters" in summary_md
    assert LIMITATIONS_ZH in summary_md
    rows = _read_results(out_dir)
    assert len(rows) == 16
    assert {row["arm"] for row in rows} == {"raw", "raw_project", "oracle", "curated"}
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    counters = summary["write_side"]["curated"]["curator_counts"]
    assert counters["windows"] == 5
    assert counters["added"] == 5


def test_cli_roommem_unknown_curated_source_fails(tmp_path, rooms_dir):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "roommem",
            "--data",
            str(rooms_dir),
            "--arm",
            "curated",
            "--curated-source",
            "nope",
            "--fake-llm",
            "--out",
            str(tmp_path / "cli-out"),
        ],
    )

    assert result.exit_code == 1
    assert "no curated memory source is registered" in result.output


def test_split_presets_resolve_to_room_ids():
    assert SPLIT_PRESETS["dev"] == ("rm01", "rm02", "rm03", "rm04", "rm05", "rm06")
    assert SPLIT_PRESETS["test"] == ("rm07", "rm08", "rm09", "rm10", "rm11", "rm12")
    assert resolve_split("dev") == list(SPLIT_PRESETS["dev"])
    assert resolve_split(" Test ") == list(SPLIT_PRESETS["test"])
    with pytest.raises(RoomMemConfigError, match="unknown split"):
        resolve_split("bogus")


def test_cli_roommem_split_errors(tmp_path, rooms_dir):
    runner = CliRunner()

    both = runner.invoke(
        app,
        ["roommem", "--data", str(rooms_dir), "--split", "dev", "--rooms", "rm01"],
    )
    assert both.exit_code == 1
    assert "mutually exclusive" in both.output

    unknown = runner.invoke(
        app,
        ["roommem", "--data", str(rooms_dir), "--split", "bogus"],
    )
    assert unknown.exit_code == 1
    assert "unknown split" in unknown.output


def test_curated_evidence_modes_share_one_curation(tmp_path, rooms_dir):
    rooms = load_rooms(rooms_dir, room_ids=["rm91"])
    summary = run_roommem(
        rooms,
        out_dir=tmp_path / "out",
        arms=["curated"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch",
        curated_evidence=("plain", "demote", "agentic"),
    )

    assert {"curated", "curated+demote", "curated+agentic"} <= set(summary["read_side"])
    assert summary["run"]["curated_evidence"] == ["plain", "demote", "agentic"]
    rows = _read_results(tmp_path / "out")
    agentic = [row for row in rows if row["arm"] == "curated+agentic"]
    assert agentic and all(row["ask"]["retrievals"] >= 1 for row in agentic)
    probes = {(row["room"], row["probe"]) for row in rows if row["arm"] == "curated"}
    assert probes == {(row["room"], row["probe"]) for row in agentic}
    oracle = run_roommem(
        rooms,
        out_dir=tmp_path / "oracle",
        arms=["oracle"],
        fake_llm=True,
        scratch_root=tmp_path / "scratch-oracle",
        curated_evidence=("plain", "demote", "agentic"),
    )
    assert {"oracle", "oracle+demote", "oracle+agentic"} <= set(oracle["read_side"])
    with pytest.raises(RoomMemConfigError, match="unknown curated evidence mode"):
        run_roommem(
            rooms,
            out_dir=tmp_path / "bad",
            arms=["curated"],
            fake_llm=True,
            curated_evidence=("telepathy",),
        )
