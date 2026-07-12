import pytest
from sqlalchemy import text

from memoryos_lite.config import Settings
from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import CoreMemoryBlock, SourceRef

CURRENT_ALEMBIC_HEAD = "0009_add_context_policy_candidates"


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

    mutable_block = CoreMemoryBlock(
        id="core_2",
        label="scratch",
        description="Mutable user facts",
        value="Alice temporarily lives in Berlin.",
        limit_tokens=100,
        source_refs=[SourceRef(source_type="message", source_id="msg_2")],
        read_only=False,
    )
    store.create_core_memory_block(mutable_block)

    deleted = store.delete_core_memory_block(
        "core_2",
        source_refs=[SourceRef(source_type="message", source_id="msg_3")],
        actor="agent",
        reason="user requested removal",
    )
    assert deleted.deleted_at is not None
    assert store.get_core_memory_block("core_2") is None
    assert store.get_core_memory_block("core_2", include_deleted=True).deleted_at is not None
    assert store.list_core_memory_history("core_2")[-1].operation == "delete"


def test_init_db_stamps_current_migration_head(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()
    with store.db() as db:
        version = db.scalar(text("select version_num from alembic_version limit 1"))
    assert version == CURRENT_ALEMBIC_HEAD


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
        conn.execute(text("INSERT INTO alembic_version VALUES ('0006_add_archival_memory')"))

    store.init_db()

    with store.db() as db:
        columns = {row[1] for row in db.execute(text("PRAGMA table_info(core_memory_blocks)"))}
        table_names = {
            row[0]
            for row in db.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
        }
        version = db.scalar(text("select version_num from alembic_version limit 1"))

    assert {"read_only", "tags_json"} <= columns
    assert "promotion_candidates" in table_names
    assert "context_policy_candidates" in table_names
    assert version == CURRENT_ALEMBIC_HEAD

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


def test_core_memory_store_update_requires_audit_metadata(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()
    core = CoreMemoryService(store, TokenEstimator())
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="agent",
        reason="seed core profile",
    )

    with pytest.raises(ValueError, match="core memory store updates require actor"):
        store.update_core_memory_block(block.model_copy(update={"value": "Alice prefers buses."}))

    assert store.get_core_memory_block(block.id).value == "Alice prefers trains."
    assert [event.operation for event in store.list_core_memory_history(block.id)] == ["add"]


def test_read_only_core_block_rejects_store_update_and_delete(tmp_path):
    store = MemoryStore(_settings(tmp_path))
    store.init_db()
    core = CoreMemoryService(store, TokenEstimator())
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = core.create_block(
        label="persona",
        description="stable assistant facts",
        value="I prefer concise answers.",
        limit_tokens=40,
        source_refs=[ref],
        actor="agent",
        reason="seed persona",
        read_only=True,
    )

    with pytest.raises(ValueError, match="read-only core memory block cannot be mutated"):
        store.update_core_memory_block(
            block.model_copy(update={"value": "I prefer detailed answers."}),
            actor="agent",
            reason="mutate read-only block",
            source_refs=[ref],
        )

    with pytest.raises(ValueError, match="read-only core memory block cannot be mutated"):
        store.delete_core_memory_block(
            block.id,
            source_refs=[ref],
            actor="agent",
            reason="delete read-only",
        )
