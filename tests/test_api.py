from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.schemas import Role


def test_api_smoke(service):
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post("/sessions", json={"title": "api-test"})
        assert response.status_code == 200
        session_id = response.json()["id"]

        response = client.post(
            f"/sessions/{session_id}/ingest",
            json={"role": Role.USER.value, "content": "用户决定做 MemoryOS Lite。"},
        )
        assert response.status_code == 200

        response = client.post(
            f"/sessions/{session_id}/build-context",
            json={"task": "用户决定做什么项目？", "budget": 500},
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == session_id

        response = client.get(f"/sessions/{session_id}/trace")
        assert response.status_code == 200
        assert response.json()
    finally:
        app.dependency_overrides.clear()
