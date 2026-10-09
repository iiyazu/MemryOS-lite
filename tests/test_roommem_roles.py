"""RoomMem per-role model specs and the new write-side metrics (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from memoryos_eval.roommem import (
    CuratedMemoryView,
    FakeJudge,
    GoldMemorySource,
    RoomMemConfigError,
    build_llm_factory,
    conflict_flag_stats,
    llm_spec_label,
    load_rooms,
    match_curated_to_gold,
    resolve_split,
    score_write_side,
    settings_for_llm_spec,
)
from memoryos_lite.config import Settings

ROOMS = Path(__file__).resolve().parents[1] / "benchmarks" / "roommem" / "rooms"


def _base() -> Settings:
    return Settings(
        memoryos_llm_provider="deepseek",
        deepseek_api_key="sk-test",
        opencode_api_key="oc-test",
    )


def test_llm_spec_switches_provider_model_and_wire() -> None:
    judge = settings_for_llm_spec(_base(), "opencode:glm-5.3-flash@chat")
    curator = settings_for_llm_spec(_base(), "opencode:muse-spark-1.2-contributor@responses")

    assert (judge.resolved_llm_provider, judge.chat_model, judge.chat_wire_api) == (
        "opencode",
        "glm-5.3-flash",
        "chat",
    )
    assert llm_spec_label(curator) == "opencode:muse-spark-1.2-contributor@responses"
    assert llm_spec_label(settings_for_llm_spec(_base(), None)) == "deepseek:deepseek-v4-flash"


@pytest.mark.parametrize(
    "spec",
    ["glm-5.3-flash", "anthropic:claude", "opencode:", "deepseek:deepseek-v4-flash@responses"],
)
def test_invalid_llm_specs_are_rejected(spec: str) -> None:
    with pytest.raises(RoomMemConfigError):
        settings_for_llm_spec(_base(), spec)


def test_answerer_and_judge_can_use_different_models(tmp_path) -> None:
    factory = build_llm_factory(
        out_dir=tmp_path,
        fake_llm=False,
        settings=_base(),
        answerer_llm="deepseek:deepseek-v4-flash",
        judge_llm="opencode:glm-5.3-flash@chat",
    )

    answerer, judge = factory(0)

    assert answerer._chat.model == "deepseek-v4-flash"  # type: ignore[attr-defined]
    assert judge._chat.model == "glm-5.3-flash"  # type: ignore[attr-defined]


def test_trap_split_rooms_load_and_mention_old_values_after_the_change() -> None:
    rooms = load_rooms(ROOMS, room_ids=resolve_split("trap"))

    assert [room.room_id for room in rooms] == ["rm13", "rm14", "rm15", "rm16"]
    for room in rooms:
        superseded = [memory for memory in room.gold_memories if memory.superseded_by]
        assert superseded, room.room_id
        assert any(probe.must_not_contain for probe in room.probes), room.room_id


def _view(view_id: str, topic_key: str, statement: str, message_id: str, quote: str):
    return CuratedMemoryView(
        id=view_id,
        kind="decision",
        topic_key=topic_key,
        statement=statement,
        sources=[GoldMemorySource(message_id=message_id, quote=quote)],
    )


def test_chain_key_consistency_counts_matched_supersede_chains() -> None:
    room = load_rooms(ROOMS, room_ids=["rm13"])[0]
    consistent = [
        _view("c1", "billing.db", "Billing runs on MySQL 8.", "m02", "MySQL 8"),
        _view("c2", "Billing.DB", "Billing runs on PostgreSQL 16.", "m04", "PostgreSQL 16"),
    ]
    split = [
        _view("c1", "billing.db", "Billing runs on MySQL 8.", "m02", "MySQL 8"),
        _view("c2", "billing.database_engine", "Billing on PostgreSQL 16.", "m04", "PostgreSQL 16"),
    ]

    good, _ = score_write_side(room, consistent, FakeJudge())
    bad, _ = score_write_side(room, split, FakeJudge())

    assert (good["chain_pairs"], good["chain_key_consistent"]) == (1, 1)
    assert (bad["chain_pairs"], bad["chain_key_consistent"]) == (1, 0)


def test_conflict_flags_classify_pairs_by_gold_topic() -> None:
    room = load_rooms(ROOMS, room_ids=["rm13"])[0]
    views = [
        # Same gold topic (billing.database) under two curated keys: a real conflict.
        _view("c1", "billing.db", "Billing runs on MySQL 8.", "m02", "MySQL 8"),
        _view("c2", "billing.engine", "Billing runs on PostgreSQL 16.", "m04", "PostgreSQL 16"),
        # A different gold topic.
        _view("c3", "billing.invoice_day", "Invoices go out on the 1st.", "m07", "on the 1st"),
    ]
    matched = {
        match.gold_id: next(v for v in views if v.id == match.curated_id)
        for match in match_curated_to_gold(views, room.gold_memories)
    }
    vectors = {
        "Billing runs on MySQL 8.": [1.0, 0.0],
        "Billing runs on PostgreSQL 16.": [0.95, 0.31],
        "Invoices go out on the 1st.": [0.6, 0.8],
    }

    stats = conflict_flag_stats(
        room, views, matched, lambda texts: [vectors[text] for text in texts], thresholds=(0.9,)
    )

    assert stats["pairs"] == {"same_topic": 1, "different_topic": 2, "unknown": 0}
    assert stats["flagged"]["0.90"] == {"same_topic": 1, "different_topic": 0, "unknown": 0}
