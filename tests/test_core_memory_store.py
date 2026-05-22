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
        read_only=True,
        tags=["profile", "source-backed"],
        metadata={"scope": "human"},
    )

    created = store.create_core_memory_block(block)
    assert created.id == "core_1"
    assert created.read_only is True
    assert created.tags == ["profile", "source-backed"]
    assert store.get_core_memory_block("core_1").value == "Alice lives in Shanghai."
    loaded = store.get_core_memory_block("core_1")
    assert loaded is not None
    assert loaded.read_only is True
    assert loaded.tags == ["profile", "source-backed"]

    history = store.list_core_memory_history("core_1")
    assert history[-1].operation == "add"
    add_event = history[-1]
    assert add_event.after["read_only"] is True
    assert add_event.after["tags"] == ["profile", "source-backed"]

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
    assert version == "0007_add_core_block_read_only_tags"


def test_init_db_upgrades_existing_core_memory_schema_before_stamping_head(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.settings.data_dir.mkdir(parents=True, exist_ok=True)
    with store.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE core_memory_blocks (
                    id VARCHAR(64) NOT NULL PRIMARY KEY,
                    label VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    value TEXT DEFAULT '' NOT NULL,
                    limit_tokens INTEGER NOT NULL,
                    source_refs_json TEXT DEFAULT '[]' NOT NULL,
                    metadata_json TEXT DEFAULT '{}' NOT NULL,
                    deleted_at DATETIME,
                    deleted_by_event_id VARCHAR(64),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE core_memory_history (
                    id VARCHAR(64) NOT NULL PRIMARY KEY,
                    memory_id VARCHAR(64) NOT NULL,
                    memory_type VARCHAR(32) NOT NULL,
                    operation VARCHAR(32) NOT NULL,
                    actor VARCHAR(16) NOT NULL,
                    reason TEXT NOT NULL,
                    source_refs_json TEXT DEFAULT '[]' NOT NULL,
                    before_json TEXT,
                    after_json TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                )
                """
            )
        )
        conn.execute(
            text("INSERT INTO alembic_version VALUES ('0006_add_archival_memory')")
        )

    store.init_db()

    with store.db() as db:
        columns = {
            row[1] for row in db.execute(text("PRAGMA table_info(core_memory_blocks)"))
        }
        version = db.scalar(text("select version_num from alembic_version limit 1"))

    assert {"read_only", "tags_json"} <= columns
    assert version == "0007_add_core_block_read_only_tags"

    store.create_core_memory_block(
        CoreMemoryBlock(
            id="core_existing",
            label="profile",
            description="Stable user facts",
            value="Alice prefers rail travel.",
            limit_tokens=100,
            source_refs=[SourceRef(source_type="message", source_id="msg_1")],
            read_only=True,
            tags=["profile"],
        )
    )
    loaded = store.get_core_memory_block("core_existing")
    assert loaded is not None
    assert loaded.read_only is True
    assert loaded.tags == ["profile"]
