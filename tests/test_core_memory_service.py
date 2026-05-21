import pytest

from memoryos_lite.config import Settings
from memoryos_lite.core_memory import CoreMemoryService, render_core_memory_blocks
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import SourceRef


class FakeTokenizer:
    def count(self, text: str) -> int:
        return len(text.split())


def _service(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )
    store = MemoryStore(settings)
    store.init_db()
    return CoreMemoryService(store=store, tokenizer=FakeTokenizer())


def test_core_memory_service_requires_source_backed_writes(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError):
        service.create_block(
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=20,
            source_refs=[],
            actor="agent",
            reason="seed profile",
        )


def test_core_memory_service_append_replace_update_and_render(tmp_path):
    service = _service(tmp_path)
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = service.create_block(
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=20,
        source_refs=[ref],
        actor="agent",
        reason="seed profile",
    )

    appended = service.append_block(
        block.id,
        "Alice prefers rail travel.",
        source_refs=[ref],
        actor="agent",
        reason="new fact",
    )
    replaced = service.replace_block(
        block.id,
        old="Shanghai",
        content="Suzhou",
        source_refs=[ref],
        actor="agent",
        reason="correction",
    )
    updated = service.update_block(
        block.id,
        "Alice lives in Suzhou.",
        source_refs=[ref],
        actor="agent",
        reason="full rewrite",
    )

    assert "Alice prefers rail travel." in appended.value
    assert replaced.value != block.value
    assert updated.value == "Alice lives in Suzhou."
    assert render_core_memory_blocks([updated]) == (
        "[Core Memory]\n"
        "- profile (20 tokens)\n"
        "  Stable user facts\n"
        "  Alice lives in Suzhou."
    )


def test_core_memory_service_rejects_over_limit_updates(tmp_path):
    service = _service(tmp_path)
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = service.create_block(
        label="profile",
        description="Stable user facts",
        value="Alice",
        limit_tokens=2,
        source_refs=[ref],
        actor="agent",
        reason="seed profile",
    )

    with pytest.raises(ValueError):
        service.append_block(
            block.id,
            "prefers rail travel",
            source_refs=[ref],
            actor="agent",
            reason="overflow",
        )
