"""Curated-memory advisories v3. All LLM calls use injectable fakes; no network."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.curator import Curator
from memoryos_lite.curator.advisories import (
    ADVISORY_KIND_BY_MEMORY_KIND,
    ADVISORY_SCHEMA_V3,
    ADVISORY_V3_ITEM_KEYS,
    ADVISORY_V3_KINDS,
    V3_MAX_CONTENT_BYTES,
    V3_MAX_QUOTE_BYTES,
    advisory_identity,
    build_advisory_v3_items,
)
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role, SessionScope
from memoryos_lite.store import create_store
from memoryos_lite.store_curator import CuratedMemoryRow


class ScriptedLLM:
    def __init__(self) -> None:
        self.responses: list[dict[str, object]] = []
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        self.calls.append((system, user))
        return self.responses.pop(0) if self.responses else {"operations": []}


def _service(tmp_path, llm, **overrides) -> tuple[MemoryOSService, Curator]:
    settings = Settings(
        data_dir=tmp_path / "memoryos",
        memoryos_curator_enabled=True,
        **{"memoryos_curator_window_messages": 1, **overrides},
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=llm)
    return MemoryOSService(store=store, settings=settings, curator=curator), curator


def _module_meta(seq: int, activity_type: str) -> dict[str, object]:
    return {"activity_type": activity_type, "module_id": "auth", "activity_seq": seq}


def _ingest_module(
    service: MemoryOSService,
    session_id: str,
    content: str,
    seq: int,
    activity_type: str,
    external_id: str | None = None,
) -> str:
    return service.ingest(
        session_id,
        MessageCreate(
            role=Role.ASSISTANT,
            content=content,
            external_id=external_id,
            metadata=_module_meta(seq, activity_type),
        ),
    ).message.id


def _op(
    message_id: str, statement: str, *, topic_key: str, kind: str = "fact"
) -> dict[str, object]:
    return {
        "op": "add",
        "kind": kind,
        "topic_key": topic_key,
        "statement": statement,
        "sources": [{"message_id": message_id, "quote": statement}],
    }


def test_module_session_v3_kinds_scope_version_occurrences_and_refs(tmp_path) -> None:
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("auth", scope=SessionScope(type="module", id="auth"))
    first = "FAILED tests/test_refresh.py::test_concurrent_refresh - token written twice"
    first_id = _ingest_module(service, session.id, first, 1, "gate_failure", "gate-001")
    llm.responses = [
        {"operations": [_op(first_id, first, topic_key="auth.refresh_lock", kind="lesson")]}
    ]
    assert curator.run_session(session.id).added == 1

    second = "Review objection: refresh again ran without taking the lock."
    second_id = _ingest_module(service, session.id, second, 2, "review_objection", "rev-002")
    llm.responses = [
        {"operations": [_op(second_id, second, topic_key="auth.refresh_lock", kind="lesson")]}
    ]
    assert curator.run_session(session.id).superseded == 1

    decision_text = "Refreshes must take the per-user lock before touching tokens."
    decision_id = _ingest_module(service, session.id, decision_text, 3, "message", "owner-003")
    llm.responses = [
        {
            "operations": [
                _op(decision_id, decision_text, topic_key="auth.refresh_policy", kind="decision")
            ]
        }
    ]
    assert curator.run_session(session.id).added == 1

    payload = service.list_curated_advisories_v3(session.id)
    assert payload["schema"] == ADVISORY_SCHEMA_V3
    assert payload["session_scope"] == {"type": "module", "id": "auth"}
    items = payload["items"]
    assert isinstance(items, list) and items
    for item in items:
        assert set(item) == set(ADVISORY_V3_ITEM_KEYS)

    lessons = [item for item in items if item["memory_kind"] == "lesson"]
    assert lessons
    lesson = lessons[-1]
    assert lesson["kind"] == "module_lesson"
    assert lesson["scope"] == {"type": "module", "id": "auth"}
    assert lesson["occurrences"] == 2
    assert lesson["version"] == 2
    refs = lesson["source_refs"]
    assert [ref["source_id"] for ref in refs] == [first_id, second_id]
    assert refs[0]["external_id"] == "gate-001"
    assert refs[0]["activity_type"] == "gate_failure"
    assert refs[1]["external_id"] == "rev-002"
    assert refs[1]["activity_type"] == "review_objection"

    decisions = [item for item in items if item["memory_kind"] == "decision"]
    assert decisions[-1]["kind"] == "module_decision"
    assert decisions[-1]["scope"] == {"type": "module", "id": "auth"}
    assert decisions[-1]["version"] == 3
    assert decisions[-1]["occurrences"] == 1


def test_room_session_v3_uses_v2_kinds_and_room_project_user_scopes(tmp_path) -> None:
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("room")
    kinds = ["fact", "rule", "preference"]
    expected_kinds = ["room_fact", "project_rule", "user_preference"]
    expected_scopes = [{"type": "room"}, {"type": "project"}, {"type": "user"}]
    for index, kind in enumerate(kinds):
        text = f"A durable {kind} statement for room mapping {index}."
        message_id = service.ingest(
            session.id, MessageCreate(role=Role.USER, content=text)
        ).message.id
        llm.responses = [
            {"operations": [_op(message_id, text, topic_key=f"room.{kind}{index}", kind=kind)]}
        ]
        assert curator.run_session(session.id).added == 1

    payload = service.list_curated_advisories_v3(session.id)
    assert payload["session_scope"] is None
    items = payload["items"]
    assert [item["kind"] for item in items] == expected_kinds
    assert [item["scope"] for item in items] == expected_scopes
    for item, kind in zip(items, kinds, strict=True):
        assert item["memory_kind"] == kind
        assert item["kind"] == ADVISORY_KIND_BY_MEMORY_KIND[kind]


def test_v3_supersedes_link_matches_v2_identity(tmp_path) -> None:
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("supersede")
    old_text = "The launch city is Lisbon."
    old_id = service.ingest(session.id, MessageCreate(role=Role.USER, content=old_text)).message.id
    llm.responses = [{"operations": [_op(old_id, old_text, topic_key="project.launch_city")]}]
    assert curator.run_session(session.id).added == 1

    new_text = "The launch city is now Porto."
    new_id = service.ingest(session.id, MessageCreate(role=Role.USER, content=new_text)).message.id
    llm.responses = [{"operations": [_op(new_id, new_text, topic_key="project.launch_city")]}]
    assert curator.run_session(session.id).superseded == 1

    payload = service.list_curated_advisories_v3(session.id)
    items = payload["items"]
    assert len(items) == 2
    assert items[1]["supersedes_advisory_id"] == items[0]["advisory_id"]
    assert items[0]["supersedes_advisory_id"] is None
    v2_items = service.list_curated_advisories(session.id)
    assert items[1]["advisory_id"] == v2_items[1]["advisory_id"]
    assert items[1]["fingerprint"] == v2_items[1]["fingerprint"]


def test_v3_truncation_keeps_valid_prefix_and_caps_refs() -> None:
    from datetime import UTC, datetime

    long_quote = "é" * 600
    assert len(long_quote.encode("utf-8")) > V3_MAX_QUOTE_BYTES
    long_statement = "x" * 5000
    assert len(long_statement.encode("utf-8")) > V3_MAX_CONTENT_BYTES
    sources = [{"message_id": f"msg_{i}", "quote": long_quote} for i in range(10)]
    row = CuratedMemoryRow(
        id="cmem_test",
        session_id="ses_test",
        kind="fact",
        topic_key="test.truncation",
        statement=long_statement,
        sources=sources,
        status="active",
        supersedes_id=None,
        superseded_by_id=None,
        run_id="crun_test",
        model="test-model",
        created_at=datetime.now(UTC),
        version=1,
        occurrences=1,
    )
    items = build_advisory_v3_items(
        [row], {}, session_scope=None, message_info={f"msg_{i}": (None, None) for i in range(10)}
    )
    assert len(items) == 1
    item = items[0]
    assert len(item["source_refs"]) == 8
    assert [ref["source_id"] for ref in item["source_refs"]] == [f"msg_{i}" for i in range(2, 10)]
    quote = item["source_refs"][0]["quote"]
    assert isinstance(quote, str)
    assert len(quote.encode("utf-8")) <= V3_MAX_QUOTE_BYTES
    assert long_quote.startswith(quote)
    quote.encode("utf-8")
    content = item["content"]
    assert isinstance(content, str)
    assert len(content.encode("utf-8")) <= V3_MAX_CONTENT_BYTES
    assert long_statement.startswith(content)


def test_v1_v2_responses_unchanged(tmp_path) -> None:
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("compat")
    statement = "Project Helios launches in Lisbon."
    message_id = service.ingest(
        session.id, MessageCreate(role=Role.USER, content=statement)
    ).message.id
    llm.responses = [{"operations": [_op(message_id, statement, topic_key="project.launch_city")]}]
    assert curator.run_session(session.id).added == 1

    v2_items = service.list_curated_advisories(session.id)
    assert len(v2_items) == 1
    assert set(v2_items[0]) == {
        "advisory_id",
        "fingerprint",
        "proposal_type",
        "kind",
        "topic_key",
        "content",
        "source_refs",
        "supersedes_advisory_id",
    }
    assert v2_items[0]["kind"] == "room_fact"
    assert v2_items[0]["source_refs"] == [
        {
            "source_type": "message",
            "source_id": message_id,
            "session_id": session.id,
            "quote": statement,
        }
    ]
    v1_items = service.list_external_advisories(session.id)
    assert isinstance(v1_items, list)


def test_advisories_endpoint_v3_and_unsupported_version(tmp_path) -> None:
    llm = ScriptedLLM()
    service, curator = _service(tmp_path, llm)
    session = service.create_session("endpoint", scope=SessionScope(type="module", id="auth"))
    text = "FAILED gate: concurrent refresh wrote the token twice"
    message_id = _ingest_module(service, session.id, text, 1, "gate_failure", "gate-e2e-1")
    llm.responses = [{"operations": [_op(message_id, text, topic_key="auth.lock", kind="lesson")]}]
    assert curator.run_session(session.id).added == 1

    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        v3 = client.get(f"/sessions/{session.id}/advisories", params={"version": 3})
        assert v3.status_code == 200
        body = v3.json()
        assert body["schema"] == ADVISORY_SCHEMA_V3
        assert body["session_scope"] == {"type": "module", "id": "auth"}
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert set(item) == set(ADVISORY_V3_ITEM_KEYS)
        assert item["kind"] == "module_lesson"
        assert item["source_refs"][0]["external_id"] == "gate-e2e-1"
        assert item["source_refs"][0]["activity_type"] == "gate_failure"

        bad = client.get(f"/sessions/{session.id}/advisories", params={"version": 4})
        assert bad.status_code == 400
        assert "unsupported advisories version" in bad.json()["detail"]

        v2 = client.get(f"/sessions/{session.id}/advisories", params={"version": 2})
        assert v2.status_code == 200
        assert v2.json()["schema"] == "memoryos_external_advisories/v2"
    finally:
        app.dependency_overrides.pop(get_service, None)


def test_contract_example_matches_v3_constants() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "contracts"
        / "memoryos_external_advisories_v3.example.json"
    )
    example = json.loads(path.read_text(encoding="utf-8"))
    assert example["schema"] == ADVISORY_SCHEMA_V3
    assert example["session_scope"] == {"type": "module", "id": "auth"}
    kinds = {item["kind"] for item in example["items"]}
    assert {"module_lesson", "module_decision"} <= kinds
    assert kinds <= set(ADVISORY_V3_KINDS)
    for item in example["items"]:
        assert set(item) == set(ADVISORY_V3_ITEM_KEYS)
        assert item["kind"] in ADVISORY_V3_KINDS
    lesson = next(item for item in example["items"] if item["kind"] == "module_lesson")
    assert lesson["source_refs"][0]["activity_type"] == "gate_failure"
    decision = next(item for item in example["items"] if item["kind"] == "module_decision")
    assert isinstance(decision["supersedes_advisory_id"], str)
    assert decision["supersedes_advisory_id"].startswith("advisory_")
    for item in example["items"]:
        memory_kind = item["memory_kind"]
        check_sources = [
            {"message_id": ref["source_id"], "quote": ref["quote"]} for ref in item["source_refs"]
        ]
        advisory_id, fingerprint = advisory_identity(memory_kind, item["content"], check_sources)
        assert item["advisory_id"] == advisory_id
        assert item["fingerprint"] == fingerprint
