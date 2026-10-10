import pytest
from sqlalchemy.exc import IntegrityError

from memoryos_eval.memory.store import MemoryStore, create_store
from memoryos_eval.memory.store_archive import ArchiveStoreMixin
from memoryos_eval.memory.store_legacy import LegacyStoreMixin
from memoryos_eval.memory.store_runtime import StoreRuntimeMixin
from memoryos_eval.memory.store_sessions import SessionStoreMixin
from memoryos_eval.memory.v3_contracts import ArchivalChunk, ArchivalDocument, SourceRef
from memoryos_lite.config import Settings


def test_memory_store_is_a_thin_composition_with_stable_public_type_identity() -> None:
    assert issubclass(
        MemoryStore,
        (StoreRuntimeMixin, SessionStoreMixin, ArchiveStoreMixin, LegacyStoreMixin),
    )
    assert "create_session" not in MemoryStore.__dict__
    assert "create_archival_document" not in MemoryStore.__dict__
    assert "save_page" not in MemoryStore.__dict__


def test_archive_ingest_rolls_back_every_row_when_commit_fails(tmp_path) -> None:
    store = create_store(Settings(data_dir=tmp_path / "data"))
    source_refs = [SourceRef(source_type="document", source_id="source_atomic")]
    store.create_archival_chunk(
        ArchivalChunk(
            id="achunk_existing",
            document_id="adoc_seed",
            archive_id="archive_atomic",
            text="seed",
            start=0,
            end=4,
            source_refs=source_refs,
        )
    )
    document = ArchivalDocument(
        id="adoc_must_rollback",
        archive_id="archive_atomic",
        title="Atomic ingest",
        text="new",
        source_refs=source_refs,
    )
    conflicting_chunk = ArchivalChunk(
        id="achunk_existing",
        document_id=document.id,
        archive_id="archive_atomic",
        text="new",
        start=0,
        end=3,
        source_refs=source_refs,
    )

    with pytest.raises(IntegrityError):
        store.create_archival_ingest_records(
            document=document,
            chunks=[conflicting_chunk],
            passages=[],
        )

    assert store.get_archival_document(document.id) is None
    assert [chunk.document_id for chunk in store.list_archival_chunks()] == ["adoc_seed"]
