import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from memoryos_lite.config import Settings
from memoryos_lite.store import ArchivalPassagePage, Base, MemoryStore, create_store
from memoryos_lite.store_archive import ArchiveStoreMixin
from memoryos_lite.store_legacy import LegacyStoreMixin
from memoryos_lite.store_protocols import PromotionMaintenanceStore
from memoryos_lite.store_runtime import StoreRuntimeMixin
from memoryos_lite.store_sessions import SessionStoreMixin
from memoryos_lite.v3_contracts import ArchivalChunk, ArchivalDocument, SourceRef


def test_memory_store_is_a_thin_composition_with_stable_public_type_identity() -> None:
    assert issubclass(
        MemoryStore,
        (StoreRuntimeMixin, SessionStoreMixin, ArchiveStoreMixin, LegacyStoreMixin),
    )
    assert "create_session" not in MemoryStore.__dict__
    assert "create_archival_document" not in MemoryStore.__dict__
    assert "save_page" not in MemoryStore.__dict__
    assert ArchivalPassagePage.__module__ == "memoryos_lite.store"
    assert str(inspect.signature(MemoryStore.list_archival_passages_page)).endswith(
        "-> memoryos_lite.store.ArchivalPassagePage"
    )


def test_promotion_maintenance_store_contract_preserves_schema_and_rolls_back(tmp_path) -> None:
    store = MemoryStore(Settings(data_dir=tmp_path / "data"))
    base_tables = set(Base.metadata.tables)
    store.init_db()

    assert isinstance(store, PromotionMaintenanceStore)
    with pytest.raises(RuntimeError, match="rollback"):
        with store.db() as db:
            db.execute(
                text(
                    "insert into sessions (id, title, created_at) "
                    "values (:id, :title, :created_at)"
                ),
                {
                    "id": "session_rollback",
                    "title": "Rollback",
                    "created_at": "2026-01-01",
                },
            )
            raise RuntimeError("rollback")

    assert store.get_session("session_rollback") is None
    assert set(Base.metadata.tables) == base_tables
    with store.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0009_add_context_policy_candidates"
        )


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
