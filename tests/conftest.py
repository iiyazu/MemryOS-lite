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
    """Service built on the shipped defaults (v3/v2/off)."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


@pytest.fixture()
def legacy_service(tmp_path: Path) -> MemoryOSService:
    """Explicit opt-in to the v1 memory/recall paths and heuristic paging."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_memory_arch="v1",
        memoryos_paging_mode="heuristic",
        memoryos_recall_pipeline="v1",
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)
