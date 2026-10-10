"""Tests for the v3 context path: ingest creates episodes for recall, and
build_context routes through V3ContextComposer."""

from pathlib import Path

import pytest

from memoryos_eval.memory.schemas import MessageCreate, Role
from memoryos_eval.memory.service import SessionMemoryService
from memoryos_eval.memory.store import create_store
from memoryos_lite.config import Settings


@pytest.fixture()
def v3_service(tmp_path: Path) -> SessionMemoryService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
    )
    store = create_store(settings)
    store.reset()
    return SessionMemoryService(store=store, settings=settings)


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
