import pytest
from pydantic import ValidationError

import memoryos_lite.v3_contracts as contracts
from memoryos_lite.schemas import (
    Episode,
    MemoryItem,
    MemoryItemType,
    MemoryPage,
    Message,
    PageType,
    Role,
)
from memoryos_lite.v3_contracts import (
    REQUIRED_V3_ADAPTERS,
    V3_FUTURE_TABLES,
    V3_KEEP_TABLES,
    V3_NO_NEW_TARGETS,
    ApprovalState,
    ArchivalDocument,
    ArchivalMemory,
    ArchivalPassage,
    ContextComposerRequest,
    ContextLayerItem,
    ContextPackageV3,
    CoreMemoryBlock,
    CoreMemoryUpdate,
    DiagnosticEvent,
    IdentityScope,
    KernelTraceEvent,
    LayerBudgetDecision,
    MemoryHistoryEvent,
    MessageLogEntry,
    RecallMemoryEntry,
    SourceRef,
    SourceSpan,
    ToolPolicyDecision,
    ToolPolicyRule,
    ensure_persisted_identity_scope,
    episode_to_recall_entry,
    item_to_archival_memory,
    item_to_archival_passage,
    message_to_log_entry,
    page_to_archival_document,
)


def test_source_ref_requires_non_empty_source_id_and_valid_span():
    ref = SourceRef(
        source_type="message",
        source_id="msg_1",
        span=SourceSpan(start=3, end=9),
        quote="source",
        confidence=0.75,
    )

    assert ref.source_id == "msg_1"
    assert ref.span.start == 3
    assert ref.confidence == 0.75

    with pytest.raises(ValidationError):
        SourceRef(source_type="message", source_id="")

    with pytest.raises(ValidationError):
        SourceRef(
            source_type="message",
            source_id="msg_1",
            span=SourceSpan(start=10, end=4),
        )

    manual_ref = SourceRef(
        source_type="manual",
        source_id="policy_1",
        approval_id="appr_1",
    )
    assert manual_ref.approval_id == "appr_1"

    with pytest.raises(ValidationError):
        SourceRef(source_type="manual", source_id="policy_2")


def test_identity_scope_allows_ephemeral_values_but_persisted_scope_is_guarded():
    empty_scope = IdentityScope()
    scope = IdentityScope(user_id="user_1", session_id="ses_1", tags=["project"])

    assert empty_scope.tags == []
    assert scope.user_id == "user_1"
    assert scope.tags == ["project"]

    with pytest.raises(ValueError):
        ensure_persisted_identity_scope(empty_scope)

    assert ensure_persisted_identity_scope(scope) is scope


def test_history_diagnostics_and_budget_decisions_share_source_refs():
    ref = SourceRef(source_type="message", source_id="msg_1", session_id="ses_1")
    history = MemoryHistoryEvent(
        memory_id="mem_1",
        memory_type="core_block",
        operation="replace",
        actor="agent",
        reason="newer user correction",
        before={"value": "old"},
        after={"value": "new"},
        source_refs=[ref],
    )
    diagnostic = DiagnosticEvent(
        layer="recall",
        event_type="rank",
        item_id="rec_1",
        reason_code="bm25_overlap",
        score=3.5,
        included=True,
        source_refs=[ref],
    )
    decision = LayerBudgetDecision(
        layer="archival",
        requested_tokens=1200,
        allocated_tokens=400,
        used_tokens=376,
        dropped_item_ids=["passage_2"],
        reason_code="budget_limit",
    )

    assert history.source_refs == [ref]
    assert diagnostic.layer == "recall"
    assert decision.dropped_item_ids == ["passage_2"]

    with pytest.raises(ValidationError):
        MemoryHistoryEvent(
            memory_id="mem_2",
            memory_type="archival_memory",
            operation="replace",
            actor="agent",
            reason="bad replace",
            after={"value": "new"},
            source_refs=[ref],
        )


def test_legacy_message_and_episode_adapt_to_v3_layer_contracts():
    message = Message(
        id="msg_1",
        session_id="ses_1",
        role=Role.USER,
        content="Alice moved to Shanghai.",
        token_count=5,
    )
    episode = Episode(
        id="epi_1",
        session_id="ses_1",
        message_id="msg_1",
        role=Role.USER,
        text="Alice moved to Shanghai.",
        index_text="[speaker=user] Alice moved to Shanghai.",
        position=1,
        source_message_ids=["msg_1"],
    )

    log_entry = message_to_log_entry(message)
    recall_entry = episode_to_recall_entry(episode)

    assert isinstance(log_entry, MessageLogEntry)
    assert log_entry.source_refs[0].source_id == "msg_1"
    assert isinstance(recall_entry, RecallMemoryEntry)
    assert recall_entry.source_message_ids == ["msg_1"]
    assert recall_entry.source_refs[0].source_type == "message"


def test_page_and_item_are_legacy_inputs_not_archival_targets():
    page = MemoryPage(
        id="page_1",
        session_id="ses_1",
        page_type=PageType.SOURCE_SUMMARY,
        title="Trip summary",
        summary="Alice discussed Shanghai.",
        source_message_ids=["msg_1"],
    )
    item = MemoryItem(
        id="item_1",
        page_id="page_1",
        session_id="ses_1",
        item_type=MemoryItemType.PROFILE,
        content="Alice lives in Shanghai.",
        source_message_ids=["msg_1"],
    )

    document = page_to_archival_document(page)
    memory = item_to_archival_memory(item)
    passage = item_to_archival_passage(item, document_id=document.id)

    assert isinstance(document, ArchivalDocument)
    assert document.legacy_page_id == "page_1"
    assert isinstance(memory, ArchivalMemory)
    assert memory.legacy_item_id == "item_1"
    assert isinstance(passage, ArchivalPassage)
    assert passage.document_id == document.id
    assert passage.legacy_item_id == "item_1"
    assert document.id.startswith("adoc_")
    assert memory.id.startswith("amem_")
    assert passage.id.startswith("apsg_")


def test_core_memory_update_requires_source_refs_or_approval():
    block = CoreMemoryBlock(
        id="core_1",
        label="human",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=200,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )

    update = CoreMemoryUpdate(
        block_id=block.id,
        operation="append",
        content="Alice prefers rail travel.",
        source_refs=[SourceRef(source_type="message", source_id="msg_2")],
    )

    assert update.source_refs[0].source_id == "msg_2"

    with pytest.raises(ValidationError):
        CoreMemoryUpdate(block_id=block.id, operation="append", content="source-less")

    approved_state = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"block": "human", "content": "manually approved"},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=block.created_at,
    )
    approved = CoreMemoryUpdate(
        block_id=block.id,
        operation="append",
        content="manually approved",
        approval_state=approved_state,
    )
    assert approved.approval_state is approved_state

    with pytest.raises(ValidationError):
        CoreMemoryUpdate(
            block_id=block.id,
            operation="append",
            content="pending approval cannot write",
            approval_state=ApprovalState(
                id="appr_2",
                session_id="ses_1",
                tool_name="memory_core_append",
                requested_action={"block": "human", "content": "pending"},
                status="pending",
                requested_by="agent",
            ),
        )


def test_core_memory_block_defaults_soft_delete_fields():
    block = CoreMemoryBlock(
        id="core_2",
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=200,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )

    assert block.deleted_at is None
    assert block.deleted_by_event_id is None


def test_core_memory_replace_requires_old_value():
    with pytest.raises(ValidationError):
        CoreMemoryUpdate(
            block_id="core_1",
            operation="replace",
            content="Alice lives in Suzhou.",
            source_refs=[SourceRef(source_type="message", source_id="msg_2")],
        )


def test_context_package_v3_groups_layer_items_and_budget_decisions():
    package = ContextPackageV3(
        session_id="ses_1",
        task="answer the user",
        items=[
            ContextLayerItem(
                layer="core",
                item_id="core_1",
                text="Alice lives in Shanghai.",
                estimated_tokens=5,
                source_refs=[SourceRef(source_type="core_block", source_id="core_1")],
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="core",
                requested_tokens=200,
                allocated_tokens=100,
                used_tokens=5,
                reason_code="always_in_context",
            )
        ],
    )
    request = ContextComposerRequest(session_id="ses_1", task="answer the user", budget=1000)

    assert package.items[0].layer == "core"
    assert request.budget == 1000


def test_v3_table_boundary_keeps_legacy_tables_and_defers_recall_split():
    assert V3_KEEP_TABLES == {
        "sessions",
        "messages",
        "episodes",
        "memory_pages",
        "memory_items",
        "memory_patches",
        "trace_events",
        "alembic_version",
    }
    assert "recall_memory_entries" not in V3_FUTURE_TABLES
    assert "archival_documents" in V3_FUTURE_TABLES
    assert "kernel_traces" in V3_FUTURE_TABLES


def test_page_and_item_are_declared_legacy_adapter_inputs_only():
    assert V3_NO_NEW_TARGETS == {"MemoryPage", "MemoryItem"}
    assert REQUIRED_V3_ADAPTERS["MemoryPage"] == "ArchivalDocument migration input"
    assert REQUIRED_V3_ADAPTERS["MemoryItem"] == "ArchivalMemory or ArchivalPassage adapter"


def test_tool_policy_decision_never_allows_unknown_tool_implicitly():
    rule = ToolPolicyRule(
        id="rule_1",
        tool_name="memory_core_append",
        effect="require_approval",
        reason="core memory mutation",
        priority=10,
        source_refs=[
            SourceRef(
                source_type="manual",
                source_id="policy",
                approval_id="appr_policy",
            )
        ],
    )
    decision = ToolPolicyDecision(
        tool_name="memory_core_append",
        effect="require_approval",
        matched_rule_ids=[rule.id],
        requires_approval=True,
        reason=rule.reason,
    )

    assert decision.effect == "require_approval"
    assert decision.requires_approval is True

    with pytest.raises(ValidationError):
        ToolPolicyDecision(
            tool_name="unknown_tool",
            effect="allow",
            matched_rule_ids=[],
            requires_approval=False,
            reason="implicit allow is forbidden",
        )


def test_approval_state_requires_resolution_metadata_when_approved():
    pending = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"block": "human", "content": "Alice likes rail."},
        status="pending",
        requested_by="agent",
    )
    approved = ApprovalState(
        id="appr_1",
        session_id="ses_1",
        tool_name="memory_core_append",
        requested_action={"block": "human", "content": "Alice likes rail."},
        status="approved",
        requested_by="agent",
        approved_by="user",
        resolved_at=pending.created_at,
    )

    assert pending.status == "pending"
    assert approved.approved_by == "user"

    with pytest.raises(ValidationError):
        ApprovalState(
            id="appr_2",
            session_id="ses_1",
            tool_name="memory_core_append",
            requested_action={"block": "human"},
            status="approved",
            requested_by="agent",
        )


def test_kernel_trace_events_are_ordered_and_replayable():
    event = KernelTraceEvent(
        step_id="step_1",
        session_id="ses_1",
        sequence=1,
        event_type="tool_policy_decision",
        payload={"tool_name": "memory_core_append", "effect": "require_approval"},
        source_refs=[SourceRef(source_type="approval", source_id="appr_1")],
        approval_id="appr_1",
    )

    assert event.sequence == 1
    assert event.payload["effect"] == "require_approval"

    with pytest.raises(ValidationError):
        KernelTraceEvent(
            step_id="step_1",
            session_id="ses_1",
            sequence=0,
            event_type="bad",
            payload={},
        )


def test_v3_contract_module_exports_expected_public_names():
    expected = {
        "SourceRef",
        "IdentityScope",
        "MemoryHistoryEvent",
        "DiagnosticEvent",
        "MessageLogEntry",
        "RecallMemoryEntry",
        "ArchivalDocument",
        "ArchivalPassage",
        "ArchivalMemory",
        "CoreMemoryBlock",
        "CoreMemoryUpdate",
        "ContextComposer",
        "AgentStepRunner",
        "ToolPolicyEngine",
        "ApprovalGate",
        "ToolExecutionManager",
        "ContinuationController",
        "ensure_persisted_identity_scope",
        "V3_KEEP_TABLES",
        "V3_FUTURE_TABLES",
        "REQUIRED_V3_ADAPTERS",
    }

    assert expected.issubset(set(contracts.__all__))
