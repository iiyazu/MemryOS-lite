from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.store_models import Base

ALEMBIC_HEAD = "0011_curated_memory_versions"
# Columns added after a table was first created; create_all never alters tables.
_COLUMN_ADDITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "curated_memories": (
        ("version", "INTEGER NOT NULL DEFAULT 0"),
        ("occurrences", "INTEGER NOT NULL DEFAULT 1"),
        ("scope_type", "VARCHAR(32)"),
        ("scope_id", "VARCHAR(255)"),
    ),
    "sessions": (
        ("scope_type", "VARCHAR(32)"),
        ("scope_id", "VARCHAR(255)"),
    ),
}


class StoreRuntimeMixin:
    """Engine, schema, and transaction lifecycle for the composed store."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        dsn = self.settings.sqlite_url
        self.engine = create_engine(dsn, connect_args={"check_same_thread": False})
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @property
    def pages_dir(self) -> Path:
        return self.settings.data_dir / "pages"

    @property
    def traces_dir(self) -> Path:
        return self.settings.data_dir / "traces"

    def init_db(self) -> None:
        try:
            Base.metadata.create_all(self.engine)
        except OperationalError as exc:
            if "already exists" not in str(exc):
                raise
        self._ensure_current_schema()
        # Stamp alembic_version so `alembic upgrade head` on an existing DB
        # does not fail with "table already exists".
        self._stamp_alembic_head()

    def _ensure_current_schema(self) -> None:
        with self.engine.begin() as conn:
            table_exists = conn.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'core_memory_blocks'"
                )
            ).fetchone()
            if table_exists is not None:
                columns = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(core_memory_blocks)"))
                }
                if "read_only" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE core_memory_blocks "
                            "ADD COLUMN read_only BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                if "tags_json" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE core_memory_blocks "
                            "ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'"
                        )
                    )
            message_table = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'messages'")
            ).fetchone()
            if message_table is not None:
                message_columns = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(messages)"))
                }
                if "external_id" not in message_columns:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN external_id VARCHAR(255)"))
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "uq_messages_session_external "
                        "ON messages(session_id, external_id)"
                    )
                )
            for table, additions in _COLUMN_ADDITIONS.items():
                exists = conn.execute(
                    text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
                    {"name": table},
                ).fetchone()
                if exists is None:
                    continue
                present = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
                for column, ddl in additions:
                    if column not in present:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    def _stamp_alembic_head(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version"
                    " (version_num VARCHAR(32) NOT NULL,"
                    " CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            if row is None:
                conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
                    {"head": ALEMBIC_HEAD},
                )
            elif row[0] != ALEMBIC_HEAD:
                conn.execute(
                    text("UPDATE alembic_version SET version_num = :head"),
                    {"head": ALEMBIC_HEAD},
                )

    @contextmanager
    def db(self) -> Iterator[DbSession]:
        with self.session_factory() as session:
            yield session
            session.commit()
