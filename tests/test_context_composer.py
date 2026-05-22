import pytest

from memoryos_lite.config import Settings
from memoryos_lite.context_composer import V3ContextComposer
from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import Message, MessageCreate, Role
from memoryos_lite.store import create_store
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ArchivalPassage,
    ContextComposerRequest,
    SourceRef,
)


class WordTokenizer(TokenEstimator):
    def count(self, text: str) -> int:
        return len(text.split())


def _ref(source_id: str = "msg_1") -> SourceRef:
    return SourceRef(source_type="message", source_id=source_id, session_id="ses_1")


def test_settings_default_to_v3_composer_with_kernel_off(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    assert settings.resolved_memory_arch == "v3"
    assert settings.resolved_agent_kernel == "off"


def test_settings_resolve_v3_composer_and_kernel_flags(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
    )

    assert settings.resolved_memory_arch == "v3"
    assert settings.resolved_agent_kernel == "v1"

    with pytest.raises(ValueError):
        bad_memory_arch = Settings(memoryos_memory_arch="bad")
        _ = bad_memory_arch.resolved_memory_arch

    with pytest.raises(ValueError):
        bad_agent_kernel = Settings(memoryos_agent_kernel="bad")
        _ = bad_agent_kernel.resolved_agent_kernel


def test_v3_composer_builds_layered_context_package(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    message = Message(
        id="msg_1",
        session_id="ses_1",
        role=Role.USER,
        content="Alice moved to Shanghai and prefers rail travel.",
        token_count=8,
    )
    store.add_message(message)
    store.ensure_episodes_for_session("ses_1")
    CoreMemoryService(store, WordTokenizer()).create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers rail travel.",
        limit_tokens=20,
        source_refs=[ref],
        actor="user",
        reason="explicit user instruction",
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_1",
            archive_id="archive_1",
            text="Alice moved to Shanghai.",
            source_refs=[ref],
        )
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="Where did Alice move?",
            budget=80,
        )
    )

    layers = [item.layer for item in package.items]
    assert layers[:2] == ["task", "core"]
    assert "recall" in layers
    assert "archival" in layers
    assert "recent" in layers
    assert package.metadata["memory_arch"] == "v3"
    assert package.budget_decisions
    assert all(item.estimated_tokens > 0 for item in package.items)


def test_v3_composer_core_items_use_structured_render_and_diagnostics(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    CoreMemoryService(store, WordTokenizer()).create_block(
        label="human",
        description="Stable user facts",
        value="Alice prefers rail travel.",
        limit_tokens=20,
        source_refs=[ref],
        actor="user",
        reason="explicit user instruction",
        tags=["profile"],
        metadata={"scope": "benchmark"},
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What does Alice prefer?",
            budget=80,
        )
    )

    core_items = [item for item in package.items if item.layer == "core"]
    assert len(core_items) == 1
    core_item = core_items[0]
    assert "<memory_blocks>" in core_item.text
    assert "<human>" in core_item.text
    assert core_item.metadata["label"] == "human"
    assert core_item.metadata["tags"] == ["profile"]
    assert core_item.metadata["metadata"] == {"scope": "benchmark"}
    assert core_item.metadata["tokens_limit"] == 20
    assert core_item.source_refs[0].source_id == "msg_1"
    core_diagnostics = [d for d in package.diagnostics if d.layer == "core"]
    assert core_diagnostics
    assert core_diagnostics[0].budget_tokens == core_item.estimated_tokens
    assert core_diagnostics[0].metadata["source_ref_count"] == 1


def test_service_build_context_routes_to_v3_when_opted_in(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
    )
    service = MemoryOSService(settings=settings)
    session = service.create_session("v3")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Carol moved to Berlin."),
    )

    package = service.build_context(session.id, "Where did Carol move?", budget=80)

    assert package.metadata["memory_arch"] == "v3"
    assert package.metadata["v3_layer_counts"]["task"] == 1
    assert package.metadata["v3_layer_counts"]["recall"] >= 1
    assert package.metadata["v3_context"]["items"]
