from __future__ import annotations

import json

from xmuse_core.agents.god_session_registry import GodSessionRegistry


def test_create_persists_stable_god_session_id(tmp_path):
    path = tmp_path / "god_sessions.json"
    registry = GodSessionRegistry(path)

    record = registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://planner-1",
        session_inbox_id="inbox-planner-1",
    )

    assert record.god_session_id
    assert record.assignment_feature_id is None
    stored = json.loads(path.read_text())
    assert stored == {
        "sessions": [
            {
                "god_session_id": record.god_session_id,
                "role": "planner",
                "agent_name": "alpha",
                "runtime": "codex",
                "session_address": "addr://planner-1",
                "session_inbox_id": "inbox-planner-1",
                "status": "starting",
                "assignment_feature_id": None,
                "pid": None,
            }
        ]
    }


def test_lookup_by_address_and_inbox(tmp_path):
    path = tmp_path / "god_sessions.json"
    registry = GodSessionRegistry(path)

    created = registry.create(
        role="reviewer",
        agent_name="beta",
        runtime="claude_code",
        session_address="addr://reviewer-1",
        session_inbox_id="inbox-reviewer-1",
    )

    by_address = registry.find_by_address("addr://reviewer-1")
    by_inbox = registry.find_by_inbox("inbox-reviewer-1")
    by_id = registry.get(created.god_session_id)

    assert by_address == created
    assert by_inbox == created
    assert by_id == created
    assert registry.list() == [created]


def test_assign_updates_feature_without_changing_god_session_id(tmp_path):
    path = tmp_path / "god_sessions.json"
    registry = GodSessionRegistry(path)

    created = registry.create(
        role="executor",
        agent_name="gamma",
        runtime="codex",
        session_address="addr://executor-1",
        session_inbox_id="inbox-executor-1",
    )

    updated = registry.assign(created.god_session_id, "feature-123")

    assert updated.god_session_id == created.god_session_id
    assert updated.assignment_feature_id == "feature-123"
    reloaded = GodSessionRegistry(path).get(created.god_session_id)
    assert reloaded.god_session_id == created.god_session_id
    assert reloaded.assignment_feature_id == "feature-123"
