from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
# OpenCode Go subscription endpoint; Muse Spark models are served on the
# Responses API only (https://opencode.ai/docs/go).
OPENCODE_DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_DEFAULT_MODEL = "muse-spark-1.3-contributor"
LLM_PROVIDERS = ("openai", "deepseek", "opencode")
WIRE_APIS = ("chat", "responses")


class Settings(BaseSettings):
    data_dir: Path = Path(".memoryos")
    memoryos_eval_data_dir: Path | None = None
    rot_safe_budget: int = 2_400
    hard_limit: int = 8_000
    recent_message_limit: int = 8
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
    opencode_api_key: str | None = None
    opencode_base_url: str = OPENCODE_DEFAULT_BASE_URL
    opencode_model: str = OPENCODE_DEFAULT_MODEL
    # "responses" for Muse Spark/GPT models, "chat" for chat-completions models.
    opencode_wire_api: str = "responses"
    # Sent as x-opencode-session; unset means one generated id per client.
    opencode_session_id: str | None = None
    memoryos_llm_timeout_s: float = 60.0
    memoryos_archival_vector_enabled: bool = True

    # Curator (LLM-extracted durable memories; opt-in)
    memoryos_curator_enabled: bool = False
    memoryos_curator_window_messages: int = 12
    memoryos_curator_idle_flush_s: float = 20.0
    memoryos_curator_poll_s: float = 2.0
    memoryos_curator_max_active_in_prompt: int = 40
    # source_evidence/v2 ranks raw evidence that states a superseded curated
    # value (by verbatim quote) behind the rest. Off until RoomMem shows a gain.
    memoryos_demote_superseded: bool = False

    # Middleware
    memoryos_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @field_validator(
        "memoryos_curator_window_messages",
        "memoryos_curator_max_active_in_prompt",
    )
    @classmethod
    def validate_curator_positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("curator window and prompt budget settings must be positive")
        return value

    @field_validator("memoryos_curator_idle_flush_s")
    @classmethod
    def validate_curator_idle_flush_s(cls, value: float) -> float:
        if value < 0:
            raise ValueError("MEMORYOS_CURATOR_IDLE_FLUSH_S must be non-negative")
        return value

    @field_validator("memoryos_curator_poll_s")
    @classmethod
    def validate_curator_poll_s(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("MEMORYOS_CURATOR_POLL_S must be positive")
        return value

    @property
    def resolved_llm_provider(self) -> str:
        provider = self.memoryos_llm_provider.strip().lower()
        if provider == "auto":
            if self.deepseek_api_key and not self.openai_api_key:
                return "deepseek"
            return "openai"
        if provider not in LLM_PROVIDERS:
            raise ValueError(
                "MEMORYOS_LLM_PROVIDER must be 'auto', 'openai', 'deepseek', or 'opencode'"
            )
        return provider

    @property
    def chat_api_key(self) -> str | None:
        provider = self.resolved_llm_provider
        if provider == "deepseek":
            return self.deepseek_api_key
        if provider == "opencode":
            return self.opencode_api_key
        return self.openai_api_key

    @property
    def chat_api_key_name(self) -> str:
        provider = self.resolved_llm_provider
        if provider == "deepseek":
            return "DEEPSEEK_API_KEY"
        if provider == "opencode":
            return "OPENCODE_API_KEY"
        return "OPENAI_API_KEY"

    @property
    def chat_base_url(self) -> str | None:
        provider = self.resolved_llm_provider
        if provider == "deepseek":
            return self.deepseek_base_url
        if provider == "opencode":
            return self.opencode_base_url
        return self.openai_base_url

    @property
    def chat_model(self) -> str:
        provider = self.resolved_llm_provider
        if provider == "deepseek":
            return self.deepseek_model
        if provider == "opencode":
            return self.opencode_model
        return self.memoryos_model

    @property
    def chat_wire_api(self) -> str:
        """Wire API of the chat provider: ``chat`` completions or ``responses``."""

        if self.resolved_llm_provider != "opencode":
            return "chat"
        val = self.opencode_wire_api.strip().lower()
        if val not in WIRE_APIS:
            raise ValueError("OPENCODE_WIRE_API must be 'chat' or 'responses'")
        return val

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'memoryos.db'}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
