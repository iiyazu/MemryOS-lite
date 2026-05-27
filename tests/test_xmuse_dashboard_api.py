import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "xmuse" / "dashboard_api.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("xmuse_dashboard_api", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dashboard_api = _load_module()
create_app = dashboard_api.create_app


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(base_dir=tmp_path))


def test_list_lanes_returns_status_for_every_lane(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {"feature_id": "done-lane", "status": "done", "prompt": "ship it"},
                {"feature_id": "new-lane", "prompt": "build it"},
            ]
        },
    )

    response = _client(tmp_path).get("/api/lanes")

    assert response.status_code == 200
    assert response.json() == {
        "lanes": [
            {
                "feature_id": "done-lane",
                "status": "done",
                "effective_status": "done",
                "prompt": "ship it",
            },
            {
                "feature_id": "new-lane",
                "status": "pending",
                "effective_status": "ready",
                "prompt": "build it",
            },
        ]
    }


def test_lane_detail_includes_execution_logs(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "api-lane", "status": "running", "prompt": "test"}]},
    )
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "api-lane-round-1.log").write_text("started\nfinished\n", encoding="utf-8")
    (logs_dir / "other-lane.log").write_text("ignore me\n", encoding="utf-8")

    response = _client(tmp_path).get("/api/lanes/api-lane")

    assert response.status_code == 200
    body = response.json()
    assert body["lane"]["feature_id"] == "api-lane"
    assert body["execution_log"] == "started\nfinished\n"
    assert body["logs"] == [
        {
            "path": "logs/api-lane-round-1.log",
            "content": "started\nfinished\n",
        }
    ]


def test_lane_detail_includes_round_logs_that_mention_lane(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "api-lane", "status": "running", "prompt": "test"}]},
    )
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "round-1.log").write_text("api-lane: gate passed\n", encoding="utf-8")
    (logs_dir / "round-2.log").write_text("other-lane: gate passed\n", encoding="utf-8")

    response = _client(tmp_path).get("/api/lanes/api-lane")

    assert response.status_code == 200
    assert response.json()["logs"] == [
        {
            "path": "logs/round-1.log",
            "content": "api-lane: gate passed\n",
        }
    ]


def test_create_lane_appends_pending_execute_lane(tmp_path):
    _write_json(tmp_path / "feature_lanes.json", {"lanes": []})

    response = _client(tmp_path).post(
        "/api/lanes",
        json={
            "feature_id": "human-request",
            "prompt": "Add a dashboard",
            "capabilities": ["code", "test"],
        },
    )

    assert response.status_code == 201
    assert response.json()["feature_id"] == "human-request"
    data = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))
    assert data["lanes"] == [
        {
            "feature_id": "human-request",
            "task_type": "execute",
            "prompt": "Add a dashboard",
            "status": "pending",
            "capabilities": ["code", "test"],
        }
    ]


def test_create_lane_rejects_duplicate_feature_id(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "same", "prompt": "already queued"}]},
    )

    response = _client(tmp_path).post(
        "/api/lanes",
        json={"feature_id": "same", "prompt": "duplicate"},
    )

    assert response.status_code == 409


def test_approve_completed_lane_marks_approval(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "ready", "status": "done", "prompt": "ready"}]},
    )

    response = _client(tmp_path).post("/api/lanes/ready/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "approved"
    assert body["approved_at"]
    data = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))
    assert data["lanes"][0]["approval_status"] == "approved"


def test_approve_rejects_lane_that_is_not_completed(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "pending-lane", "status": "pending", "prompt": "wait"}]},
    )

    response = _client(tmp_path).post("/api/lanes/pending-lane/approve")

    assert response.status_code == 409


def test_reject_can_trigger_rework(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "needs-fix", "status": "done", "prompt": "almost"}]},
    )

    response = _client(tmp_path).post(
        "/api/lanes/needs-fix/reject",
        json={"reason": "Missing tests", "rework": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "rejected"
    assert body["status"] == "pending"
    assert body["rework_requested"] is True
    assert body["rejection_reason"] == "Missing tests"


def test_sessions_and_errors_tolerate_missing_files(tmp_path):
    client = _client(tmp_path)

    assert client.get("/api/sessions").json() == {"sessions": []}
    assert client.get("/api/errors").json() == {"errors": []}


def test_sessions_and_errors_read_supported_file_shapes(tmp_path):
    _write_json(
        tmp_path / "active_sessions.json",
        {"sessions": [{"feature_id": "running", "pid": 123, "state": "running"}]},
    )
    _write_json(
        tmp_path / "error_knowledge.json",
        {"entries": [{"entry_id": "err-1", "pit": "pytest failed"}]},
    )
    client = _client(tmp_path)

    assert client.get("/api/sessions").json() == {
        "sessions": [{"feature_id": "running", "pid": 123, "state": "running"}]
    }
    assert client.get("/api/errors").json() == {
        "errors": [{"entry_id": "err-1", "pit": "pytest failed"}]
    }


def test_sessions_support_mcp_dict_shape(tmp_path):
    _write_json(
        tmp_path / "active_sessions.json",
        {
            "sessions": {
                "running": {"session_id": "sess-1", "pid": 123, "status": "running"}
            }
        },
    )

    response = _client(tmp_path).get("/api/sessions")

    assert response.status_code == 200
    assert response.json() == {
        "sessions": [
            {
                "feature_id": "running",
                "session_id": "sess-1",
                "pid": 123,
                "status": "running",
            }
        ]
    }


def test_sessions_support_god_session_registry_shape(tmp_path):
    _write_json(
        tmp_path / "active_sessions.json",
        {
            "sessions": [
                {
                    "god_session_id": "god-1",
                    "role": "executor",
                    "session_address": "xmuse://sessions/god-1",
                    "session_inbox_id": "inbox-1",
                    "status": "running",
                    "pid": 456,
                }
            ]
        },
    )

    response = _client(tmp_path).get("/api/sessions")

    assert response.status_code == 200
    assert response.json() == {
        "sessions": [
            {
                "god_session_id": "god-1",
                "role": "executor",
                "session_address": "xmuse://sessions/god-1",
                "session_inbox_id": "inbox-1",
                "status": "running",
                "pid": 456,
            }
        ]
    }


def test_metrics_use_normalized_lane_states(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {"feature_id": "ready-lane", "status": "pending", "duration_seconds": 10},
                {"feature_id": "requeued-lane", "status": "reworking", "duration_seconds": 30},
                {"feature_id": "done-lane", "status": "merged"},
                {"feature_id": "terminated-lane", "status": "failed"},
                {"feature_id": "gate-failed-lane", "status": "gate_failed"},
                {"feature_id": "exec-failed-lane", "status": "exec_failed"},
            ]
        },
    )

    response = _client(tmp_path).get("/api/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "total": 6,
        "done": 1,
        "ready": 1,
        "requeued": 1,
        "failed": 3,
        "pending": 2,
        "avg_time_seconds": 20.0,
    }


def test_approve_accepts_merged_lane(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "ready", "status": "merged", "prompt": "ready"}]},
    )

    response = _client(tmp_path).post("/api/lanes/ready/approve")

    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"


def test_approve_awaiting_final_action_merge_resolves_hold(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {"lanes": [{"feature_id": "ready", "status": "awaiting_final_action", "prompt": "ready"}]},
    )
    _write_json(
        tmp_path / "final_actions.json",
        {
            "holds": [
                {
                    "id": "final-1",
                    "lane_id": "ready",
                    "verdict_id": "verdict-1",
                    "action": "merge",
                    "target_status": "reviewed",
                    "status": "pending",
                    "summary": "merge now",
                }
            ]
        },
    )

    response = _client(tmp_path).post("/api/lanes/ready/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "merged"
    data = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))
    assert data["lanes"][0]["status"] == "merged"
    holds = json.loads((tmp_path / "final_actions.json").read_text(encoding="utf-8"))
    assert holds["holds"][0]["status"] == "approved"


def test_metrics_treats_merged_lane_as_completed(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {"feature_id": "a", "status": "merged", "duration_seconds": 10},
                {"feature_id": "b", "status": "failed", "duration_seconds": 30},
                {"feature_id": "c", "status": "running"},
            ]
        },
    )

    response = _client(tmp_path).get("/api/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "done": 1,
        "ready": 0,
        "requeued": 0,
        "failed": 1,
        "pending": 1,
        "avg_time_seconds": 20.0,
    }


def test_cors_allows_localhost_frontend(tmp_path):
    response = _client(tmp_path).options(
        "/api/lanes",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_default_port_is_dashboard_port():
    assert dashboard_api.DEFAULT_PORT == 8200


def test_dashboard_lists_resolutions_and_verdicts_from_read_models(tmp_path):
    _write_json(
        tmp_path / "read_models" / "resolutions.json",
        {"resolutions": [{"resolution_id": "res-1", "status": "approved"}]},
    )
    _write_json(
        tmp_path / "read_models" / "verdicts.json",
        {"verdicts": [{"verdict_id": "verdict-1", "decision": "merge"}]},
    )

    client = _client(tmp_path)
    resolutions = client.get("/api/resolutions")
    verdicts = client.get("/api/verdicts")

    assert resolutions.status_code == 200
    assert resolutions.json()["resolutions"][0]["resolution_id"] == "res-1"
    assert verdicts.status_code == 200
    assert verdicts.json()["verdicts"][0]["decision"] == "merge"
