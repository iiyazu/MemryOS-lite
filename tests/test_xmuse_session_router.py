from __future__ import annotations

import json

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
