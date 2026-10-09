from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.store_models import Base


class StoreRuntimeMixin:
    """Engine, schema, and transaction lifecycle for the composed store."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        dsn = self.settings.sqlite_url
        self.engine = create_engine(dsn, connect_args={"check_same_thread": False})
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @property
    def traces_dir(self) -> Path:
        return self.settings.data_dir / "traces"

    def init_db(self) -> None:
        """Create any missing table from the current models; existing tables are not altered."""
        try:
            Base.metadata.create_all(self.engine)
        except OperationalError as exc:
            if "already exists" not in str(exc):
                raise

    @contextmanager
    def db(self) -> Iterator[DbSession]:
        with self.session_factory() as session:
            yield session
            session.commit()
