import pytest

from memoryos_lite.archive_rag import (
    ArchiveParsedDocument,
    ArchiveRAGDiagnostic,
    ArchiveRAGIngestRequest,
    ArchiveTextSpan,
    MemoryOSArchiveRAG,
)
from memoryos_lite.config import Settings
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import SourceRef, SourceSpan


def _store(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )
    store = MemoryStore(settings)
    store.init_db()
    return store


def _ref(source_id: str = "msg_1") -> SourceRef:
    return SourceRef(source_type="message", source_id=source_id, session_id="ses_1")


class ExternalParser:
    def __init__(self) -> None:
        self.seen_content: list[str | bytes] = []

    def parse(self, request: ArchiveRAGIngestRequest) -> ArchiveParsedDocument:
        self.seen_content.append(request.content)
        return ArchiveParsedDocument(
            text="Alpha beta. Gamma delta.",
            metadata={"parser": "external"},
        )


class ExternalSplitter:
    def split(self, document: ArchiveParsedDocument) -> list[ArchiveTextSpan]:
        return [
            ArchiveTextSpan(
                text="Alpha beta",
                start=0,
                end=10,
                metadata={"splitter": "external", "ordinal": 0},
            ),
            ArchiveTextSpan(
                text="Gamma delta",
                start=12,
                end=23,
                metadata={"splitter": "external", "ordinal": 1},
            ),
        ]


class CapturingIndexer:
    def __init__(self) -> None:
        self.indexed_ids: list[str] = []
        self.indexed_source_ids: list[str | None] = []

    def index_passages(self, passages):
        self.indexed_ids.extend(passage.id for passage in passages)
        self.indexed_source_ids.extend(passage.source_refs[0].source_id for passage in passages)
        return [
            ArchiveRAGDiagnostic(
                event_type="archive_indexed",
                reason_code="test_indexer",
                item_id=passages[0].id,
            )
        ]


def test_archive_rag_boundary_uses_adapters_but_persists_memoryos_archival_records(tmp_path):
    store = _store(tmp_path)
    parser = ExternalParser()
    indexer = CapturingIndexer()
    service = MemoryOSArchiveRAG(
        store,
        parser=parser,
        splitter=ExternalSplitter(),
        indexer=indexer,
    )
    ref = _ref("msg_source")

    result = service.ingest(
        ArchiveRAGIngestRequest(
            document_id="adoc_external",
            archive_id="archive_external",
            title="External document",
            content=b"raw external bytes",
            source_refs=[ref],
            source_id="source_external",
            file_id="file_external",
            tags=["manual"],
            metadata={"tenant": "test"},
        )
    )

    assert parser.seen_content == [b"raw external bytes"]
    assert result.document.id == "adoc_external"
    assert result.document.text == "Alpha beta. Gamma delta."
    assert result.document.source_refs == [ref]
    assert result.document.metadata["tenant"] == "test"
    assert result.document.metadata["parser_metadata"] == {"parser": "external"}
    assert [chunk.id for chunk in result.chunks] == [
        "achunk_adoc_external_0000",
        "achunk_adoc_external_0001",
    ]
    assert [passage.id for passage in result.passages] == [
        "apsg_adoc_external_0000",
        "apsg_adoc_external_0001",
    ]
    assert [passage.source_refs[0].source_id for passage in result.passages] == [
        "msg_source",
        "msg_source",
    ]
    assert [passage.citation.start for passage in result.passages] == [0, 12]
    assert [passage.citation.end for passage in result.passages] == [10, 23]
    assert [passage.source_refs[0].span for passage in result.passages] == [
        SourceSpan(start=0, end=10),
        SourceSpan(start=12, end=23),
    ]
    assert [passage.source_refs[0].quote for passage in result.passages] == [
        "Alpha beta",
        "Gamma delta",
    ]
    assert indexer.indexed_ids == [
        "apsg_adoc_external_0000",
        "apsg_adoc_external_0001",
    ]
    assert indexer.indexed_source_ids == ["msg_source", "msg_source"]
    assert result.diagnostics[0].event_type == "archive_indexed"

    assert store.get_archival_document("adoc_external") == result.document
    assert store.list_archival_chunks(document_id="adoc_external") == result.chunks
    assert store.list_archival_passages(archive_id="archive_external") == result.passages


class BadSplitter:
    def split(self, document: ArchiveParsedDocument) -> list[ArchiveTextSpan]:
        return [ArchiveTextSpan(text="wrong", start=0, end=5)]


def test_archive_rag_boundary_rejects_invalid_splitter_spans_before_sqlite_write(tmp_path):
    store = _store(tmp_path)
    service = MemoryOSArchiveRAG(
        store,
        parser=ExternalParser(),
        splitter=BadSplitter(),
    )

    with pytest.raises(ValueError, match="splitter span text must match document text"):
        service.ingest(
            ArchiveRAGIngestRequest(
                document_id="adoc_bad",
                archive_id="archive_bad",
                title="Bad external document",
                content="raw text",
                source_refs=[_ref()],
            )
        )

    assert store.get_archival_document("adoc_bad") is None
    assert store.list_archival_chunks(document_id="adoc_bad") == []
    assert store.list_archival_passages(archive_id="archive_bad") == []


def test_archive_rag_boundary_rolls_back_document_and_chunks_when_passage_write_fails(tmp_path):
    store = _store(tmp_path)
    service = MemoryOSArchiveRAG(
        store,
        parser=ExternalParser(),
        splitter=ExternalSplitter(),
    )

    with pytest.raises(ValueError, match="require archive_id, source_id, or file_id"):
        service.ingest(
            ArchiveRAGIngestRequest(
                document_id="adoc_partial",
                archive_id=None,
                source_id=None,
                file_id=None,
                title="Partial external document",
                content="raw text",
                source_refs=[_ref()],
            )
        )

    assert store.get_archival_document("adoc_partial") is None
    assert store.list_archival_chunks(document_id="adoc_partial") == []
    assert store.list_archival_passages() == []


def test_archive_rag_boundary_allows_file_only_source_ingest(tmp_path):
    store = _store(tmp_path)
    service = MemoryOSArchiveRAG(
        store,
        parser=ExternalParser(),
        splitter=ExternalSplitter(),
    )

    result = service.ingest(
        ArchiveRAGIngestRequest(
            document_id="adoc_file_only",
            archive_id=None,
            source_id=None,
            file_id="file_external",
            title="File-only external document",
            content="raw text",
            source_refs=[_ref()],
        )
    )

    assert result.document.file_id == "file_external"
    assert [passage.file_id for passage in result.passages] == [
        "file_external",
        "file_external",
    ]
    assert [passage.id for passage in store.list_archival_passages(file_id="file_external")] == [
        "apsg_adoc_file_only_0000",
        "apsg_adoc_file_only_0001",
    ]
