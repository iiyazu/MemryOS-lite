import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from memoryos_lite.config import Settings


def test_redis_and_alembic_are_not_core_dependencies() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = "\n".join(pyproject["project"]["dependencies"])
    assert "redis" not in dependencies
    assert "alembic" not in dependencies


def test_curator_positive_settings_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_window_messages=0)
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_max_active_in_prompt=0)
    with pytest.raises(ValidationError):
        Settings(memoryos_curator_idle_flush_s=-1.0)
