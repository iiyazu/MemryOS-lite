import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from memoryos_lite.config import Settings


def test_redis_cache_config_defaults_to_disabled() -> None:
    settings = Settings()

    assert settings.memoryos_redis_url is None
    assert settings.memoryos_cache_namespace == "memoryos:v1"
    assert settings.memoryos_cache_default_ttl_s == 300


def test_redis_cache_config_preserves_memory_defaults() -> None:
    settings = Settings()

    assert settings.resolved_memory_arch == "v3"
    assert Settings(memoryos_memory_arch="v1").resolved_memory_arch == "v1"
    assert settings.resolved_recall_pipeline == "v1"
    assert Settings(memoryos_recall_pipeline="v2").resolved_recall_pipeline == "v2"
    assert settings.resolved_agent_kernel == "off"


def test_redis_dependency_is_optional_extra() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "redis" not in "\n".join(pyproject["project"]["dependencies"])
    redis_extra = pyproject["project"]["optional-dependencies"]["redis"]
    assert any(dependency.startswith("redis>=") for dependency in redis_extra)


def test_redis_cache_ttl_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(memoryos_cache_default_ttl_s=0)


def test_redis_cache_namespace_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        Settings(memoryos_cache_namespace=":")
