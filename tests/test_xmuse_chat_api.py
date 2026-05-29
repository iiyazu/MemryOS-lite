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


chat_api = _load_module()
create_app = chat_api.create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(base_dir=tmp_path))


def test_chat_conversation_message_flow_uses_sqlite_store(tmp_path: Path) -> None:
    client = _client(tmp_path)

    create_response = client.post("/api/chat/conversations", json={"title": "xmuse MVP"})

    assert create_response.status_code == 201
    conversation = create_response.json()
    assert conversation["title"] == "xmuse MVP"
    assert (tmp_path / "chat.db").exists()

    message_response = client.post(
        f"/api/chat/conversations/{conversation['id']}/messages",
        json={
            "author": "human",
            "role": "human",
            "content": "Need the first chat-plane backend slice.",
        },
    )

    assert message_response.status_code == 201
    list_response = client.get(f"/api/chat/conversations/{conversation['id']}/messages")

    assert list_response.status_code == 200
    assert [item["content"] for item in list_response.json()["messages"]] == [
        "Need the first chat-plane backend slice."
    ]

    conversations_response = client.get("/api/chat/conversations")
    assert conversations_response.status_code == 200
    assert conversations_response.json()["conversations"][0]["id"] == conversation["id"]


def test_chat_proposal_approval_creates_resolution_snapshot(tmp_path: Path) -> None:
    client = _client(tmp_path)
    conversation = client.post(
        "/api/chat/conversations",
        json={"title": "xmuse MVP"},
    ).json()

    proposal_response = client.post(
        f"/api/chat/conversations/{conversation['id']}/proposals",
        json={
            "author": "architect-god",
            "proposal_type": "lane-plan",
            "content": "Split into chat, planner, execution, dashboard lanes.",
            "references": [],
        },
    )

    assert proposal_response.status_code == 201
    proposal = proposal_response.json()

    approval_response = client.post(
        f"/api/chat/proposals/{proposal['id']}/approve",
        json={
            "approved_by": ["human"],
            "approval_mode": "human",
            "goal_summary": "Build the MVP",
        },
    )

    assert approval_response.status_code == 200
    resolution = approval_response.json()
    assert resolution["version"] == 1
    assert resolution["status"] == "approved"

    fetch_response = client.get(f"/api/chat/resolutions/{resolution['id']}")

    assert fetch_response.status_code == 200
    assert fetch_response.json()["derived_from_proposal_ids"] == [proposal["id"]]


def test_approving_proposal_projects_dependency_ready_lanes_into_execution_queue(tmp_path: Path) -> None:
    client = _client(tmp_path)
    conversation = client.post(
        "/api/chat/conversations",
        json={"title": "xmuse MVP"},
    ).json()
    proposal = client.post(
        f"/api/chat/conversations/{conversation['id']}/proposals",
        json={
            "author": "architect-god",
            "proposal_type": "lane-plan",
            "content": "Split into chat and dashboard lanes.",
            "references": [],
        },
    ).json()

    approval_response = client.post(
        f"/api/chat/proposals/{proposal['id']}/approve",
        json={
            "approved_by": ["human"],
            "approval_mode": "human",
            "goal_summary": "Build the MVP",
            "content": {
                "lanes": [
                    {
                        "feature_id": "chat-plane",
                        "prompt": "Build the chat plane.",
                        "priority": 90,
                        "capabilities": ["code"],
                        "depends_on": [],
                    },
                    {
                        "feature_id": "dashboard-split",
                        "prompt": "Build the dashboard surface.",
                        "priority": 60,
                        "capabilities": ["code", "test"],
                        "depends_on": ["chat-plane"],
                    },
                ]
            },
        },
    )

    assert approval_response.status_code == 200
    resolution = approval_response.json()
    lanes_path = tmp_path / "feature_lanes.json"
    assert lanes_path.exists()
    assert lanes_path.read_text(encoding="utf-8")
    graph_path = tmp_path / "lane_graphs" / f"{resolution['id']}-graph-v1.json"
    assert graph_path.exists()


def test_chat_threads_endpoint_projects_conversations_and_messages(tmp_path: Path) -> None:
    client = _client(tmp_path)
    conversation = client.post("/api/chat/conversations", json={"title": "lane-alpha"}).json()
    client.post(
        f"/api/chat/conversations/{conversation['id']}/messages",
        json={
            "author": "human",
            "role": "human",
            "content": "Summarize the blocking gate evidence.",
        },
    )

    threads_response = client.get("/api/chat/threads")

    assert threads_response.status_code == 200
    thread = threads_response.json()["threads"][0]
    assert thread["id"] == conversation["id"]
    assert thread["featureId"] == "lane-alpha"
    assert thread["messages"][0]["role"] == "user"


def test_thread_message_endpoint_records_human_checkpoint(tmp_path: Path) -> None:
    client = _client(tmp_path)
    conversation = client.post("/api/chat/conversations", json={"title": "lane-beta"}).json()

    response = client.post(
        f"/api/chat/threads/{conversation['id']}/messages",
        json={"message": "Keep the next patch minimal."},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["thread_id"] == conversation["id"]
    assert payload["message"]["role"] == "user"
    assert payload["message"]["content"] == "Keep the next patch minimal."
