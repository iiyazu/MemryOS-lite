from fastapi.testclient import TestClient

from memoryos_lite import __version__
from memoryos_lite.api import app as api_app_module
from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ContextPackage, Role
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    ContextLayerItem,
    ContextPackageV3,
    SourceRef,
    SourceType,
)


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
    finally:
        app.dependency_overrides.clear()


def test_api_build_context_full_profile_is_default(service):
    session = service.create_session("full-profile")
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        default_response = client.post(
            f"/sessions/{session.id}/build-context",
            json={"task": "What should be recalled?", "budget": 500},
        )
        explicit_response = client.post(
            f"/sessions/{session.id}/build-context",
            json={
                "task": "What should be recalled?",
                "budget": 500,
                "response_profile": "full",
            },
        )

        assert default_response.status_code == 200
        assert explicit_response.status_code == 200
        assert default_response.json() == explicit_response.json()
        assert default_response.json()["session_id"] == session.id
    finally:
        app.dependency_overrides.clear()


def test_api_build_context_accepts_source_evidence_v2_profile(service):
    session = service.create_session("source-evidence-v2-profile")
    service.build_context = lambda **_kwargs: ContextPackage(
        session_id=session.id,
        task="What should be recalled?",
        metadata={
            "v3_context": ContextPackageV3(
                session_id=session.id,
                task="What should be recalled?",
            ).model_dump(mode="json")
        },
    )
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            f"/sessions/{session.id}/build-context",
            json={
                "task": "What should be recalled?",
                "response_profile": "source_evidence/v2",
            },
        )

        assert response.status_code == 200
        assert response.json()["schema"] == "memoryos_source_evidence/v2"
    finally:
        app.dependency_overrides.clear()


def test_api_build_context_source_evidence_profile_uses_compact_builder(
    service,
    monkeypatch,
):
    session = service.create_session("source-evidence-profile")
    captured = []

    def _build_source_evidence(package):
        captured.append(package)
        return {
            "schema": "memoryos_source_evidence/v1",
            "items": [],
            "omitted_count": 0,
            "estimated_tokens": 0,
            "truncated": False,
            "diagnostics_digest": f"sha256:{'0' * 64}",
        }

    monkeypatch.setattr(api_app_module, "build_source_evidence", _build_source_evidence)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            f"/sessions/{session.id}/build-context",
            json={
                "task": "What should be recalled?",
                "budget": 500,
                "response_profile": "source_evidence/v1",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "schema": "memoryos_source_evidence/v1",
            "items": [],
            "omitted_count": 0,
            "estimated_tokens": 0,
            "truncated": False,
            "diagnostics_digest": f"sha256:{'0' * 64}",
        }
        assert len(captured) == 1
        assert captured[0].session_id == session.id
    finally:
        app.dependency_overrides.clear()


def test_api_build_context_source_evidence_failure_is_stable_422(
    service,
    monkeypatch,
):
    session = service.create_session("source-evidence-invalid")

    def _reject_source_evidence(_package):
        raise ValueError("source_evidence_v3_context_missing")

    monkeypatch.setattr(api_app_module, "build_source_evidence", _reject_source_evidence)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            f"/sessions/{session.id}/build-context",
            json={"task": "Recall", "response_profile": "source_evidence/v1"},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "source_evidence_v3_context_missing"}
    finally:
        app.dependency_overrides.clear()


def test_api_compact_source_evidence_omits_non_finite_score(service, monkeypatch):
    session = service.create_session("non-finite-source-evidence")
    invalid = ContextLayerItem(
        layer="archival",
        item_id="invalid",
        text="invalid score",
        estimated_tokens=1,
        source_refs=[SourceRef(source_type=SourceType.DOCUMENT, source_id="source-invalid")],
        metadata={
            "archive_id": "archive-1",
            "document_id": "document-1",
            "score": float("nan"),
        },
    )
    valid = ContextLayerItem(
        layer="archival",
        item_id="valid",
        text="valid score",
        estimated_tokens=1,
        source_refs=[SourceRef(source_type=SourceType.DOCUMENT, source_id="source-valid")],
        metadata={"archive_id": "archive-1", "document_id": "document-1", "score": 0.75},
    )
    package = ContextPackage(
        session_id=session.id,
        task="Recall",
        metadata={
            "v3_context": ContextPackageV3(
                session_id=session.id,
                task="Recall",
                items=[invalid, valid],
            ).model_dump(mode="json")
        },
    )
    monkeypatch.setattr(service, "build_context", lambda **_kwargs: package)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            f"/sessions/{session.id}/build-context",
            json={"task": "Recall", "response_profile": "source_evidence/v1"},
        )

        assert response.status_code == 200, response.text
        assert [item["item_id"] for item in response.json()["items"]] == ["valid"]
        assert response.json()["omitted_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_health_advertises_build_context_profiles():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == __version__ == app.version
    assert payload["capabilities"]["build_context_profiles"] == [
        "full",
        "source_evidence/v1",
        "source_evidence/v2",
    ]
    assert payload["capabilities"]["hybrid"]["lexical"] is True
    assert payload["capabilities"]["hybrid"]["rrf"] is payload["capabilities"]["hybrid"]["semantic"]
    assert payload["capabilities"]["message_ingest"] is True


def test_api_archive_ingest_and_attach(service):
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        session_response = client.post("/sessions", json={"title": "api-archive"})
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]
        ref = {"source_type": "document", "source_id": "doc_api", "session_id": session_id}

        ingest_response = client.post(
            "/archives/ingest",
            json={
                "document_id": "adoc_api",
                "title": "API archive",
                "content": "API archive says Project Helios launches in Lisbon.",
                "source_refs": [ref],
                "identity": {"kind": "archive", "archive_id": "archive_api"},
            },
        )
        assert ingest_response.status_code == 200, ingest_response.text
        passage_ids = ingest_response.json()["passage_ids"]
        assert len(passage_ids) == 1
        assert passage_ids[0].startswith("apsg_")

        attach_response = client.post(
            "/archives/attachments",
            json={
                "archive_id": "archive_api",
                "scope_type": "session",
                "scope_id": session_id,
                "source_refs": [ref],
            },
        )
        assert attach_response.status_code == 200, attach_response.text
        assert attach_response.json()["passage_count"] == 1

    finally:
        app.dependency_overrides.clear()


def test_api_compact_source_evidence_uses_real_v3_archive(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos-v3",
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
    )
    compact_service = MemoryOSService(store=create_store(settings), settings=settings)
    compact_service.store.reset()
    app.dependency_overrides[get_service] = lambda: compact_service
    client = TestClient(app)
    try:
        session_id = client.post("/sessions", json={"title": "compact-v3"}).json()["id"]
        source_ref = {
            "source_type": "document",
            "source_id": "activity-api",
            "session_id": session_id,
        }
        assert (
            client.post(
                "/archives/ingest",
                json={
                    "document_id": "xmuse-room-activity-api",
                    "title": "Grounded Room activity",
                    "content": "Project Helios launches in Lisbon.",
                    "source_refs": [source_ref],
                    "identity": {"kind": "archive", "archive_id": "room-archive-api"},
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/archives/attachments",
                json={
                    "archive_id": "room-archive-api",
                    "scope_type": "session",
                    "scope_id": session_id,
                    "source_refs": [source_ref],
                },
            ).status_code
            == 200
        )

        response = client.post(
            f"/sessions/{session_id}/build-context",
            json={
                "task": "Where does Project Helios launch?",
                "budget": 500,
                "response_profile": "source_evidence/v1",
            },
        )
        assert response.status_code == 200, response.text
        compact = response.json()
        assert compact["schema"] == "memoryos_source_evidence/v1"
        assert len(compact["items"]) == 1
        assert compact["items"][0]["archive_id"] == "room-archive-api"
        assert compact["items"][0]["document_id"] == "xmuse-room-activity-api"
        assert compact["items"][0]["source_refs"] == [
            {"source_type": "document", "source_id": "activity-api"}
        ]
        assert set(compact["items"][0]) == {
            "item_id",
            "archive_id",
            "document_id",
            "source_refs",
            "text",
            "estimated_tokens",
            "content_sha256",
            "score",
            "rank",
            "truncated",
        }
    finally:
        app.dependency_overrides.clear()
