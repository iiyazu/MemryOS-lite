from fastapi.testclient import TestClient

from memoryos_eval.memory.service import SessionMemoryService
from memoryos_lite import __version__
from memoryos_lite.api.app import app
from memoryos_lite.config import Settings
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveDocumentIngestRequest,
)
from memoryos_lite.source_evidence import build_source_evidence
from memoryos_lite.store import create_store

#: The whole HTTP surface since MO-10: the hub sends every fact it needs.
STATELESS_PATHS = {"/health", "/curate", "/recall", "/similar"}


def test_http_surface_is_stateless():
    client = TestClient(app)

    assert set(app.openapi()["paths"]) == STATELESS_PATHS
    assert client.post("/sessions", json={"title": "x"}).status_code == 404
    assert client.post("/archives/ingest", json={}).status_code == 404


def test_health_lists_capabilities_only():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "version", "capabilities"}
    assert payload["status"] == "ok"
    assert payload["version"] == __version__ == app.version
    assert "recall" in payload["capabilities"]


def test_compact_source_evidence_uses_a_real_v3_archive(tmp_path):
    # In process only (the evaluation harness): the session and archive
    # store has no HTTP route any more.
    settings = Settings(
        data_dir=tmp_path / ".memoryos-v3",
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
    )
    service = SessionMemoryService(store=create_store(settings), settings=settings)
    service.store.reset()
    session_id = service.create_session("compact-v3").id
    source_ref = {"source_type": "document", "source_id": "activity-api", "session_id": session_id}
    service.ingest_archive_document(
        ArchiveDocumentIngestRequest.model_validate(
            {
                "document_id": "xmuse-room-activity-api",
                "title": "Grounded Room activity",
                "content": "Project Helios launches in Lisbon.",
                "source_refs": [source_ref],
                "identity": {"kind": "archive", "archive_id": "room-archive-api"},
            }
        )
    )
    attached = service.attach_archive(
        ArchiveAttachmentRequest.model_validate(
            {
                "archive_id": "room-archive-api",
                "scope_type": "session",
                "scope_id": session_id,
                "source_refs": [source_ref],
            }
        )
    )
    assert attached.passage_count == 1

    compact = build_source_evidence(
        service.build_context(session_id, "Where does Project Helios launch?", budget=500)
    )

    assert compact["schema"] == "memoryos_source_evidence/v1"
    assert len(compact["items"]) == 1
    item = compact["items"][0]
    assert (item["archive_id"], item["document_id"]) == (
        "room-archive-api",
        "xmuse-room-activity-api",
    )
    assert item["source_refs"] == [{"source_type": "document", "source_id": "activity-api"}]
    assert set(item) == {
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
