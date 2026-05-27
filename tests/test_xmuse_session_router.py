from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from xmuse_core.routing import session_router as session_router_module
from xmuse_core.agents.god_session_registry import GodSessionRegistry
from xmuse_core.routing.session_router import SessionRouter


def test_route_resolves_god_session_and_queues_message(tmp_path):
    registry = GodSessionRegistry(tmp_path / "god_sessions.json")
    router = SessionRouter(registry=registry, inbox_root=tmp_path / "inboxes")
    record = registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://planner-1",
        session_inbox_id="inbox-planner-1",
    )

    routed = router.route(
        target_address="addr://planner-1",
        sender_address="addr://orchestrator",
        message_type="task.created",
        payload={"feature_id": "feature-123"},
    )

    assert routed.god_session_id == record.god_session_id
    inbox_path = tmp_path / "inboxes" / "inbox-planner-1.json"
    assert json.loads(inbox_path.read_text()) == [
        {
            "sender_address": "addr://orchestrator",
            "message_type": "task.created",
            "payload": {"feature_id": "feature-123"},
        }
    ]


def test_route_appends_when_inbox_already_exists(tmp_path):
    registry = GodSessionRegistry(tmp_path / "god_sessions.json")
    router = SessionRouter(registry=registry, inbox_root=tmp_path / "inboxes")
    registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://planner-1",
        session_inbox_id="inbox-planner-1",
    )
    inbox_path = tmp_path / "inboxes" / "inbox-planner-1.json"
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text(
        json.dumps(
            [
                {
                    "sender_address": "addr://existing",
                    "message_type": "task.existing",
                    "payload": {"feature_id": "feature-0"},
                }
            ]
        )
    )

    router.route(
        target_address="addr://planner-1",
        sender_address="addr://orchestrator",
        message_type="task.created",
        payload={"feature_id": "feature-123"},
    )

    assert json.loads(inbox_path.read_text()) == [
        {
            "sender_address": "addr://existing",
            "message_type": "task.existing",
            "payload": {"feature_id": "feature-0"},
        },
        {
            "sender_address": "addr://orchestrator",
            "message_type": "task.created",
            "payload": {"feature_id": "feature-123"},
        },
    ]


def test_route_raises_for_unknown_target_address(tmp_path):
    registry = GodSessionRegistry(tmp_path / "god_sessions.json")
    router = SessionRouter(registry=registry, inbox_root=tmp_path / "inboxes")

    with pytest.raises(KeyError, match="addr://missing"):
        router.route(
            target_address="addr://missing",
            sender_address="addr://orchestrator",
            message_type="task.created",
            payload={"feature_id": "feature-123"},
        )


def test_read_inbox_returns_empty_list_for_missing_inbox(tmp_path):
    registry = GodSessionRegistry(tmp_path / "god_sessions.json")
    router = SessionRouter(registry=registry, inbox_root=tmp_path / "inboxes")

    assert router.read_inbox("inbox-missing") == []


@pytest.mark.parametrize("inbox_id", ["../escape", "nested/inbox", "nested\\inbox"])
def test_read_inbox_rejects_invalid_inbox_id(tmp_path, inbox_id):
    registry = GodSessionRegistry(tmp_path / "god_sessions.json")
    router = SessionRouter(registry=registry, inbox_root=tmp_path / "inboxes")

    with pytest.raises(ValueError, match="inbox_id"):
        router.read_inbox(inbox_id)


def test_route_uses_sidecar_lock_file(tmp_path, monkeypatch):
    lock_calls: list[tuple[str, int]] = []

    def fake_flock(handle, operation):
        lock_calls.append((Path(handle.name).name, operation))

    monkeypatch.setattr(
        session_router_module,
        "fcntl",
        SimpleNamespace(LOCK_EX=1, LOCK_UN=2, flock=fake_flock),
        raising=False,
    )
    registry = GodSessionRegistry(tmp_path / "god_sessions.json")
    router = SessionRouter(registry=registry, inbox_root=tmp_path / "inboxes")
    registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://planner-1",
        session_inbox_id="inbox-planner-1",
    )

    router.route(
        target_address="addr://planner-1",
        sender_address="addr://orchestrator",
        message_type="task.created",
        payload={"feature_id": "feature-123"},
    )

    assert (tmp_path / "inboxes" / "inbox-planner-1.json.lock").exists()
    assert lock_calls == [("inbox-planner-1.json.lock", 1), ("inbox-planner-1.json.lock", 2)]
