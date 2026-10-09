from sqlalchemy import text

from memoryos_lite.config import Settings
from memoryos_lite.store import MemoryStore

CURRENT_ALEMBIC_HEAD = "0011_curated_memory_versions"


def _settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )


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
