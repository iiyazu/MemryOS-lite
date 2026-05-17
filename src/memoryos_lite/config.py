from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"


class Settings(BaseSettings):
    data_dir: Path = Path(".memoryos")
    memoryos_eval_data_dir: Path | None = None
    model_max_context: int = 128_000
    rot_safe_budget: int = 2_400
    hard_limit: int = 8_000
    recent_message_limit: int = 8
    memoryos_page_window_max_messages: int = 24
    memoryos_page_window_max_tokens: int = 5_000
    memoryos_evidence_max_tokens: int = 48
    memoryos_evidence_reserve_ratio: float = 0.6
    # 0 means "no absolute token cap"; the ratio still controls the reserve.
    memoryos_evidence_reserve_tokens: int = 512
    memoryos_evidence_reserve_min_pages: int = 8
    memoryos_paging_mode: str = "heuristic"
    memoryos_paging_context_pages: int = 10
    memoryos_item_extraction: bool = True
    memoryos_item_evidence_max: int = 3
    memoryos_evidence_representation: str = "legacy"
    memoryos_evidence_direct_raw_fallback: bool = True
    memoryos_evidence_candidate_top_k: int = 20
    memoryos_evidence_context_neighbors_before: int = 2
    memoryos_evidence_context_neighbors_after: int = 1
    memoryos_llm_provider: str = "auto"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    memoryos_model: str = "gpt-4o-mini"
    memoryos_embedding_model: str = "text-embedding-3-small"
    memoryos_embedding_provider: str = "auto"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = DEEPSEEK_DEFAULT_BASE_URL
    deepseek_model: str = DEEPSEEK_DEFAULT_MODEL
    memoryos_rewrite_enabled: bool = False
    memoryos_rerank_enabled: bool = False
    memoryos_llm_timeout_s: float = 60.0
    memoryos_qdrant_timeout_s: float = 10.0
    agent_max_tool_turns: int = 10
    qdrant_url: str | None = None
    qdrant_collection: str = "memoryos_pages"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def resolved_llm_provider(self) -> str:
        provider = self.memoryos_llm_provider.strip().lower()
        if provider == "auto":
            if self.deepseek_api_key and not self.openai_api_key:
                return "deepseek"
            return "openai"
        if provider not in {"openai", "deepseek"}:
            raise ValueError("MEMORYOS_LLM_PROVIDER must be 'auto', 'openai', or 'deepseek'")
        return provider

    @property
    def chat_api_key(self) -> str | None:
        if self.resolved_llm_provider == "deepseek":
            return self.deepseek_api_key
        return self.openai_api_key

    @property
    def chat_api_key_name(self) -> str:
        if self.resolved_llm_provider == "deepseek":
            return "DEEPSEEK_API_KEY"
        return "OPENAI_API_KEY"

    @property
    def chat_base_url(self) -> str | None:
        if self.resolved_llm_provider == "deepseek":
            return self.deepseek_base_url
        return self.openai_base_url

    @property
    def chat_model(self) -> str:
        if self.resolved_llm_provider == "deepseek":
            return self.deepseek_model
        return self.memoryos_model

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'memoryos.db'}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
