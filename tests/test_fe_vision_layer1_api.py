"""Tests for fe-vision2-layer1-participants-api."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "xmuse" / "chat_api.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("xmuse_chat_api", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


create_app = _load_module().create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def test_create_conversation_seeds_default_builtin_participants(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post("/api/chat/conversations", json={"title": "default gods"})

    assert response.status_code == 201
    conversation = response.json()
    participants = conversation["participants"]
    assert [participant["role"] for participant in participants] == [
        "architect",
        "review",
        "execute",
    ]
    assert [participant["display_name"] for participant in participants] == [
        "architect-god",
        "review-god",
        "execute-god",
    ]
    assert all(participant["status"] == "active" for participant in participants)
    assert all(participant["role_template_id"] for participant in participants)

    list_response = client.get(
        f"/api/chat/conversations/{conversation['id']}/participants"
    )

    assert list_response.status_code == 200
    assert list_response.json()["participants"] == participants


def test_create_conversation_with_initial_participants_uses_requested_set(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    templates = client.get("/api/chat/role-templates").json()["role_templates"]
    review_template = next(t for t in templates if t["slug"] == "review")

    response = client.post(
        "/api/chat/conversations",
        json={
            "title": "custom gods",
            "initial_participants": [
                {
                    "role": "review",
                    "cli_kind": "claude",
                    "model": "opus",
                    "role_template_id": review_template["id"],
                    "display_name": "Review lead",
                }
            ],
        },
    )

    assert response.status_code == 201
    participants = response.json()["participants"]
    assert len(participants) == 1
    assert participants[0]["role"] == "review"
    assert participants[0]["display_name"] == "Review lead"
    assert participants[0]["model"] == "opus"
    assert participants[0]["role_template_id"] == review_template["id"]


def test_add_and_delete_conversation_participant(tmp_path: Path) -> None:
    client = _client(tmp_path)
    conversation = client.post(
        "/api/chat/conversations",
        json={"title": "participant crud", "initial_participants": []},
    ).json()

    add_response = client.post(
        f"/api/chat/conversations/{conversation['id']}/participants",
        json={"role": "execute", "cli_kind": "codex", "display_name": "Executor"},
    )

    assert add_response.status_code == 201
    participant = add_response.json()
    assert participant["role"] == "execute"
    assert participant["model"]
    assert participant["display_name"] == "Executor"

    delete_response = client.delete(
        f"/api/chat/conversations/{conversation['id']}/participants/"
        f"{participant['participant_id']}"
    )

    assert delete_response.status_code == 204
    list_response = client.get(
        f"/api/chat/conversations/{conversation['id']}/participants"
    )
    assert list_response.json()["participants"] == []


def test_role_template_crud_for_custom_templates(tmp_path: Path) -> None:
    client = _client(tmp_path)

    create_response = client.post(
        "/api/chat/role-templates",
        json={
            "slug": "security",
            "display_name": "Security GOD",
            "prompt": "Review security-sensitive changes.",
            "cli_kind": "codex",
            "default_model": "gpt-5.5",
        },
    )

    assert create_response.status_code == 201
    template = create_response.json()
    assert template["slug"] == "security"
    assert template["predefined"] is False

    update_response = client.put(
        f"/api/chat/role-templates/{template['id']}",
        json={
            "display_name": "Security Review GOD",
            "default_model": "gpt-5.5-review",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["display_name"] == "Security Review GOD"
    assert updated["prompt"] == "Review security-sensitive changes."
    assert updated["default_model"] == "gpt-5.5-review"

    list_response = client.get("/api/chat/role-templates")
    assert list_response.status_code == 200
    assert any(t["id"] == template["id"] for t in list_response.json()["role_templates"])

    delete_response = client.delete(f"/api/chat/role-templates/{template['id']}")

    assert delete_response.status_code == 204
    remaining = client.get("/api/chat/role-templates").json()["role_templates"]
    assert all(t["id"] != template["id"] for t in remaining)


def test_predefined_role_templates_reject_update_and_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)
    templates = client.get("/api/chat/role-templates").json()["role_templates"]
    architect = next(t for t in templates if t["slug"] == "architect")

    update_response = client.put(
        f"/api/chat/role-templates/{architect['id']}",
        json={"display_name": "Changed"},
    )
    delete_response = client.delete(f"/api/chat/role-templates/{architect['id']}")

    assert update_response.status_code == 409
    assert delete_response.status_code == 409
