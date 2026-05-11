from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path(".memoryos")
    memoryos_eval_data_dir: Path | None = None
    database_url: str | None = None
    postgres_host: str | None = None
    postgres_port: int = 5432
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    model_max_context: int = 128_000
    rot_safe_budget: int = 2_400
    hard_limit: int = 8_000
    recent_message_limit: int = 8
    memoryos_paging_mode: str = "heuristic"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    memoryos_model: str = "gpt-4o-mini"
    memoryos_embedding_model: str = "text-embedding-3-small"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def sqlite_url(self) -> str:
        """Resolve DSN in priority order: DATABASE_URL → derived Postgres → SQLite."""
        if self.database_url:
            return self.database_url
        if self.postgres_host and self.postgres_db and self.postgres_user:
            password = self.postgres_password or ""
            auth = f"{self.postgres_user}:{password}" if password else self.postgres_user
            return (
                f"postgresql+psycopg://{auth}@{self.postgres_host}:{self.postgres_port}"
                f"/{self.postgres_db}"
            )
        return f"sqlite:///{self.data_dir / 'memoryos.db'}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
