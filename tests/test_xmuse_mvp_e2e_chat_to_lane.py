import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from xmuse_core.chat.models import StructuredResolution
from xmuse_core.structuring.planner import build_lane_graph
from xmuse_core.structuring.projection import project_ready_lanes

PROJECT = Path(__file__).resolve().parents[1]
CHAT_MODULE_PATH = PROJECT / "xmuse" / "chat_api.py"
DASHBOARD_MODULE_PATH = PROJECT / "xmuse" / "dashboard_api.py"


def _load_dashboard_module():
    spec = importlib.util.spec_from_file_location("xmuse_dashboard_api", DASHBOARD_MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module():
    spec = importlib.util.spec_from_file_location("xmuse_chat_api", CHAT_MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chat_api = _load_module()
dashboard_api = _load_dashboard_module()


def _chat_client(tmp_path: Path) -> TestClient:
    return TestClient(chat_api.create_app(base_dir=tmp_path))


def test_chat_to_lane_projection_smoke(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    conversation = client.post("/api/chat/conversations", json={"title": "xmuse MVP"}).json()
    proposal = client.post(
        f"/api/chat/conversations/{conversation['id']}/proposals",
        json={
            "author": "architect-god",
            "proposal_type": "lane-plan",
            "content": "Chat first, dashboard separate.",
            "references": [],
        },
    ).json()

    resolution_payload = client.post(
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
    ).json()

    resolution = StructuredResolution(**resolution_payload)
    graph = build_lane_graph(resolution)
    existing_lanes = (tmp_path / "feature_lanes.json").read_text(encoding="utf-8")
    projected = project_ready_lanes(graph, tmp_path / "feature_lanes.json")
    dashboard = TestClient(dashboard_api.create_app(base_dir=tmp_path))
    resolutions = dashboard.get("/api/resolutions")

    assert "chat-plane" in existing_lanes
    assert [lane["feature_id"] for lane in projected] == []
    assert resolutions.status_code == 200
    assert resolutions.json()["resolutions"][0]["resolution_id"] == resolution.id
