"""Tests for the v3 context path (core-recall-archive).

Verifies that with the new defaults (paging_mode=off, recall_pipeline=v2,
memory_arch=v3), the system correctly:
- Skips auto-paging on ingest
- Creates episodes for recall
- Routes build_context through V3ContextComposer
"""

from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role
from memoryos_lite.store import create_store


@pytest.fixture()
def v3_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MemoryOSService:
    monkeypatch.delenv("MEMORYOS_PAGING_MODE", raising=False)
    monkeypatch.delenv("MEMORYOS_RECALL_PIPELINE", raising=False)
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


def test_v3_defaults(v3_service):
    assert v3_service.settings.memoryos_paging_mode == "off"
    assert v3_service.settings.memoryos_recall_pipeline == "v2"
    assert v3_service.settings.memoryos_memory_arch == "v3"


def test_ingest_does_not_auto_page(v3_service):
    session = v3_service.create_session("test")
    for i in range(10):
        v3_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"msg {i}"))

    pages = v3_service.store.list_pages(session.id)
    assert pages == []


def test_ingest_creates_episodes(v3_service):
    session = v3_service.create_session("test")
    v3_service.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))
    v3_service.ingest(session.id, MessageCreate(role=Role.ASSISTANT, content="hi there"))

    episodes = v3_service.store.list_episodes(session.id)
    assert len(episodes) >= 2


def test_build_context_uses_v3_composer(v3_service):
    session = v3_service.create_session("test")
    v3_service.ingest(session.id, MessageCreate(role=Role.USER, content="I live in Tokyo"))
    v3_service.ingest(session.id, MessageCreate(role=Role.ASSISTANT, content="Got it"))

    ctx = v3_service.build_context(session_id=session.id, task="Where does the user live?")
    assert ctx.metadata["memory_arch"] == "v3"
