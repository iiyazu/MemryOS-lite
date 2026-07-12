import pytest

from memoryos_lite.config import Settings
from memoryos_lite.schemas import Message, Role
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalDocument,
    ArchivalMemory,
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


def test_archival_passage_listing_supports_pagination_and_total(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    for index in range(3):
        store.create_archival_passage(
            ArchivalPassage(
                id=f"apsg_{index}",
                archive_id="archive_page",
                text=f"passage {index}",
                source_refs=[ref],
            )
        )

    page = store.list_archival_passages_page(archive_id="archive_page", limit=2, offset=1)

    assert page.total == 3
    assert [passage.id for passage in page.passages] == ["apsg_1", "apsg_2"]
    assert page.limit == 2
    assert page.offset == 1


def test_archival_passage_listing_filters_by_producer_metadata(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_agent",
            archive_id="archive_1",
            text="agent passage",
            source_refs=[ref],
            metadata={"producer": "xmuse_review_agent"},
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_manual",
            archive_id="archive_1",
            text="manual passage",
            source_refs=[ref],
            metadata={"producer": "manual"},
        )
    )

    page = store.list_archival_passages_page(
        archive_id="archive_1",
        producer="xmuse_review_agent",
    )

    assert page.total == 1
    assert [passage.id for passage in page.passages] == ["apsg_agent"]


def test_archival_memory_crud_records_history_and_rejects_sourceless_writes(tmp_path):
    store = _store(tmp_path)
    ref = _ref()

    with pytest.raises(ValueError):
        store.add_archival_memory(
            ArchivalMemory(
                id="amem_bad",
                memory_type="fact",
                content="No provenance.",
            ),
            actor="agent",
            reason="bad write",
        )

    memory = store.add_archival_memory(
        ArchivalMemory(
            id="amem_1",
            archive_id="archive_1",
            memory_type="fact",
            content="Alice lives in Shanghai.",
            source_refs=[ref],
        ),
        actor="agent",
        reason="message extraction",
    )
    updated = store.update_archival_memory(
        memory.id,
        content="Alice lives in Suzhou.",
        source_refs=[ref],
        actor="agent",
        reason="user correction",
    )
    deleted = store.delete_archival_memory(
        memory.id,
        source_refs=[ref],
        actor="agent",
        reason="obsolete",
    )
    history = store.list_archival_memory_history(memory.id)

    assert updated is not None
    assert updated.content == "Alice lives in Suzhou."
    assert deleted is not None
    assert deleted.deleted_at is not None
    assert [event.operation for event in history] == ["add", "update", "delete"]


def test_archival_producer_helpers_preserve_message_source_refs(tmp_path):
    store = _store(tmp_path)
    message = Message(
        id="msg_1",
        session_id="ses_1",
        role=Role.USER,
        content="Alice moved to Shanghai.",
    )

    document = store.create_archival_document_from_message(
        message,
        archive_id="archive_1",
        title="message extract",
    )
    passage = store.create_archival_passage_from_document(
        document,
        text="Alice moved to Shanghai.",
        source_refs=document.source_refs,
    )
    memory = store.create_archival_memory_from_consolidation(
        content="Alice moved to Shanghai.",
        memory_type="event",
        archive_id="archive_1",
        source_refs=passage.source_refs,
    )

    assert document.producer == "message"
    assert passage.source_refs[0].source_id == "msg_1"
    assert memory.source_refs[0].source_id == "msg_1"


def test_archival_passage_from_document_uses_text_offset_for_citation(tmp_path):
    store = _store(tmp_path)
    message = Message(
        id="msg_1",
        session_id="ses_1",
        role=Role.USER,
        content="prefix Alice moved to Shanghai suffix",
    )
    document = store.create_archival_document_from_message(
        message,
        archive_id="archive_1",
        title="message extract",
    )

    passage = store.create_archival_passage_from_document(
        document,
        text="Alice moved to Shanghai",
        source_refs=document.source_refs,
    )

    assert passage.citation == SourceSpan(start=7, end=30)


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
