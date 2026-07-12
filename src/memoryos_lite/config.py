from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    memoryos_paging_mode: str = "off"
    memoryos_paging_context_pages: int = 10
    memoryos_item_extraction: bool = True
    memoryos_item_evidence_max: int = 3
    memoryos_evidence_representation: str = "legacy"
    memoryos_memory_arch: str = "v3"
    memoryos_agent_kernel: str = "off"
    memoryos_recall_pipeline: str = "v2"
    memoryos_evidence_direct_raw_fallback: bool = True
    memoryos_evidence_candidate_top_k: int = 5
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
    memoryos_redis_url: str | None = None
    memoryos_recall_cache_enabled: bool = False
    memoryos_cache_namespace: str = "memoryos:v1"
    memoryos_cache_default_ttl_s: int = 300
    memoryos_cache_query_analysis_ttl_s: int = 3600
    memoryos_cache_recall_candidates_ttl_s: int = 300
    memoryos_cache_context_package_ttl_s: int = 300
    agent_max_tool_turns: int = 10
    qdrant_url: str | None = None
    qdrant_collection: str = "memoryos_pages"
    memoryos_archival_vector_enabled: bool = True
    memoryos_archival_qdrant_url: str | None = None
    memoryos_archival_qdrant_collection: str = "memoryos_archival_passages"
    memoryos_recovery_enabled: bool = True
    memoryos_recovery_max_attempts: int = 3
    memoryos_recovery_initial_delay_s: float = 0.05
    memoryos_recovery_max_delay_s: float = 2.0
    memoryos_recovery_backoff_multiplier: float = 2.0
    memoryos_recovery_circuit_failure_threshold: int = 5
    memoryos_recovery_circuit_recovery_timeout_s: float = 60.0
    memoryos_recovery_graceful_degradation: bool = True

    # Middleware
    memoryos_api_key: str | None = None
    memoryos_cors_origins: str = "*"
    memoryos_log_format: str = "text"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @field_validator(
        "memoryos_cache_default_ttl_s",
        "memoryos_cache_query_analysis_ttl_s",
        "memoryos_cache_recall_candidates_ttl_s",
        "memoryos_cache_context_package_ttl_s",
    )
    @classmethod
    def validate_cache_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("cache TTL settings must be positive")
        return value

    @field_validator("memoryos_cache_namespace")
    @classmethod
    def validate_cache_namespace(cls, value: str) -> str:
        if not value.strip(":").strip():
            raise ValueError("MEMORYOS_CACHE_NAMESPACE must not be empty")
        return value

    @field_validator(
        "memoryos_recovery_max_attempts",
        "memoryos_recovery_circuit_failure_threshold",
    )
    @classmethod
    def validate_recovery_positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("recovery attempt and circuit threshold settings must be positive")
        return value

    @field_validator(
        "memoryos_recovery_initial_delay_s",
        "memoryos_recovery_max_delay_s",
        "memoryos_recovery_backoff_multiplier",
        "memoryos_recovery_circuit_recovery_timeout_s",
    )
    @classmethod
    def validate_recovery_non_negative_floats(cls, value: float) -> float:
        if value < 0:
            raise ValueError("recovery timing settings must be non-negative")
        return value

    @property
    def resolved_evidence_representation(self) -> str:
        val = self.memoryos_evidence_representation.strip().lower()
        valid = {"legacy", "raw", "deterministic_context", "page_context_plus_raw"}
        if val not in valid:
            raise ValueError(
                f"MEMORYOS_EVIDENCE_REPRESENTATION={val!r} invalid. Valid: {sorted(valid)}"
            )
        return val

    @property
    def resolved_memory_arch(self) -> str:
        val = self.memoryos_memory_arch.strip().lower()
        if val not in {"v1", "v3"}:
            raise ValueError("MEMORYOS_MEMORY_ARCH must be 'v1' or 'v3'")
        return val

    @property
    def resolved_agent_kernel(self) -> str:
        val = self.memoryos_agent_kernel.strip().lower()
        if val not in {"off", "v1"}:
            raise ValueError("MEMORYOS_AGENT_KERNEL must be 'off' or 'v1'")
        return val

    @property
    def resolved_recall_pipeline(self) -> str:
        val = self.memoryos_recall_pipeline.strip().lower()
        if val not in {"v1", "v2"}:
            raise ValueError("MEMORYOS_RECALL_PIPELINE must be 'v1' or 'v2'")
        return val

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
