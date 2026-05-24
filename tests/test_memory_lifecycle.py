import pytest

from memoryos_lite.config import Settings
from memoryos_lite.context_composer import V3ContextComposer
from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.memory_lifecycle import (
    MemoryLifecycleService,
    archival_to_core_candidate,
    recall_to_archival_candidate,
)
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ApprovalState,
    ArchivalMemory,
    ArchiveAttachment,
    ContextComposerRequest,
    SourceRef,
)


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


def test_lifecycle_create_candidate_persists_pending_candidate(tmp_path):
    store = _store(tmp_path)
    service = MemoryLifecycleService(store)

    candidate = service.create_candidate(
        source_layer="archival",
        target_layer="core",
        operation="promote",
        content="Alice prefers concise status updates.",
        source_refs=[_ref()],
        identity_scope=None,
        reason="source-backed preference candidate",
        confidence=0.87,
        write_source="explicit_instruction",
        metadata={
            "label": "human",
            "limit_tokens": 120,
            "tool_name": "core_promotion_request",
        },
    )

    persisted = store.get_promotion_candidate(candidate.id)
    candidates = store.list_promotion_candidates(status="pending")

    assert persisted is not None
    assert persisted.id == candidate.id
    assert persisted.status == "pending"
    assert persisted.target_layer == "core"
    assert persisted.operation == "promote"
    assert persisted.content == "Alice prefers concise status updates."
    assert persisted.source_refs[0].source_id == "msg_1"
    assert persisted.write_source == "explicit_instruction"
    assert persisted.metadata["label"] == "human"
    assert [item.id for item in candidates] == [candidate.id]


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


def test_recall_to_archival_candidate_is_retrievable_by_v3_context(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_1",
            archive_id="archive_1",
            scope_type="session",
            scope_id="ses_1",
            source_refs=[ref],
        )
    )
    service = MemoryLifecycleService(store)
    candidate = recall_to_archival_candidate(
        "Alice moved to Shanghai and prefers rail travel.",
        source_refs=[ref],
        archive_id="archive_1",
        reason="promote stable fact",
        confidence=0.91,
    )

    service.apply_candidate(candidate, actor="agent")
    package = V3ContextComposer(
        store=store,
        settings=Settings(data_dir=tmp_path / "data", memoryos_memory_arch="v3"),
        tokenizer=TokenEstimator(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="Where did Alice move and what travel does she prefer?",
            budget=80,
        )
    )

    archival_items = [item for item in package.items if item.layer == "archival"]
    assert [item.text for item in archival_items] == [
        "Alice moved to Shanghai and prefers rail travel."
    ]
    assert archival_items[0].source_refs[0].source_id == "msg_1"
    assert package.metadata["archival_eligibility"]["selected_passage_ids"] == [
        f"apsg_{candidate.id}"
    ]


def test_archival_memory_updates_and_deletes_sync_retrieval_passages(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_1",
            archive_id="archive_1",
            scope_type="session",
            scope_id="ses_1",
            source_refs=[ref],
        )
    )
    service = MemoryLifecycleService(store)
    candidate = recall_to_archival_candidate(
        "Alice moved to Shanghai.",
        source_refs=[ref],
        archive_id="archive_1",
        reason="promote stable fact",
        confidence=0.91,
    )

    service.apply_candidate(candidate, actor="agent")
    store.update_archival_memory(
        candidate.id,
        content="Alice moved to Suzhou.",
        source_refs=[ref],
        actor="agent",
        reason="user correction",
    )

    updated_package = V3ContextComposer(
        store=store,
        settings=Settings(data_dir=tmp_path / "data", memoryos_memory_arch="v3"),
        tokenizer=TokenEstimator(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="Where did Alice move?",
            budget=80,
        )
    )
    updated_archival_items = [item for item in updated_package.items if item.layer == "archival"]
    assert [item.text for item in updated_archival_items] == ["Alice moved to Suzhou."]

    store.delete_archival_memory(
        candidate.id,
        source_refs=[ref],
        actor="agent",
        reason="obsolete",
    )

    deleted_package = V3ContextComposer(
        store=store,
        settings=Settings(data_dir=tmp_path / "data", memoryos_memory_arch="v3"),
        tokenizer=TokenEstimator(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="Where did Alice move?",
            budget=80,
        )
    )
    assert [item for item in deleted_package.items if item.layer == "archival"] == []


def test_source_scoped_archival_memory_is_retrievable_by_source_scope(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    store.add_archival_memory(
        ArchivalMemory(
            id="amem_source",
            memory_type="fact",
            content="Alice keeps a source-scoped rail note.",
            source_refs=[ref],
        ),
        actor="agent",
        reason="message extraction",
    )

    package = V3ContextComposer(
        store=store,
        settings=Settings(data_dir=tmp_path / "data", memoryos_memory_arch="v3"),
        tokenizer=TokenEstimator(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What source-scoped rail note does Alice keep?",
            source_ids=["msg_1"],
            budget=80,
        )
    )

    archival_items = [item for item in package.items if item.layer == "archival"]
    assert [item.text for item in archival_items] == [
        "Alice keeps a source-scoped rail note."
    ]
    assert package.metadata["archival_eligibility"]["selected_passage_ids"] == [
        "apsg_amem_source"
    ]


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


def test_archival_to_core_candidate_updates_existing_core_block_in_place_with_history(
    tmp_path,
):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    lifecycle = MemoryLifecycleService(store, core)
    ref = _ref()

    existing = core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed core profile",
    )

    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[ref],
        reason="promote corrected preference",
        confidence=0.95,
        label="human",
        limit_tokens=40,
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_update",
        requested_action={"content": candidate.content},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=candidate.created_at,
    )

    applied = lifecycle.apply_candidate(candidate, actor="agent", approval_state=approved)

    blocks = store.list_core_memory_blocks()
    history = store.list_core_memory_history(existing.id)

    assert applied.status == "applied"
    assert len(blocks) == 1
    assert blocks[0].id == existing.id
    assert blocks[0].value == "Alice prefers rail travel."
    assert blocks[0].metadata["promotion_candidate_id"] == candidate.id
    assert blocks[0].metadata["approval_id"] == approved.id
    assert [event.operation for event in history] == ["add", "update"]
    assert history[1].before["value"] == "Alice prefers trains."
    assert history[1].after["value"] == "Alice prefers rail travel."


def test_archival_to_core_candidate_rejects_duplicate_label_conflict(tmp_path):
    store = _store(tmp_path)
    core = CoreMemoryService(store, TokenEstimator())
    lifecycle = MemoryLifecycleService(store, core)
    ref = _ref()
    first = core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed human profile",
    )
    second = core.create_block(
        label="human",
        description="secondary live facts",
        value="Alice prefers buses.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed human profile duplicate",
    )

    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[ref],
        reason="promote corrected preference",
        confidence=0.95,
        label="human",
        limit_tokens=40,
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_update",
        requested_action={"content": candidate.content},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=candidate.created_at,
    )

    with pytest.raises(ValueError, match="multiple live core memory blocks share label"):
        lifecycle.apply_candidate(candidate, actor="agent", approval_state=approved)

    assert [block.value for block in store.list_core_memory_blocks()] == [
        "Alice prefers trains.",
        "Alice prefers buses.",
    ]
    assert [event.operation for event in store.list_core_memory_history(first.id)] == ["add"]
    assert [event.operation for event in store.list_core_memory_history(second.id)] == ["add"]
