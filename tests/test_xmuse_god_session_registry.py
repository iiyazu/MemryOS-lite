from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from xmuse_core.agents import god_session_registry as registry_module
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

    assert record.god_session_id.startswith("god-")
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


def test_create_rejects_duplicate_session_address(tmp_path):
    path = tmp_path / "god_sessions.json"
    registry = GodSessionRegistry(path)
    registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://shared",
        session_inbox_id="inbox-alpha",
    )

    with pytest.raises(ValueError, match="session_address"):
        registry.create(
            role="reviewer",
            agent_name="beta",
            runtime="claude_code",
            session_address="addr://shared",
            session_inbox_id="inbox-beta",
        )


def test_create_rejects_duplicate_session_inbox_id(tmp_path):
    path = tmp_path / "god_sessions.json"
    registry = GodSessionRegistry(path)
    registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://alpha",
        session_inbox_id="inbox-shared",
    )

    with pytest.raises(ValueError, match="session_inbox_id"):
        registry.create(
            role="reviewer",
            agent_name="beta",
            runtime="claude_code",
            session_address="addr://beta",
            session_inbox_id="inbox-shared",
        )


def test_assign_preserves_unrelated_fields(tmp_path):
    path = tmp_path / "god_sessions.json"
    initial = {
        "sessions": [
            {
                "god_session_id": "god-existing",
                "role": "planner",
                "agent_name": "alpha",
                "runtime": "codex",
                "session_address": "addr://alpha",
                "session_inbox_id": "inbox-alpha",
                "status": "running",
                "assignment_feature_id": None,
                "pid": 4242,
            }
        ]
    }
    path.write_text(json.dumps(initial))
    registry = GodSessionRegistry(path)

    updated = registry.assign("god-existing", "feature-123")

    assert updated.god_session_id == "god-existing"
    assert updated.role == "planner"
    assert updated.agent_name == "alpha"
    assert updated.runtime == "codex"
    assert updated.session_address == "addr://alpha"
    assert updated.session_inbox_id == "inbox-alpha"
    assert updated.status == "running"
    assert updated.pid == 4242
    assert updated.assignment_feature_id == "feature-123"


def test_create_and_assign_use_sidecar_file_lock(tmp_path, monkeypatch):
    path = tmp_path / "god_sessions.json"
    lock_calls: list[tuple[str, int]] = []

    def fake_flock(handle, operation):
        lock_calls.append((Path(handle.name).name, operation))

    monkeypatch.setattr(
        registry_module,
        "fcntl",
        SimpleNamespace(LOCK_EX=1, LOCK_UN=2, flock=fake_flock),
        raising=False,
    )
    registry = GodSessionRegistry(path)

    created = registry.create(
        role="planner",
        agent_name="alpha",
        runtime="codex",
        session_address="addr://alpha",
        session_inbox_id="inbox-alpha",
    )
    registry.assign(created.god_session_id, "feature-123")

    assert path.with_name(f"{path.name}.lock").exists()
    assert lock_calls == [
        (f"{path.name}.lock", 1),
        (f"{path.name}.lock", 2),
        (f"{path.name}.lock", 1),
        (f"{path.name}.lock", 2),
    ]
