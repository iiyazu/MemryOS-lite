"""Alembic environment for memoryos-lite.

The DSN is always pulled from ``memoryos_lite.config.get_settings().sqlite_url``,
so migrations work identically under:

* local SQLite dev (default)
* local Postgres via docker-compose (`POSTGRES_*` env → resolved DSN)
* CI / production (`DATABASE_URL` explicit)

Autogenerate is wired to ``memoryos_lite.store.Base.metadata`` so future
revisions can use ``alembic revision --autogenerate``.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Load the project settings *before* importing Base so env vars are honored.
from memoryos_lite.config import get_settings  # noqa: E402
from memoryos_lite.store import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the ini's placeholder URL with the one our Settings resolves.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sqlite_url)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, D401
    """Skip the pgvector extension-owned types in autogenerate diffs."""
    if type_ == "type" and name in {"vector"}:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
