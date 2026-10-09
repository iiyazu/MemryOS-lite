import re
import time

from fastapi.testclient import TestClient

from memoryos_lite.api import app as api_app_module
from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.curator import Curator
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ContextPackage, Role
from memoryos_lite.store import create_store
from memoryos_lite.store_curator import CuratedMemoryWrite
from memoryos_lite.v3_contracts import (
    ContextLayerItem,
    ContextPackageV3,
    SourceRef,
    SourceType,
)


class _EchoCuratorLLM:
    """Returns one grounded memory for the first message of the window prompt."""

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        window = user.split("Messages to curate:\n", 1)[1]
        match = re.match(r"\[([^\]]+)\] .+ \(message\): (.+)", window.strip().splitlines()[0])
        assert match is not None
        message_id, content = match.group(1), match.group(2)
        return {
            "memories": [
                {
                    "kind": "fact",
                    "topic_key": "api.test",
                    "statement": content,
                    "sources": [{"activity_id": message_id, "quote": content}],
                }
            ]
        }


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


def test_api_advisories_serves_v2_only(service):
    session = service.create_session("advisories-routing")
    statement = "Helios launches in Lisbon."
    service.store.apply_curator_window(
        session_id=session.id,
        run_id="crun_api",
        model="test-model",
        last_message_seq=0,
        writes=[
            CuratedMemoryWrite(
                kind="decision",
                topic_key="project.launch_city",
                statement=statement,
                sources=[{"message_id": "msg_api", "quote": statement}],
            )
        ],
    )
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        for params in ({}, {"version": 1}):
            v1 = client.get(f"/sessions/{session.id}/advisories", params=params)
            assert v1.status_code == 400

        v2 = client.get(f"/sessions/{session.id}/advisories", params={"version": 2})
        assert v2.status_code == 200
        assert v2.json()["schema"] == "memoryos_external_advisories/v2"
        items = v2.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert set(item) == {
            "advisory_id",
            "fingerprint",
            "proposal_type",
            "kind",
            "topic_key",
            "content",
            "source_refs",
            "supersedes_advisory_id",
        }
        assert item["proposal_type"] == "curated_memory"
        assert item["kind"] == "room_decision"
        assert item["content"] == statement
        assert item["supersedes_advisory_id"] is None
        assert item["source_refs"] == [
            {
                "source_type": "message",
                "source_id": "msg_api",
                "session_id": session.id,
                "quote": statement,
            }
        ]
        assert len(item["fingerprint"]) == 64

        unsupported = client.get(f"/sessions/{session.id}/advisories", params={"version": 4})
        assert unsupported.status_code == 400
        assert "unsupported advisories version" in unsupported.json()["detail"]

        missing = client.get("/sessions/sess_absent/advisories", params={"version": 2})
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_health_reports_curator_disabled_by_default():
    client = TestClient(app)
    curator_block = client.get("/health").json()["curator"]

    assert curator_block["enabled"] is False
    assert curator_block["state"] == "disabled"
    assert curator_block["reason_code"] == "curator_disabled"
    assert isinstance(curator_block["model"], str)
    assert curator_block["counters"] == {
        "sessions": 0,
        "runs": 0,
        "proposals": 0,
        "rejected_grounding": 0,
        "rejected_schema": 0,
        "llm_errors": 0,
    }


def test_health_reports_curator_degraded_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = Settings(
        data_dir=tmp_path / "curator-health",
        memoryos_curator_enabled=True,
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=None)
    service = MemoryOSService(store=store, settings=settings, curator=curator)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        curator_block = client.get("/health").json()["curator"]

        assert curator_block["enabled"] is True
        assert curator_block["state"] == "degraded"
        assert curator_block["reason_code"] == "curator_llm_key_missing"
        assert "key" not in str(curator_block["counters"])
    finally:
        app.dependency_overrides.clear()


def test_curator_never_exposes_api_key(tmp_path):
    secret = "sk-test-curator-secret-value"
    settings = Settings(
        data_dir=tmp_path / "curator-secret",
        memoryos_curator_enabled=True,
        memoryos_curator_window_messages=1,
        openai_api_key=secret,
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=_EchoCuratorLLM())
    service = MemoryOSService(store=store, settings=settings, curator=curator)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        session_id = client.post("/sessions", json={"title": "secret"}).json()["id"]
        content = "A durable fact that must not leak credentials."
        client.post(
            f"/sessions/{session_id}/ingest",
            json={"role": Role.USER.value, "content": content},
        )
        assert curator.run_session(session_id).added == 1

        health_body = client.get("/health").text
        v1_body = client.get(f"/sessions/{session_id}/advisories").text
        v2_body = client.get(f"/sessions/{session_id}/advisories", params={"version": 2}).text
        trace_body = str([event.payload for event in service.store.list_traces(session_id)])

        assert secret not in health_body
        assert secret not in v1_body
        assert secret not in v2_body
        assert secret not in trace_body
    finally:
        app.dependency_overrides.clear()


def test_curator_worker_not_started_when_disabled(service):
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert app.state.curator_worker is None
        assert app.state.curator_worker is None
    finally:
        app.dependency_overrides.clear()


def test_curator_worker_serves_advisories_v2_when_enabled(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "curator-worker",
        memoryos_curator_enabled=True,
        memoryos_curator_window_messages=1,
        memoryos_curator_poll_s=0.05,
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=_EchoCuratorLLM())
    service = MemoryOSService(store=store, settings=settings, curator=curator)
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            worker = app.state.curator_worker
            assert worker is not None
            assert worker.running

            session_id = client.post("/sessions", json={"title": "worker"}).json()["id"]
            content = "The worker curates this durable launch fact."
            client.post(
                f"/sessions/{session_id}/ingest",
                json={"role": Role.USER.value, "content": content},
            )

            deadline = time.monotonic() + 5.0
            items: list[dict] = []
            while time.monotonic() < deadline:
                items = client.get(
                    f"/sessions/{session_id}/advisories", params={"version": 2}
                ).json()["items"]
                if items:
                    break
                time.sleep(0.05)

            assert items, "worker did not curate the message in time"
            assert items[0]["content"] == content
            assert items[0]["source_refs"][0]["source_type"] == "message"

        assert not worker.running
        assert app.state.curator_worker is None
    finally:
        app.dependency_overrides.clear()
