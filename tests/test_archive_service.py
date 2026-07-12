import pytest
from pydantic import ValidationError

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveDocumentIngestRequest,
    ArchiveSourceRefPayload,
)
from memoryos_lite.store import create_store


def _ref() -> dict[str, str]:
    return {"source_type": "document", "source_id": "doc_source"}


def test_archive_ingest_request_requires_exactly_one_identity_route() -> None:
    request = ArchiveDocumentIngestRequest(
        document_id="adoc_1",
        title="Spec",
        content="Project Helios launches in Lisbon.",
        source_refs=[_ref()],
        identity={"kind": "archive", "archive_id": "archive_1"},
    )

    assert request.identity.kind == "archive"
    assert request.identity.archive_id == "archive_1"

    with pytest.raises(ValidationError) as exc_info:
        ArchiveDocumentIngestRequest(
            document_id="adoc_bad",
            title="Bad",
            content="Bad",
            source_refs=[_ref()],
            identity={
                "kind": "archive",
                "archive_id": "archive_1",
                "source_id": "src_1",
            },
        )
    assert "source_id" in str(exc_info.value)
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_archive_source_ref_payload_validates_manual_approval() -> None:
    with pytest.raises(ValidationError, match="manual source refs require approval_id"):
        ArchiveSourceRefPayload(source_type="manual", source_id="manual_1")

    ref = ArchiveSourceRefPayload(
        source_type="manual",
        source_id="manual_1",
        approval_id="approval_1",
    )
    assert ref.approval_id == "approval_1"


def _service(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


def test_service_archive_ingest_attach_and_context_preserve_source_span_quote(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("archive-service")
    ref = {"source_type": "document", "source_id": "doc_1", "session_id": session.id}

    ingest = service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_service",
            title="Service doc",
            content="Project Helios launches in Lisbon.",
            source_refs=[ref],
            identity={"kind": "archive", "archive_id": "archive_service"},
        )
    )
    attachment = service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id="archive_service",
            scope_type="session",
            scope_id=session.id,
            source_refs=[ref],
        )
    )
    context = service.build_context(
        session.id,
        "Where does Project Helios launch?",
        budget=120,
    )

    assert len(ingest.passage_ids) == 1
    passage_id = ingest.passage_ids[0]
    assert passage_id.startswith("apsg_")
    assert attachment.passage_count == 1
    archival = [
        item for item in context.metadata["v3_context"]["items"] if item["layer"] == "archival"
    ]
    assert archival[0]["item_id"] == passage_id
    assert archival[0]["source_refs"][0]["span"] == {"start": 0, "end": 34}
    assert archival[0]["source_refs"][0]["quote"] == "Project Helios launches in Lisbon."


def test_service_archive_ingest_is_idempotent_for_same_document(tmp_path):
    service = _service(tmp_path)
    ref = {"source_type": "document", "source_id": "doc_1"}
    request = ArchiveDocumentIngestRequest(
        document_id="adoc_replay",
        title="Replay",
        content="Replay-safe content.",
        source_refs=[ref],
        identity={"kind": "archive", "archive_id": "archive_replay"},
    )

    first = service.ingest_archive_document(request)
    second = service.ingest_archive_document(request)

    assert first.passage_ids == second.passage_ids
    assert second.diagnostics[0].reason_code == "archive_ingest_idempotent_replay"


def test_service_archive_ingest_rejects_conflicting_document_id(tmp_path):
    service = _service(tmp_path)
    ref = {"source_type": "document", "source_id": "doc_1"}
    service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_conflict",
            title="Conflict",
            content="Original content.",
            source_refs=[ref],
            identity={"kind": "archive", "archive_id": "archive_conflict"},
        )
    )

    with pytest.raises(ValueError, match="archive document conflict"):
        service.ingest_archive_document(
            ArchiveDocumentIngestRequest(
                document_id="adoc_conflict",
                title="Conflict",
                content="Changed content.",
                source_refs=[ref],
                identity={"kind": "archive", "archive_id": "archive_conflict"},
            )
        )


def test_service_file_only_archive_ingest_can_be_listed(tmp_path):
    service = _service(tmp_path)
    ref = {"source_type": "document", "source_id": "doc_file"}

    ingest = service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_file",
            title="File scoped archive",
            content="File-only archive content.",
            source_refs=[ref],
            identity={"kind": "file", "file_id": "file_1"},
            producer="xmuse_review_agent",
        )
    )
    page = service.list_archive_passages(
        file_id="file_1",
        producer="xmuse_review_agent",
        limit=10,
        offset=0,
    )

    assert len(ingest.passage_ids) == 1
    assert ingest.passage_ids[0].startswith("apsg_")
    assert page.total == 1
    assert page.passages[0].file_id == "file_1"
    assert page.passages[0].metadata["producer"] == "xmuse_review_agent"


def test_service_archive_context_reports_lexical_fallback_without_qdrant(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("archive-no-qdrant")
    ref = {
        "source_type": "document",
        "source_id": "doc_no_qdrant",
        "session_id": session.id,
    }
    ingest = service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_no_qdrant",
            title="No Qdrant doc",
            content="Shanghai rail lexical fallback.",
            source_refs=[ref],
            identity={"kind": "archive", "archive_id": "archive_no_qdrant"},
        )
    )
    service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id="archive_no_qdrant",
            scope_type="session",
            scope_id=session.id,
            source_refs=[ref],
        )
    )

    context = service.build_context(session.id, "Shanghai rail", budget=120)

    archival = [
        item for item in context.metadata["v3_context"]["items"] if item["layer"] == "archival"
    ]
    event_types = {row["event_type"] for row in context.metadata["v3_component_accounting"]}
    assert archival[0]["item_id"] == ingest.passage_ids[0]
    assert "archival_vector_unavailable" in event_types
    assert "archival_lexical_fallback" in event_types
