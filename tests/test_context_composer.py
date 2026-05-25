import pytest

from memoryos_lite.config import Settings
from memoryos_lite.context_composer import V3ContextComposer
from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.memory_lifecycle import (
    MemoryLifecycleService,
    archival_to_core_candidate,
)
from memoryos_lite.retrieval.archival_searcher import ArchivalPassageSearcher
from memoryos_lite.retrieval.archival_vector import (
    ArchivalEmbeddingConfig,
    ArchivalVectorIndex,
)
from memoryos_lite.retrieval.providers.qdrant_archival import (
    QdrantArchivalPassageStore,
)
from memoryos_lite.schemas import Message, MessageCreate, Role
from memoryos_lite.store import create_store
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ApprovalState,
    ArchivalPassage,
    ArchiveAttachment,
    ContextComposerRequest,
    IdentityScope,
    SourceRef,
)


class WordTokenizer(TokenEstimator):
    def count(self, text: str) -> int:
        return len(text.split())


class TinyEmbeddingClient:
    @property
    def dim(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if normalized == "favorite transport" or "semantic-target" in normalized:
            return [1.0, 0.0, 0.0]
        if "favorite transport" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def _vector_searcher(
    store,
    collection: str,
) -> ArchivalPassageSearcher:
    return ArchivalPassageSearcher(
        vector_index=ArchivalVectorIndex(
            embedding_client=TinyEmbeddingClient(),
            vector_store=QdrantArchivalPassageStore(
                url=":memory:",
                collection=collection,
                dim=3,
            ),
            config=ArchivalEmbeddingConfig(provider="test", model="tiny", dim=3),
        ),
        passage_loader=store.get_archival_passages_by_ids,
    )


def _ref(source_id: str = "msg_1") -> SourceRef:
    return SourceRef(source_type="message", source_id=source_id, session_id="ses_1")


def test_settings_default_to_v3_composer_with_kernel_off(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    assert settings.resolved_memory_arch == "v3"
    assert settings.resolved_agent_kernel == "off"
    assert settings.memoryos_archival_vector_enabled is True


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
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_1",
            archive_id="archive_1",
            scope_type="session",
            scope_id="ses_1",
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


def test_v3_composer_filters_archival_passages_by_attached_scope(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_attached",
            archive_id="archive_attached",
            text="Alice keeps the quiet archive note about Shanghai rail.",
            source_refs=[ref],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_unattached",
            archive_id="archive_unattached",
            text="Alice keeps the loud perfect Shanghai rail answer in an unattached archive.",
            source_refs=[_ref("msg_2")],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
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
            task="Where is Alice's Shanghai rail note?",
            budget=80,
        )
    )

    archival_items = [item for item in package.items if item.layer == "archival"]
    assert [item.item_id for item in archival_items] == ["apsg_attached"]
    eligibility = package.metadata["archival_eligibility"]
    assert eligibility["eligible_archive_ids"] == ["archive_attached"]
    assert eligibility["selected_passage_ids"] == ["apsg_attached"]
    assert eligibility["archival_scope_excluded"] == 1
    assert "apsg_unattached" in eligibility["scope_excluded_passage_ids"]


def test_v3_composer_reports_archival_scope_eligibility(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_match",
            archive_id="archive_attached",
            text="Alice archived a Shanghai rail preference.",
            source_refs=[ref],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_no_match",
            archive_id="archive_attached",
            text="Bob archived a kitchen inventory.",
            source_refs=[_ref("msg_2")],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_excluded",
            archive_id="archive_other",
            text="Alice Shanghai rail distractor from another archive.",
            source_refs=[_ref("msg_3")],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="agent",
            scope_id="agent_1",
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
            task="What did Alice archive about Shanghai rail?",
            budget=80,
            identity_scope=IdentityScope(agent_id="agent_1"),
        )
    )

    eligibility = package.metadata["archival_eligibility"]
    assert eligibility["eligible_archive_ids"] == ["archive_attached"]
    assert eligibility["selected_passage_ids"] == ["apsg_match"]
    assert eligibility["selected_source_refs"] == [
        {"source_type": "message", "source_id": "msg_1", "session_id": "ses_1"}
    ]
    assert eligibility["eligible_passage_count"] == 2
    assert eligibility["selected_passage_count"] == 1
    assert eligibility["archival_scope_excluded"] == 1
    assert eligibility["archival_no_match"] == 1
    event_types = [
        diagnostic.event_type
        for diagnostic in package.diagnostics
        if diagnostic.layer == "archival"
    ]
    assert "archival_selected" in event_types
    assert "archival_eligible_no_match" in event_types
    assert "archival_scope_excluded" in event_types


def test_v3_composer_scope_excluded_accounting_keeps_source_refs(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    attached_ref = _ref("msg_attached")
    excluded_ref = _ref("msg_excluded")
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_attached",
            archive_id="archive_attached",
            text="Alice attached a Shanghai rail note.",
            source_refs=[attached_ref],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_excluded",
            archive_id="archive_excluded",
            text="Alice excluded a Shanghai rail note.",
            source_refs=[excluded_ref],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
            source_refs=[attached_ref],
        )
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What did Alice archive about Shanghai rail?",
            budget=80,
        )
    )

    excluded = next(
        row
        for row in package.metadata["component_accounting"]
        if row["event_type"] == "archival_scope_excluded"
        and row["item_id"] == "apsg_excluded"
    )
    assert excluded["component"] == "archival"
    assert excluded["source_ids"] == ["msg_excluded"]
    assert excluded["source_refs"][0]["source_id"] == "msg_excluded"
    assert excluded["included"] is False
    assert excluded["dropped"] is False
    assert excluded["metadata"]["archive_id"] == "archive_excluded"


def test_v3_composer_reports_no_attached_archive_diagnostic(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="Is any archive attached?",
            budget=80,
        )
    )

    eligibility = package.metadata["archival_eligibility"]
    assert eligibility["archival_no_attached_archive"] is True
    assert any(
        row["event_type"] == "archival_no_attached_archive"
        and row["component"] == "archival"
        and row["included"] is False
        and row["dropped"] is False
        for row in package.metadata["component_accounting"]
    )


def test_v3_composer_uses_archival_vector_search_with_source_refs(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_archival_vector_enabled=True,
    )
    store = create_store(settings)
    store.reset()
    target_ref = _ref("msg_target")
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_target",
            archive_id="archive_attached",
            text="semantic-target metro preference",
            source_refs=[target_ref],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_lexical",
            archive_id="archive_attached",
            text="favorite transport distractor",
            source_refs=[_ref("msg_lexical")],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
            source_refs=[target_ref],
        )
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        archival_searcher=_vector_searcher(
            store,
            "memoryos_archival_composer_vector",
        ),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="favorite transport",
            budget=80,
        )
    )

    archival_items = [item for item in package.items if item.layer == "archival"]
    assert archival_items[0].item_id == "apsg_target"
    assert archival_items[0].metadata["source"] == "archival_vector"
    assert archival_items[0].source_refs[0].source_id == "msg_target"
    selected = next(
        row
        for row in package.metadata["component_accounting"]
        if row["event_type"] == "archival_selected"
    )
    assert selected["item_id"] == "apsg_target"
    assert selected["source_ids"] == ["msg_target"]


def test_v3_composer_records_archival_vector_fallback_diagnostics(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_archival_vector_enabled=True,
    )
    store = create_store(settings)
    store.reset()
    ref = _ref()
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_1",
            archive_id="archive_attached",
            text="Shanghai rail lexical fallback",
            source_refs=[ref],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
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
            task="Shanghai rail",
            budget=80,
        )
    )

    event_types = {
        row["event_type"] for row in package.metadata["component_accounting"]
    }
    assert "archival_vector_unavailable" in event_types
    assert "archival_lexical_fallback" in event_types


def test_v3_composer_filters_unattached_passage_before_archival_vector_search(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_archival_vector_enabled=True,
    )
    store = create_store(settings)
    store.reset()
    attached_ref = _ref("msg_attached")
    unattached_ref = _ref("msg_unattached")
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_attached",
            archive_id="archive_attached",
            text="favorite transport attached fallback",
            source_refs=[attached_ref],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_unattached",
            archive_id="archive_unattached",
            text="semantic-target unattached best vector",
            source_refs=[unattached_ref],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
            source_refs=[attached_ref],
        )
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        archival_searcher=_vector_searcher(
            store,
            "memoryos_archival_composer_scope_filter",
        ),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="favorite transport",
            budget=80,
        )
    )

    archival_item_ids = [item.item_id for item in package.items if item.layer == "archival"]
    assert "apsg_unattached" not in archival_item_ids
    assert package.metadata["archival_eligibility"]["selected_passage_ids"] == [
        "apsg_attached"
    ]
    assert "apsg_unattached" in package.metadata["archival_eligibility"][
        "scope_excluded_passage_ids"
    ]


def test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_budget_dropped",
            archive_id="archive_attached",
            text="Shanghai rail " + ("padding " * 200),
            source_refs=[ref],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
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
            task="Shanghai rail?",
            budget=20,
        )
    )

    assert [item.item_id for item in package.items if item.layer == "archival"] == []
    eligibility = package.metadata["archival_eligibility"]
    assert eligibility["eligible_passage_count"] == 1
    assert eligibility["selected_passage_ids"] == []
    assert eligibility["selected_source_refs"] == []
    assert eligibility["selected_passage_count"] == 0
    archival_budget = [
        decision for decision in package.budget_decisions if decision.layer == "archival"
    ][0]
    assert archival_budget.dropped_item_ids == ["apsg_budget_dropped"]
    selected_events = [
        diagnostic
        for diagnostic in package.diagnostics
        if diagnostic.event_type == "archival_selected"
    ]
    assert selected_events == []


def test_v3_composer_records_component_accounting_for_included_and_budget_dropped_items(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    store.add_message(
        Message(
            id="msg_recall",
            session_id="ses_1",
            role=Role.USER,
            content="Shanghai rail marker.",
            token_count=3,
        )
    )
    ref = _ref("msg_archival")
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_budget_dropped",
            archive_id="archive_attached",
            text="Shanghai rail " + ("padding " * 200),
            source_refs=[ref],
        )
    )
    store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_attached",
            archive_id="archive_attached",
            scope_type="session",
            scope_id="ses_1",
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
            task="Shanghai rail?",
            budget=20,
        )
    )

    accounting = package.metadata["component_accounting"]
    assert any(
        row["component"] == "recall"
        and row["item_id"] == "msg_recall"
        and row["source_ids"] == ["msg_recall"]
        and row["included"] is True
        and row["dropped"] is False
        for row in accounting
    )
    dropped = next(
        row for row in accounting if row["item_id"] == "apsg_budget_dropped"
    )
    assert dropped["component"] == "archival"
    assert dropped["source_ids"] == ["msg_archival"]
    assert dropped["estimated_tokens"] > 0
    assert dropped["included"] is False
    assert dropped["dropped"] is True
    assert dropped["reason_code"] == "budget_drop"


def test_v3_composer_final_context_trace_flattens_selected_source_refs(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    store.add_message(
        Message(
            id="msg_selected",
            session_id="ses_1",
            role=Role.USER,
            content="The selected recall source says MemoryOS Lite.",
            token_count=7,
        )
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What says MemoryOS Lite?",
            budget=80,
        )
    )

    trace = package.metadata["final_context_trace"]
    recall_row = next(
        row for row in trace if row["component"] == "recall" and row["item_id"] == "msg_selected"
    )
    assert recall_row["source_ids"] == ["msg_selected"]
    assert isinstance(recall_row["rendered_index"], int)
    assert recall_row["included"] is True
    assert recall_row["dropped"] is False
    assert all(row["dropped"] is False for row in trace)


def test_v3_composer_final_trace_preserves_signed_packet_member_offsets(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    for message_id, content in [
        ("d1_prev", "Lena packed the notebooks."),
        ("d1_anchor", "Lena chose the target cafe."),
        ("d1_next", "She ordered jasmine tea."),
    ]:
        store.add_message(
            Message(
                id=message_id,
                session_id="ses_1",
                role=Role.USER,
                content=content,
                metadata={"benchmark_session_id": "D1"},
                token_count=len(content.split()),
            )
        )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="target cafe",
            budget=100,
        )
    )

    trace = package.metadata["final_context_trace"]
    anchor_row = next(
        row for row in trace
        if row["component"] == "recall" and row["item_id"] == "d1_anchor"
    )
    assert anchor_row["metadata"]["packet_member_neighbor_offsets"] == [
        {"message_id": "d1_prev", "neighbor_offset": -1},
        {"message_id": "d1_anchor", "neighbor_offset": 0},
        {"message_id": "d1_next", "neighbor_offset": 1},
    ]


def test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    for message in [
        Message(
            id="msg_d1_1",
            session_id="ses_1",
            role=Role.USER,
            content="Alice set up the picnic plan yesterday.",
            metadata={"benchmark_session_id": "D1", "benchmark_date": "2026-01-01"},
            token_count=7,
        ),
        Message(
            id="msg_d1_2",
            session_id="ses_1",
            role=Role.USER,
            content="The queried temporal marker is MemoryOS Lite.",
            metadata={"benchmark_session_id": "D1", "benchmark_date": "2026-01-01"},
            token_count=7,
        ),
        Message(
            id="msg_d2_1",
            session_id="ses_1",
            role=Role.USER,
            content="D2 adjacent distractor should not be a neighbor.",
            metadata={"benchmark_session_id": "D2", "benchmark_date": "2026-01-02"},
            token_count=8,
        ),
    ]:
        store.add_message(message)

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What is the queried temporal marker?",
            budget=100,
        )
    )

    neighbor_rows = [
        row for row in package.metadata["final_context_trace"]
        if row["component"] == "recall" and row["metadata"].get("neighbor_of") == "msg_d1_2"
    ]
    assert any(row["item_id"] == "msg_d1_1" for row in neighbor_rows)
    assert all(row["item_id"] != "msg_d2_1" for row in neighbor_rows)
    assert any(
        row["item_id"] == "msg_d1_1"
        and row["source_ids"] == ["msg_d1_1"]
        and row["metadata"]["benchmark_session_id"] == "D1"
        for row in package.metadata["locomo_neighbor_diagnostics"]
    )


def test_v3_composer_records_locomo_neighbor_budget_drop(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    store.add_message(
        Message(
            id="msg_neighbor",
            session_id="ses_1",
            role=Role.USER,
            content="same-session neighbor " + ("padding " * 80),
            metadata={"benchmark_session_id": "D1", "benchmark_date": "2026-01-01"},
            token_count=82,
        )
    )
    store.add_message(
        Message(
            id="msg_hit",
            session_id="ses_1",
            role=Role.USER,
            content="The compact marker is MemoryOS Lite.",
            metadata={"benchmark_session_id": "D1", "benchmark_date": "2026-01-01"},
            token_count=6,
        )
    )

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What is the compact marker?",
            budget=18,
        )
    )

    dropped = next(
        row for row in package.metadata["locomo_neighbor_diagnostics"]
        if row["item_id"] == "msg_neighbor"
    )
    assert dropped["source_ids"] == ["msg_neighbor"]
    assert dropped["metadata"]["neighbor_of"] == "msg_hit"
    assert dropped["included"] is False
    assert dropped["dropped"] is True
    assert dropped["reason_code"] == "budget_drop"


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
            budget=120,
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


def test_v3_composer_renders_approved_core_promotion_with_provenance(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    core = CoreMemoryService(store, TokenEstimator())
    lifecycle = MemoryLifecycleService(store, core)

    core.create_block(
        label="human",
        description="stable user facts",
        value="Alice prefers trains.",
        limit_tokens=40,
        source_refs=[ref],
        actor="user",
        reason="seed human profile",
    )

    candidate = archival_to_core_candidate(
        "Alice prefers rail travel.",
        source_refs=[ref],
        reason="promote stable preference",
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
    lifecycle.apply_candidate(candidate, actor="agent", approval_state=approved)

    package = V3ContextComposer(
        store=store,
        settings=settings,
        tokenizer=TokenEstimator(),
    ).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="What does Alice prefer?",
            budget=120,
        )
    )

    core_items = [item for item in package.items if item.layer == "core"]
    assert len(core_items) == 1
    assert "Alice prefers rail travel." in core_items[0].text
    assert core_items[0].source_refs[0].source_id == "msg_1"
    assert core_items[0].metadata["metadata"]["promotion_candidate_id"] == candidate.id
    assert core_items[0].metadata["metadata"]["approval_id"] == approved.id
    assert core_items[0].metadata["tokens_current"] > 0


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
