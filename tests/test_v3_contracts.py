import pytest
from pydantic import ValidationError

import memoryos_lite.v3_contracts as contracts
from memoryos_lite.schemas import (
    Episode,
    Message,
    Role,
)
from memoryos_lite.v3_contracts import (
    ArchivalChunk,
    ArchivalPassage,
    ArchiveAttachment,
    ContextComposerRequest,
    ContextLayerItem,
    ContextPackageV3,
    DiagnosticEvent,
    IdentityScope,
    LayerBudgetDecision,
    MessageLogEntry,
    RecallMemoryEntry,
    SourceRef,
    SourceSpan,
    ensure_persisted_identity_scope,
    episode_to_recall_entry,
    message_to_log_entry,
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


def test_diagnostics_and_budget_decisions_share_source_refs():
    ref = SourceRef(source_type="message", source_id="msg_1", session_id="ses_1")
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

    assert diagnostic.layer == "recall"
    assert decision.dropped_item_ids == ["passage_2"]


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


def test_archival_contracts_include_chunk_attachment_and_first_class_metadata():
    ref = SourceRef(source_type="message", source_id="msg_1", session_id="ses_1")
    chunk = ArchivalChunk(
        id="achunk_1",
        document_id="adoc_1",
        archive_id="archive_1",
        text="Alice moved to Shanghai.",
        start=0,
        end=24,
        source_refs=[ref],
    )
    passage = ArchivalPassage(
        id="apsg_1",
        document_id="adoc_1",
        chunk_id=chunk.id,
        archive_id="archive_1",
        text=chunk.text,
        source_id="source_1",
        file_id="file_1",
        tags=["travel"],
        source_refs=[ref],
    )
    attachment = ArchiveAttachment(
        id="aatt_1",
        archive_id="archive_1",
        scope_type="agent",
        scope_id="agent_1",
        source_refs=[ref],
    )

    assert chunk.document_id == "adoc_1"
    assert passage.chunk_id == chunk.id
    assert passage.source_id == "source_1"
    assert passage.file_id == "file_1"
    assert passage.updated_at is not None
    assert attachment.scope_type == "agent"


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


def test_v3_contract_module_exports_expected_public_names():
    expected = {
        "SourceRef",
        "IdentityScope",
        "DiagnosticEvent",
        "MessageLogEntry",
        "RecallMemoryEntry",
        "ArchivalDocument",
        "ArchivalPassage",
        "ContextComposer",
        "ensure_persisted_identity_scope",
    }

    assert expected.issubset(set(contracts.__all__))
