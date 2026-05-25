import pytest
from pydantic import ValidationError

from memoryos_lite.schemas import ArchiveDocumentIngestRequest, ArchiveSourceRefPayload


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
