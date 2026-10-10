"""Deterministic curator consolidation. All LLM calls use injectable fakes."""

from __future__ import annotations

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.curator import Curator
from memoryos_lite.curator.curate import normalize_topic_key
from memoryos_lite.curator.prompt import CURATE_ROOM_SYSTEM_PROMPT
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role
from memoryos_lite.store import create_store


class ScriptedLLM:
    def __init__(self) -> None:
        self.responses: list[dict[str, object]] = []
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        self.calls.append((system, user))
        return self.responses.pop(0) if self.responses else {"memories": []}


def _service(tmp_path, llm, **overrides) -> tuple[MemoryOSService, Curator]:
    settings = Settings(
        data_dir=tmp_path / "memoryos",
        **{"memoryos_curator_window_messages": 1, **overrides},
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=llm)
    return MemoryOSService(store=store, settings=settings), curator


def _ingest(service: MemoryOSService, session_id: str, content: str, **metadata) -> str:
    return service.ingest(
        session_id, MessageCreate(role=Role.USER, content=content, metadata=metadata)
    ).message.id


def _op(message_id: str, statement: str, *, topic_key: str, kind: str = "fact"):
    return {
        "kind": kind,
        "topic_key": topic_key,
        "statement": statement,
        "sources": [{"activity_id": message_id, "quote": statement}],
    }


def test_newer_value_supersedes_by_version(tmp_path):
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("deterministic")
    lisbon = "The launch city is Lisbon."
    lisbon_id = _ingest(service, session.id, lisbon)
    llm.responses = [{"memories": [_op(lisbon_id, lisbon, topic_key="project.launch_city")]}]
    curator.run_session(session.id)
    old = service.store.list_active_curated_memories(session.id)[0]

    porto = "The launch city is now Porto."
    porto_id = _ingest(service, session.id, porto)
    llm.responses = [{"memories": [_op(porto_id, porto, topic_key="Project.Launch City")]}]
    result = curator.run_session(session.id)

    assert (result.superseded, result.added, result.stale) == (1, 0, 0)
    active = service.store.list_active_curated_memories(session.id)
    assert [row.statement for row in active] == [porto]
    assert active[0].topic_key == "project.launch_city"
    assert active[0].supersedes_id == old.id
    assert active[0].version > old.version
    assert service.store.get_curated_memory(old.id).status == "superseded"
    assert llm.calls[0][0] == CURATE_ROOM_SYSTEM_PROMPT


def test_out_of_order_older_value_is_stored_already_superseded(tmp_path):
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("out-of-order")
    current = "Deploys go out on Thursdays."
    current_id = _ingest(service, session.id, current, activity_seq=50)
    llm.responses = [{"memories": [_op(current_id, current, topic_key="ops.deploy_day")]}]
    curator.run_session(session.id)

    # Delivered later but older in the consumer's activity order.
    older = "Deploys go out on Mondays."
    older_id = _ingest(service, session.id, older, activity_seq=12)
    llm.responses = [{"memories": [_op(older_id, older, topic_key="ops.deploy_day")]}]
    result = curator.run_session(session.id)

    assert (result.stale, result.superseded, result.added) == (1, 0, 0)
    active = service.store.list_active_curated_memories(session.id)
    assert [(row.statement, row.version) for row in active] == [(current, 50)]
    # Stale proposals are counted, not stored: only the newest value remains.
    rows = service.store.list_curated_memories(session.id)
    assert [row.statement for row in rows] == [current]


def test_one_window_keeps_only_the_newest_value_per_topic(tmp_path):
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm, memoryos_curator_window_messages=2)
    session = service.create_session("window-newest")
    old_text = "We host on Heroku for now."
    new_text = "We moved hosting to Fly.io."
    old_id = _ingest(service, session.id, old_text)
    new_id = _ingest(service, session.id, new_text)
    # The LLM lists the newer value first; order of proposals does not matter.
    llm.responses = [
        {
            "memories": [
                _op(new_id, new_text, topic_key="infra.hosting"),
                _op(old_id, old_text, topic_key="infra.hosting"),
            ]
        }
    ]

    result = curator.run_session(session.id, force=True)

    assert (result.added, result.noop) == (1, 1)
    assert [row.statement for row in service.store.list_active_curated_memories(session.id)] == [
        new_text
    ]


def test_repeated_lesson_accumulates_occurrences_instead_of_replacing(tmp_path):
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("lessons")
    first = "Token refresh raced without the lock; take it before refreshing."
    first_id = _ingest(service, session.id, first)
    llm.responses = [
        {"memories": [_op(first_id, first, topic_key="auth.refresh_lock", kind="lesson")]}
    ]
    curator.run_session(session.id)

    second = "Review noted: refresh again ran without taking the lock."
    second_id = _ingest(service, session.id, second)
    llm.responses = [
        {
            "memories": [
                # Re-citing an already counted source is not a new occurrence.
                _op(first_id, first, topic_key="auth.refresh_lock", kind="lesson"),
                _op(second_id, second, topic_key="auth.refresh_lock", kind="lesson"),
            ]
        }
    ]
    result = curator.run_session(session.id)

    assert (result.superseded, result.noop) == (1, 1)
    active = service.store.list_active_curated_memories(session.id)
    assert len(active) == 1
    lesson = active[0]
    assert lesson.occurrences == 2
    assert [source["message_id"] for source in lesson.sources] == [first_id, second_id]
    assert lesson.statement == second

    # A later window that only re-cites known sources changes nothing.
    third_id = _ingest(service, session.id, "ok, noted")
    llm.responses = [
        {"memories": [_op(first_id, first, topic_key="auth.refresh_lock", kind="lesson")]}
    ]
    assert curator.run_session(session.id).noop == 1
    assert service.store.list_active_curated_memories(session.id)[0].id == lesson.id
    assert third_id


def test_written_memories_are_traced_with_activity_types_and_source_lag(tmp_path):
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("trace")
    text = "Gate failed: migrations must run before seeding."
    message_id = _ingest(service, session.id, text, activity_type="gate_failure")
    llm.responses = [
        {
            "assignments": [
                {
                    "activity_id": message_id,
                    "lesson": "db.seed",
                    "quote": "migrations must run before seeding",
                }
            ],
            "lessons": [{"topic_key": "db.seed", "statement": text}],
        }
    ]

    curator.run_session(session.id)

    events = [
        event
        for event in service.store.list_traces(session.id)
        if event.event_type == "curator_memory_written"
    ]
    assert len(events) == 1
    payload = events[0].payload
    assert payload["kind"] == "lesson"
    assert payload["activity_types"] == ["gate_failure"]
    assert isinstance(payload["source_lag_s"], float) and payload["source_lag_s"] >= 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Project.Launch City", "project.launch_city"),
        ("  infra / hosting  ", "infra_hosting"),
        ("a..b__c", "a.b_c"),
        ("项目.发布 城市", "项目.发布_城市"),
        ("...", None),
    ],
)
def test_topic_keys_are_normalized(raw, expected):
    assert normalize_topic_key(raw) == expected
