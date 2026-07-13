import pytest
from sqlalchemy import text

from memoryos_lite.archive_rag import ArchiveRAGIngestRequest, MemoryOSArchiveRAG
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ArchiveDocumentIngestRequest
from memoryos_lite.store import Base, MemoryStore, create_store
from memoryos_lite.store_protocols import ArchiveIngestStore
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalPassage,
    SourceRef,
)


class FakeArchiveIngestStore:
    def __init__(self) -> None:
        self.calls: list[tuple[ArchivalDocument, list[ArchivalChunk], list[ArchivalPassage]]] = []

    def create_archival_ingest_records(
        self,
        *,
        document: ArchivalDocument,
        chunks: list[ArchivalChunk],
        passages: list[ArchivalPassage],
    ) -> tuple[ArchivalDocument, list[ArchivalChunk], list[ArchivalPassage]]:
        self.calls.append((document, chunks, passages))
        return document, chunks, passages


def test_memory_store_structurally_satisfies_archive_ingest_store(tmp_path) -> None:
    store = MemoryStore(Settings(data_dir=tmp_path / "data"))
    store.init_db()

    assert isinstance(store, ArchiveIngestStore)


def test_archive_rag_accepts_a_minimal_archive_ingest_store() -> None:
    store = FakeArchiveIngestStore()
    service = MemoryOSArchiveRAG(store)

    result = service.ingest(
        ArchiveRAGIngestRequest(
            document_id="adoc_protocol",
            archive_id="archive_protocol",
            title="Protocol document",
            content="Protocol-backed archive text.",
            source_refs=[SourceRef(source_type="document", source_id="doc_protocol")],
        )
    )

    assert isinstance(store, ArchiveIngestStore)
    assert [document.id for document, _, _ in store.calls] == ["adoc_protocol"]
    assert [chunk.id for chunk in result.chunks] == ["achunk_adoc_protocol_0000"]
    assert [passage.id for passage in result.passages] == ["apsg_adoc_protocol_0000"]


def test_archive_replay_and_conflict_leave_existing_rows_intact(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    request = ArchiveDocumentIngestRequest(
        document_id="adoc_protocol_replay",
        title="Replay",
        content="Original archive content.",
        source_refs=[{"source_type": "document", "source_id": "doc_protocol"}],
        identity={"kind": "archive", "archive_id": "archive_protocol"},
    )

    first = service.ingest_archive_document(request)
    replay = service.ingest_archive_document(request)
    with pytest.raises(ValueError, match="archive document conflict"):
        service.ingest_archive_document(request.model_copy(update={"content": "Changed."}))

    assert replay.passage_ids == first.passage_ids
    assert store.get_archival_document(request.document_id).text == request.content
    assert [chunk.id for chunk in store.list_archival_chunks(request.document_id)] == (
        first.chunk_ids
    )
    assert [passage.id for passage in store.list_archival_passages("archive_protocol")] == (
        first.passage_ids
    )


def test_protocol_keeps_store_base_and_alembic_head_compatible(tmp_path) -> None:
    store = MemoryStore(Settings(data_dir=tmp_path / "data"))
    store.init_db()

    assert {"archival_documents", "archival_chunks", "archival_passages"} <= set(
        Base.metadata.tables
    )
    with store.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0009_add_context_policy_candidates"
        )
