import pytest

from memoryos_lite.config import Settings
from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.memory_lifecycle import (
    MemoryLifecycleService,
    archival_to_core_candidate,
    recall_to_archival_candidate,
)
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import ApprovalState, SourceRef


def _store(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        sqlite_path=tmp_path / "memory.sqlite3",
    )
    store = MemoryStore(settings)
    store.init_db()
    return store


def _ref() -> SourceRef:
    return SourceRef(source_type="message", source_id="msg_1", session_id="ses_1")


def test_lifecycle_candidates_require_source_refs_and_remain_pending(tmp_path):
    service = MemoryLifecycleService(_store(tmp_path))

    with pytest.raises(ValueError):
        service.create_candidate(
            source_layer="recall",
            target_layer="archival",
            operation="add",
            content="No source.",
            source_refs=[],
            identity_scope=None,
            reason="bad extraction",
            confidence=0.5,
            write_source="message_extraction",
        )

    candidate = service.create_candidate(
        source_layer="recall",
        target_layer="archival",
        operation="add",
        content="Alice moved to Shanghai.",
        source_refs=[_ref()],
        identity_scope=None,
        reason="message extraction",
        confidence=0.8,
        write_source="message_extraction",
    )

    assert candidate.status == "pending"
    assert candidate.reason == "message extraction"
    assert candidate.source_refs[0].source_id == "msg_1"


def test_recall_to_archival_candidate_applies_as_archival_memory(tmp_path):
    store = _store(tmp_path)
    service = MemoryLifecycleService(store)
    candidate = recall_to_archival_candidate(
        "Alice moved to Shanghai.",
        source_refs=[_ref()],
        archive_id="archive_1",
        reason="promote stable fact",
        confidence=0.91,
    )

    applied = service.apply_candidate(candidate, actor="agent")
    history = store.list_archival_memory_history(candidate.id)

    assert applied.status == "applied"
    assert candidate.metadata["archive_id"] == "archive_1"
    assert [event.operation for event in history] == ["add"]


def test_archival_to_core_promotion_requires_approved_state(tmp_path):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    service = MemoryLifecycleService(store, core)
    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[_ref()],
        reason="promote stable preference",
        confidence=0.95,
        label="human",
        limit_tokens=100,
    )

    with pytest.raises(ValueError):
        service.apply_candidate(candidate, actor="agent")

    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"content": candidate.content},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=candidate.created_at,
    )
    applied = service.apply_candidate(candidate, actor="agent", approval_state=approved)

    assert applied.status == "applied"
    assert store.list_core_memory_blocks()[0].value == "Alice prefers rail travel."
