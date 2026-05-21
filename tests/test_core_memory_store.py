from sqlalchemy import text

from memoryos_lite.config import Settings
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import CoreMemoryBlock, SourceRef


def _settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )


def test_core_memory_store_round_trip_history_and_soft_delete(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()

    block = CoreMemoryBlock(
        id="core_1",
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=100,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )

    created = store.create_core_memory_block(block)
    assert created.id == "core_1"
    assert store.get_core_memory_block("core_1").value == "Alice lives in Shanghai."

    history = store.list_core_memory_history("core_1")
    assert history[-1].operation == "add"

    deleted = store.delete_core_memory_block(
        "core_1",
        source_refs=[SourceRef(source_type="message", source_id="msg_2")],
        actor="agent",
        reason="user requested removal",
    )
    assert deleted.deleted_at is not None
    assert store.get_core_memory_block("core_1") is None
    assert store.get_core_memory_block("core_1", include_deleted=True).deleted_at is not None
    assert store.list_core_memory_history("core_1")[-1].operation == "delete"


def test_init_db_stamps_current_migration_head(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()
    with store.db() as db:
        version = db.scalar(text("select version_num from alembic_version limit 1"))
    assert version == "0006_add_archival_memory"
