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
        tags=["profile"],
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
    rendered = render_core_memory_blocks([updated], tokenizer=FakeTokenizer())
    assert "<memory_blocks>" in rendered.text
    assert "<profile>" in rendered.text
    assert "<description>\nStable user facts\n</description>" in rendered.text
    assert "- read_only=false" in rendered.text
    assert "- tokens_current=4" in rendered.text
    assert "- tokens_limit=20" in rendered.text
    assert "- tags=profile" in rendered.text
    assert "- message:msg_1" in rendered.text
    assert "<value>\nAlice lives in Suzhou.\n</value>" in rendered.text
    assert rendered.metadata_by_block[updated.id]["label"] == "profile"
    assert rendered.metadata_by_block[updated.id]["tokens_limit"] == 20


def test_core_memory_service_rejects_read_only_mutations(tmp_path):
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
        read_only=True,
    )

    with pytest.raises(ValueError, match="read-only core memory block"):
        service.append_block(
            block.id,
            "Alice prefers rail.",
            source_refs=[ref],
            actor="agent",
            reason="append",
        )
    with pytest.raises(ValueError, match="read-only core memory block"):
        service.replace_block(
            block.id,
            old="Shanghai",
            content="Suzhou",
            source_refs=[ref],
            actor="agent",
            reason="replace",
        )
    with pytest.raises(ValueError, match="read-only core memory block"):
        service.update_block(
            block.id,
            "Alice lives in Suzhou.",
            source_refs=[ref],
            actor="agent",
            reason="update",
        )
    with pytest.raises(ValueError, match="read-only core memory block"):
        service.delete_block(
            block.id,
            source_refs=[ref],
            actor="agent",
            reason="delete",
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
