import pytest

from memoryos_lite.config import Settings
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalPassage,
    ArchiveAttachment,
    ArchiveEligibilityScope,
    SourceRef,
    SourceSpan,
)


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


def test_archival_store_round_trips_documents_chunks_passages_and_attachments(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    document = store.create_archival_document(
        ArchivalDocument(
            id="adoc_1",
            archive_id="archive_1",
            title="Trip notes",
            text="Alice moved to Shanghai and prefers rail travel.",
            source_id="source_1",
            file_id="file_1",
            tags=["travel"],
            source_refs=[ref],
            producer="explicit_document",
        )
    )
    chunk = store.create_archival_chunk(
        ArchivalChunk(
            id="achunk_1",
            document_id=document.id,
            archive_id=document.archive_id,
            text="Alice moved to Shanghai.",
            start=0,
            end=24,
            source_refs=[ref],
        )
    )
    passage = store.create_archival_passage(
        ArchivalPassage(
            id="apsg_1",
            document_id=document.id,
            chunk_id=chunk.id,
            archive_id=document.archive_id,
            text=chunk.text,
            citation=SourceSpan(start=0, end=24),
            tags=["travel"],
            source_refs=[ref],
        )
    )
    attachment = store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_1",
            archive_id="archive_1",
            scope_type="agent",
            scope_id="agent_1",
            source_refs=[ref],
        )
    )

    assert store.get_archival_document(document.id) == document
    assert store.list_archival_chunks(document_id=document.id) == [chunk]
    assert store.list_archival_passages(archive_id="archive_1") == [passage]
    assert store.list_archive_attachments(scope_type="agent", scope_id="agent_1") == [attachment]


def test_archival_store_batch_lookup_rehydrates_passages_by_id(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    first = store.create_archival_passage(
        ArchivalPassage(
            id="apsg_first",
            archive_id="archive_1",
            text="First source-backed archival passage.",
            source_refs=[ref],
        )
    )
    second = store.create_archival_passage(
        ArchivalPassage(
            id="apsg_second",
            archive_id="archive_1",
            text="Second source-backed archival passage.",
            source_refs=[_ref("msg_2")],
        )
    )

    passages = store.get_archival_passages_by_ids(["apsg_second", "apsg_missing", "apsg_first"])

    assert list(passages) == ["apsg_first", "apsg_second"]
    assert passages["apsg_first"] == first
    assert passages["apsg_second"] == second
    assert "apsg_missing" not in passages


def test_archival_passage_invariants_and_attachment_scope_helper(tmp_path):
    store = _store(tmp_path)
    ref = _ref()

    with pytest.raises(ValueError, match="agent/archive passages require archive_id"):
        store.create_archival_passage(
            ArchivalPassage(
                id="apsg_neither",
                text="missing passage identity",
                source_refs=[ref],
            )
        )
    with pytest.raises(ValueError, match="cannot set source_id"):
        store.create_archival_passage(
            ArchivalPassage(
                id="apsg_both",
                archive_id="archive_1",
                source_id="source_1",
                text="mixed passage identity",
                source_refs=[ref],
            )
        )

    archive_passage = store.create_archival_passage(
        ArchivalPassage(
            id="apsg_agent",
            archive_id="archive_1",
            text="Attached archive memory.",
            source_refs=[ref],
        )
    )
    source_passage = store.create_archival_passage(
        ArchivalPassage(
            id="apsg_source",
            source_id="source_1",
            file_id="file_1",
            text="Source file passage.",
            source_refs=[ref],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_other",
            archive_id="archive_2",
            text="Unattached archive memory.",
            source_refs=[ref],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_1",
            archive_id="archive_1",
            scope_type="session",
            scope_id="ses_1",
            source_refs=[ref],
        )
    )

    result = store.list_archival_passages_for_scope(
        ArchiveEligibilityScope(session_id="ses_1", source_ids=["source_1"])
    )

    assert result.eligible_archive_ids == ["archive_1"]
    assert [passage.id for passage in result.eligible_passages] == [
        archive_passage.id,
        source_passage.id,
    ]
    assert result.scope_excluded_passage_ids == ["apsg_other"]
