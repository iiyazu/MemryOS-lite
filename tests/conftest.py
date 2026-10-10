from pathlib import Path

import pytest

from memoryos_eval.memory.service import SessionMemoryService
from memoryos_eval.memory.store import create_store
from memoryos_lite.config import Settings


@pytest.fixture(autouse=True)
def _huggingface_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")


@pytest.fixture()
def service(tmp_path: Path) -> SessionMemoryService:
    """Service built on the shipped defaults (v3/v2/off)."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
    )
    store = create_store(settings)
    store.reset()
    return SessionMemoryService(store=store, settings=settings)
