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
            source_id="source_1",
            file_id="file_1",
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
    assert store.list_archive_attachments(scope_type="agent", scope_id="agent_1") == [
        attachment
    ]


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
