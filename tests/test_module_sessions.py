"""Module-scoped sessions: activity metadata, lesson sources, gate log rendering."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.curator import Curator
from memoryos_lite.curator.prompt import GATE_LOG_HEAD_CHARS, render_message
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import (
    ActivityMetadataError,
    Message,
    MessageCreate,
    Role,
    SessionScope,
)
from memoryos_lite.store import create_store


class ScriptedLLM:
    def __init__(self) -> None:
        self.responses: list[dict[str, object]] = []
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        self.calls.append((system, user))
        return self.responses.pop(0) if self.responses else {"operations": []}


def _service(tmp_path, llm=None) -> tuple[MemoryOSService, Curator]:
    settings = Settings(
        data_dir=tmp_path / "memoryos",
        memoryos_curator_enabled=True,
        memoryos_curator_window_messages=1,
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=llm or ScriptedLLM())
    return MemoryOSService(store=store, settings=settings, curator=curator), curator


def _activity(seq: int, activity_type: str, **extra) -> dict[str, object]:
    return {"activity_type": activity_type, "module_id": "auth", "activity_seq": seq, **extra}


def _ingest(service, session_id, content, metadata, role=Role.ASSISTANT) -> str:
    return service.ingest(
        session_id, MessageCreate(role=role, content=content, metadata=metadata)
    ).message.id


def test_module_session_scope_round_trips_and_is_validated_on_ingest(tmp_path):
    service, _ = _service(tmp_path)
    session = service.create_session("auth", scope=SessionScope(type="module", id="auth"))
    assert service.store.get_session(session.id).scope == SessionScope(type="module", id="auth")

    _ingest(
        service, session.id, "Owner: refresh now takes the per-user lock.", _activity(1, "message")
    )
    _ingest(
        service,
        session.id,
        "auth-api v2: POST /login returns {token, refresh_token}.",
        _activity(2, "contract_revision", contract_id="auth-api", contract_version=2),
    )
    bad = [
        {"module_id": "auth", "activity_seq": 3},  # missing activity_type
        _activity(3, "message") | {"module_id": "billing"},  # wrong module
        _activity(3, "message") | {"activity_seq": "3"},  # non-integer seq
        _activity(3, "contract_revision", contract_id="auth-api"),  # no version
        _activity(3, "deploy"),  # unknown type
    ]
    for metadata in bad:
        with pytest.raises(ActivityMetadataError):
            _ingest(service, session.id, "Not accepted.", metadata)

    room = service.create_session("room")
    _ingest(service, room.id, "Plain room message.", {})
    with pytest.raises(ActivityMetadataError):
        _ingest(service, room.id, "Typo type.", {"activity_type": "gate-failure"})


def test_api_creates_module_sessions_and_rejects_bad_activity_metadata(tmp_path):
    service, _ = _service(tmp_path)
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        created = client.post(
            "/sessions", json={"title": "auth", "scope": {"type": "module", "id": "auth"}}
        )
        assert created.status_code == 200
        body = created.json()
        assert body["scope"] == {"type": "module", "id": "auth"}
        response = client.post(
            f"/sessions/{body['id']}/ingest",
            json={"role": "assistant", "content": "x", "metadata": {"activity_type": "message"}},
        )
        assert response.status_code == 422
        plain = client.post("/sessions", json={"title": "room"}).json()
        assert plain["scope"] is None
    finally:
        app.dependency_overrides.pop(get_service, None)


def test_module_lesson_occurrences_count_cited_review_and_gate_messages(tmp_path):
    llm = ScriptedLLM()
    settings = Settings(
        data_dir=tmp_path / "memoryos",
        memoryos_curator_enabled=True,
        memoryos_curator_window_messages=3,
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=llm)
    service = MemoryOSService(store=store, settings=settings, curator=curator)
    session = service.create_session("auth", scope=SessionScope(type="module", id="auth"))

    def lesson(*cited: tuple[str, str]) -> dict[str, object]:
        return {
            "op": "add",
            "kind": "lesson",
            "topic_key": "auth.refresh_lock",
            "statement": "Take the per-user lock before refreshing a token.",
            "sources": [{"message_id": mid, "quote": quote} for mid, quote in cited],
        }

    note = "Owner: I refresh tokens without a lock for now."
    gate = "FAILED test_concurrent_refresh - token written twice"
    note_id = _ingest(service, session.id, note, _activity(1, "message"))
    gate_id = _ingest(service, session.id, gate, _activity(2, "gate_failure"))
    # A plain message cited next to the gate failure is not an occurrence.
    llm.responses = [{"operations": [lesson((note_id, note), (gate_id, gate))]}]
    curator.run_session(session.id, force=True)
    assert service.store.list_active_curated_memories(session.id)[0].occurrences == 1

    review = "Objection: refresh still runs without the per-user lock."
    rerun = "FAILED test_parallel_refresh - token written twice again"
    review_id = _ingest(service, session.id, review, _activity(3, "review_objection"))
    rerun_id = _ingest(service, session.id, rerun, _activity(4, "gate_failure"))
    # One re-added proposal citing two new review/gate messages is two occurrences.
    llm.responses = [{"operations": [lesson((review_id, review), (rerun_id, rerun))]}]
    curator.run_session(session.id, force=True)

    active = service.store.list_active_curated_memories(session.id)
    assert len(active) == 1
    assert active[0].occurrences == 3


def test_module_lessons_must_quote_a_review_objection_or_gate_failure(tmp_path):
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("auth", scope=SessionScope(type="module", id="auth"))
    owner_text = "Owner note: always take the per-user lock before refreshing a token."
    owner_id = _ingest(service, session.id, owner_text, _activity(1, "message"))
    llm.responses = [
        {
            "operations": [
                {
                    "op": "add",
                    "kind": "lesson",
                    "topic_key": "auth.refresh_lock",
                    "statement": "Take the per-user lock before refreshing.",
                    "sources": [{"message_id": owner_id, "quote": owner_text}],
                }
            ]
        }
    ]
    assert curator.run_session(session.id).rejected_grounding == 1

    gate_text = "FAILED tests/test_refresh.py::test_concurrent_refresh - token written twice"
    gate_id = _ingest(service, session.id, gate_text, _activity(2, "gate_failure"))
    llm.responses = [
        {
            "operations": [
                {
                    "op": "add",
                    "kind": "lesson",
                    "topic_key": "auth.refresh_lock",
                    "statement": "Concurrent refresh without the lock writes the token twice.",
                    "sources": [{"message_id": gate_id, "quote": "token written twice"}],
                }
            ]
        }
    ]
    assert curator.run_session(session.id).added == 1
    system, user = llm.calls[-1]
    assert "module auth" in user
    assert f"[{gate_id}] " in user and "(agent, gate_failure)" in user


def test_long_gate_logs_are_rendered_as_head_and_tail():
    log = "x" * 3000 + "\nE   AssertionError: token written twice\n" + "y" * 3000
    message = Message(
        id="msg_1",
        session_id="s",
        role=Role.ASSISTANT,
        content=log,
        metadata={"activity_type": "gate_failure", "participant_id": "gate"},
    )

    rendered = render_message(message)

    assert "characters of the log omitted" in rendered
    assert rendered.count("x") == GATE_LOG_HEAD_CHARS
    assert "(agent, gate_failure)" in rendered
    untyped = Message(id="msg_2", session_id="s", role=Role.USER, content="hello there")
    assert render_message(untyped) == "[msg_2] user (human): hello there"
