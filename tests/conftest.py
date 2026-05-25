from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.store import create_store


@pytest.fixture(autouse=True)
def _huggingface_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")


@pytest.fixture()
def service(tmp_path: Path) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_memory_arch="v1",
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)
