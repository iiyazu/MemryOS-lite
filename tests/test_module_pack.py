"""module_pack/v1: deterministic, bounded resume pack for a module owner."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.module_pack import ModulePackError, build_module_pack
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveDocumentIngestRequest,
    ArchiveIdentityArchive,
    ArchiveSourceRefPayload,
    SessionScope,
)
from memoryos_lite.store import create_store

ARCHIVE = "xmuse-module-auth"
SCOPE = SessionScope(type="module", id="auth")


def _service(tmp_path) -> MemoryOSService:
    settings = Settings(data_dir=tmp_path / "memoryos", memoryos_embedding_provider="none")
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


def _document(service: MemoryOSService, document_id: str, text: str, **metadata) -> None:
    service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id=document_id,
            title=document_id,
            content=text,
            source_refs=[ArchiveSourceRefPayload(source_type="document", source_id=document_id)],
            identity=ArchiveIdentityArchive(kind="archive", archive_id=ARCHIVE),
            metadata=metadata,
        )
    )


def _module_session(service: MemoryOSService) -> str:
    session = service.create_session("auth owner", scope=SCOPE)
    service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id=ARCHIVE,
            scope_type="session",
            scope_id=session.id,
            source_refs=[ArchiveSourceRefPayload(source_type="document", source_id="binding")],
        )
    )
    return session.id


def _seed(service: MemoryOSService) -> None:
    _document(
        service,
        "act-c1",
        "auth-api v1\nPOST /login returns {token, expires_in}",
        activity_type="contract_revision",
        contract_id="auth-api",
        contract_version=1,
    )
    _document(
        service,
        "act-c2",
        "auth-api v2\nPOST /login returns {token, refresh_token}",
        activity_type="contract_revision",
        contract_id="auth-api",
        contract_version=2,
        contract_summary="auth-api v2: login returns token and refresh_token",
    )
    _document(
        service,
        "cand-d1",
        "Tokens are stored in Redis.",
        memory_kind="decision",
        topic_key="auth.token_store",
        version=10,
    )
    _document(
        service,
        "cand-d2",
        "Tokens are stored in Postgres.",
        memory_kind="decision",
        topic_key="auth.token_store",
        version=30,
    )
    _document(
        service,
        "cand-l1",
        "Take the per-user lock before refreshing a token.",
        memory_kind="lesson",
        topic_key="auth.refresh_lock",
        version=25,
        occurrences=1,
    )
    _document(
        service,
        "cand-l1b",
        "Take the per-user lock before refreshing; it failed CI twice.",
        memory_kind="lesson",
        topic_key="auth.refresh_lock",
        version=40,
        occurrences=2,
    )
    _document(
        service,
        "cand-l2",
        "Never log raw tokens.",
        memory_kind="lesson",
        topic_key="auth.no_token_logs",
        version=35,
        occurrences=1,
    )


def test_pack_keeps_current_contract_pointer_and_newest_memories(tmp_path):
    service = _service(tmp_path)
    session_id = _module_session(service)
    _seed(service)

    pack = service.build_module_pack(session_id)

    assert pack["schema"] == "memoryos_module_pack/v1"
    assert pack["scope"] == {"type": "module", "id": "auth"}
    (contract,) = pack["sections"]["contracts"]
    assert (contract["contract_id"], contract["version"], contract["document_id"]) == (
        "auth-api",
        2,
        "act-c2",
    )
    assert contract["summary"] == "auth-api v2: login returns token and refresh_token"
    assert "text" not in contract  # contracts are pointers only
    lessons = pack["sections"]["lessons"]
    assert [(item["document_id"], item["occurrences"]) for item in lessons] == [
        ("cand-l1b", 2),
        ("cand-l2", 1),
    ]
    assert [item["document_id"] for item in pack["sections"]["decisions"]] == ["cand-d2"]
    assert pack["truncated"] is False
    assert pack["diagnostics"]["conflict_check"] == "unavailable"
    # Deterministic: the same inputs give the same digest.
    assert service.build_module_pack(session_id)["diagnostics_digest"] == pack["diagnostics_digest"]
    events = [
        e for e in service.store.list_traces(session_id) if e.event_type == "module_pack_built"
    ]
    assert events and events[-1].payload["items"] == {"contracts": 1, "lessons": 2, "decisions": 1}


def test_budget_fills_contracts_then_lessons_then_decisions(tmp_path):
    service = _service(tmp_path)
    session_id = _module_session(service)
    _seed(service)

    pack = service.build_module_pack(session_id, budget=30)

    assert pack["sections"]["contracts"]
    assert pack["estimated_tokens"] <= 30
    assert pack["truncated"] is True
    assert pack["omitted"]["decisions"] >= 1


def test_pack_requires_a_module_session_and_a_bounded_budget(tmp_path):
    service = _service(tmp_path)
    room = service.create_session("room")
    with pytest.raises(ModulePackError):
        service.build_module_pack(room.id)
    with pytest.raises(ModulePackError):
        build_module_pack(scope=SCOPE, documents=[], budget=4001)


def test_possible_conflicts_are_marked_between_different_topic_keys(tmp_path):
    service = _service(tmp_path)
    session_id = _module_session(service)
    _seed(service)
    documents = service.store.list_archival_documents_for_archives([ARCHIVE])
    vectors = {
        "Tokens are stored in Postgres.": [1.0, 0.0],
        "Take the per-user lock before refreshing; it failed CI twice.": [0.0, 1.0],
        "Never log raw tokens.": [0.99, 0.1],
    }

    pack = build_module_pack(
        scope=SCOPE,
        documents=documents,
        embed_batch=lambda texts: [vectors[text] for text in texts],
        conflict_threshold=0.9,
    )

    by_id = {
        item["document_id"]: item
        for item in pack["sections"]["lessons"] + pack["sections"]["decisions"]
    }
    assert by_id["cand-d2"]["possible_conflict_with"] == ["cand-l2"]
    assert "possible_conflict_with" not in by_id["cand-l1b"]
    assert pack["diagnostics"] == {"conflict_check": "fastembed", "conflict_threshold": 0.9}
    del session_id


def test_api_serves_module_pack_and_rejects_bad_requests(tmp_path):
    service = _service(tmp_path)
    session_id = _module_session(service)
    _seed(service)
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        ok = client.post(
            f"/sessions/{session_id}/build-context",
            json={"task": "resume", "response_profile": "module_pack/v1"},
        )
        assert ok.status_code == 200 and ok.json()["schema"] == "memoryos_module_pack/v1"
        too_big = client.post(
            f"/sessions/{session_id}/build-context",
            json={"task": "resume", "response_profile": "module_pack/v1", "budget": 5000},
        )
        assert too_big.status_code == 422
        room = client.post("/sessions", json={"title": "room"}).json()["id"]
        not_module = client.post(
            f"/sessions/{room}/build-context",
            json={"task": "resume", "response_profile": "module_pack/v1"},
        )
        assert not_module.status_code == 422
        health = client.get("/health").json()
        assert "module_pack/v1" in health["capabilities"]["build_context_profiles"]
    finally:
        app.dependency_overrides.pop(get_service, None)
