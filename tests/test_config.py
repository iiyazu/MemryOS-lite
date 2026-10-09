import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from memoryos_lite.config import Settings


def test_redis_is_not_a_core_dependency() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "redis" not in "\n".join(pyproject["project"]["dependencies"])


def test_curator_defaults_to_disabled_with_bounded_windows() -> None:
    settings = Settings()

    assert settings.memoryos_curator_enabled is False
    assert settings.memoryos_curator_window_messages == 12
    assert settings.memoryos_curator_idle_flush_s == 20.0
    assert settings.memoryos_curator_poll_s == 2.0
    assert settings.memoryos_curator_max_active_in_prompt == 40


def test_curator_positive_settings_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_window_messages=0)
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_max_active_in_prompt=0)
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_idle_flush_s=-1.0)
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_poll_s=0.0)
