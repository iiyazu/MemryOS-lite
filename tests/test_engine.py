from unittest.mock import patch

from memoryos_lite.cache import (
    CacheDiagnostics,
    CacheReadResult,
    CacheStatus,
    CacheWriteResult,
)
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import (
    MemoryItem,
    MemoryItemType,
    MemoryPage,
    MemoryPageDraft,
    MemoryPatch,
    MessageCreate,
    PageType,
    PatchOperation,
    Role,
)
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    ArchivalPassage,
    ArchiveAttachment,
    ContextPackageV3,
    CoreMemoryBlock,
    SourceRef,
)


def test_context_builder_first_multi_evidence_matching_is_narrow(service):
    assert service.context_builder._needs_multi_evidence("Which event did I attend first?") is True
    assert service.context_builder._needs_multi_evidence("What is my first name?") is False
    assert service.context_builder._needs_multi_evidence("What did I think at first?") is False

def test_context_builder_retrieves_relevant_page(service):
    session = service.create_session("test")
    service.settings.rot_safe_budget = 1
    for content in [
        "用户目标是在 20 天内完成 Agent infra 项目。",
        "最终决定不做 Runbook Oncall Agent，改做 MemoryOS Lite。",
        "技术栈选择 LangGraph 和 FastAPI。",
        "需要 benchmark 对比 Sliding Window 和 Vector RAG。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
    page = service.page(session.id)

    context = service.build_context(session.id, "用户最终决定做什么项目？", budget=800)

    assert page is not None
    loaded_ids = [item.page_id for item in context.retrieved_pages + context.active_task_pages]
    assert page.id in loaded_ids
    assert context.estimated_tokens <= 800


def test_v3_build_context_includes_core_memory_diagnostics(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")
    service = MemoryOSService(settings=settings)
    session = service.create_session("core-memory-v3")
    service.store.create_core_memory_block(
        CoreMemoryBlock(
            id="core_1",
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=100,
            source_refs=[SourceRef(source_type="message", source_id="msg_1")],
            tags=["profile"],
            metadata={"scope": "human"},
        )
    )

    context = service.build_context(session.id, "用户住在哪里？", budget=200)

    assert context.metadata["memory_arch"] == "v3"
    assert context.metadata["v3_layer_counts"]["core"] == 1
    assert any("<memory_blocks>" in item for item in context.pinned_core)
    core_diagnostics = [
        d for d in context.metadata["v3_diagnostics"] if d["layer"] == "core"
    ]
    assert core_diagnostics
    assert core_diagnostics[0]["metadata"]["tags"] == ["profile"]


def test_v3_build_context_promotes_cache_diagnostics_to_legacy_metadata(
    tmp_path,
    monkeypatch,
):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_recall_cache_enabled=True,
    )
    service = MemoryOSService(settings=settings)
    session = service.create_session("v3-cache-metadata")
    v3_metadata = {
        "cache": {"status": "miss", "scope": "recall_context_package"},
        "recall_cache": {"status": "miss", "scope": "recall_context_package"},
        "query_analysis_cache": {"status": "hit", "scope": "query_analysis"},
        "recall_candidate_cache": {"status": "hit", "scope": "recall_candidates"},
        "recall_memory_watermark": "messages:1",
    }

    def fake_build(request):
        return ContextPackageV3(
            session_id=request.session_id,
            task=request.task,
            metadata=v3_metadata,
        )

    monkeypatch.setattr(service.v3_context_composer, "build", fake_build)

    context = service.build_context(session.id, "Where did Bob move?", budget=120)

    assert context.metadata["cache"] == v3_metadata["cache"]
    assert context.metadata["recall_cache"] == v3_metadata["recall_cache"]
    assert context.metadata["query_analysis_cache"] == v3_metadata[
        "query_analysis_cache"
    ]
    assert context.metadata["recall_candidate_cache"] == v3_metadata[
        "recall_candidate_cache"
    ]
    assert context.metadata["recall_memory_watermark"] == "messages:1"
    assert context.metadata["v3_context"]["metadata"]["cache"] == v3_metadata["cache"]


def test_v3_internal_recall_cache_remains_disabled_by_cache_flag(tmp_path):
    class CountingDerivedCache:
        backend_name = "counting"

        def __init__(self) -> None:
            self.get_calls = 0
            self.set_calls = 0
            self.delete_calls = 0

        def get(self, key: str) -> CacheReadResult:
            self.get_calls += 1
            return CacheReadResult(status=CacheStatus.MISS, key=key)

        def set(self, key, entry, *, ttl_s=None) -> CacheWriteResult:
            self.set_calls += 1
            return CacheWriteResult(status=CacheStatus.STORED, key=key)

        def delete(self, key: str) -> CacheWriteResult:
            self.delete_calls += 1
            return CacheWriteResult(status=CacheStatus.STORED, key=key)

        def status(self) -> CacheDiagnostics:
            return CacheDiagnostics(
                status=CacheStatus.DISABLED,
                metadata={"backend": self.backend_name, "enabled": False},
            )

    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v1",
        memoryos_recall_cache_enabled=False,
    )
    service = MemoryOSService(settings=settings)
    cache = CountingDerivedCache()
    service.recall_pipeline.cache = cache
    session = service.create_session("v3-cache-disabled")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Bob moved to Shanghai."),
    )

    context = service.build_context(session.id, "Where did Bob move?", budget=160)

    assert context.metadata["memory_arch"] == "v3"
    assert context.metadata["recall_cache"]["enabled"] is False
    assert context.metadata["recall_cache"]["status"] == "disabled"
    assert context.metadata["recall_memory_watermark"]
    assert cache.get_calls == 0
    assert cache.set_calls == 0
    assert cache.delete_calls == 0


def test_explicit_v1_build_context_excludes_v3_core_memory_blocks(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")
    service = MemoryOSService(settings=settings)
    session = service.create_session("core-memory-v1")
    service.store.create_core_memory_block(
        CoreMemoryBlock(
            id="core_1",
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=100,
            source_refs=[SourceRef(source_type="message", source_id="msg_1")],
            tags=["profile"],
        )
    )

    context = service.build_context(session.id, "用户住在哪里？", budget=200)

    assert context.metadata.get("memory_arch") != "v3"
    assert "v3_diagnostics" not in context.metadata
    assert "Alice lives in Shanghai." not in context.model_dump_json()


def test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")
    service = MemoryOSService(settings=settings)
    session = service.create_session("archival-scope-v1")
    ref = SourceRef(source_type="message", source_id="msg_1", session_id=session.id)
    service.store.create_archival_passage(
        ArchivalPassage(
            id="apsg_v1_hidden",
            archive_id="archive_1",
            text="Alice lives in a scoped archival passage.",
            source_refs=[ref],
        )
    )
    service.store.create_archive_attachment(
        ArchiveAttachment(
            id="aatt_v1_hidden",
            archive_id="archive_1",
            scope_type="session",
            scope_id=session.id,
            source_refs=[ref],
        )
    )

    context = service.build_context(session.id, "用户住在哪里？", budget=200)

    assert context.metadata.get("memory_arch") != "v3"
    assert "archival_eligibility" not in context.metadata
    assert "v3_diagnostics" not in context.metadata
    assert "Alice lives in a scoped archival passage." not in context.model_dump_json()


def test_v3_build_context_trace_includes_component_accounting_and_final_context_trace(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")
    service = MemoryOSService(settings=settings)
    session = service.create_session("v3-accounting")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Carol's benchmark marker is MemoryOS Lite."),
    )

    context = service.build_context(session.id, "What is Carol's benchmark marker?", budget=120)

    assert context.metadata["v3_component_accounting"]
    assert context.metadata["v3_final_context_trace"]
    assert context.metadata["v3_component_token_totals"]["recall"] > 0
    assert context.metadata["v3_component_drop_counts"]["recall"] == 0
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["v3_component_accounting"] == context.metadata[
        "v3_component_accounting"
    ]
    assert context_built.payload["v3_final_context_trace"] == context.metadata[
        "v3_final_context_trace"
    ]


def test_explicit_v1_build_context_excludes_v3_component_accounting(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")
    service = MemoryOSService(settings=settings)
    session = service.create_session("v1-no-accounting")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Carol's benchmark marker is MemoryOS Lite."),
    )

    context = service.build_context(session.id, "What is Carol's benchmark marker?", budget=120)

    assert context.metadata.get("memory_arch") != "v3"
    assert "v3_component_accounting" not in context.metadata
    assert "v3_final_context_trace" not in context.metadata
    assert "v3_component_token_totals" not in context.metadata
    assert "locomo_neighbor_diagnostics" not in context.metadata


def test_context_builder_deduplicates_pinned_core_pages_by_id(service):
    session = service.create_session("test")
    summary = "用户长期稳定方案是 MemoryOS Lite，并且关注 source attribution。"
    core_page = MemoryPage(
        id="core_profile_test",
        session_id=session.id,
        page_type=PageType.CORE_PROFILE,
        title="Core profile",
        summary=summary,
    )
    same_text_page = MemoryPage(
        id="source_summary_same_text",
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="Same text source",
        summary=summary,
    )
    service.store.save_page(core_page)
    service.store.save_page(same_text_page)
    task = "用户长期稳定方案是什么？"
    task_tokens = service.tokenizer.count(task)
    page_tokens = service.tokenizer.count(summary)
    budget = task_tokens + (page_tokens * 3)

    context = service.build_context(session.id, task, budget=budget)

    loaded_ids = [item.page_id for item in context.retrieved_pages + context.active_task_pages]
    assert context.pinned_core == [summary]
    assert core_page.id not in loaded_ids
    assert same_text_page.id in loaded_ids
    assert context.estimated_tokens == task_tokens + (page_tokens * 2)
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["retrieved_pages"] == [context.retrieved_pages[0].model_dump()]
    retrieved = context_built.payload["retrieved_pages"][0]
    assert retrieved["page_id"] == same_text_page.id
    assert retrieved["reason"].startswith("rrf ")
    assert retrieved["estimated_tokens"] == page_tokens


def test_context_builder_audits_core_profile_dropped_over_budget(service):
    session = service.create_session("test")
    summary = "用户长期稳定方案是 MemoryOS Lite。" * 80
    core_page = MemoryPage(
        id="core_profile_over_budget",
        session_id=session.id,
        page_type=PageType.CORE_PROFILE,
        title="Large core profile",
        summary=summary,
    )
    service.store.save_page(core_page)
    task = "用户长期稳定方案是什么？"
    budget = service.tokenizer.count(task) + 1

    context = service.build_context(session.id, task, budget=budget)

    assert context.pinned_core == []
    assert context.retrieved_pages == []
    assert context.active_task_pages == []
    assert len(context.dropped_pages) == 1
    dropped = context.dropped_pages[0]
    assert dropped.page_id == core_page.id
    assert dropped.reason == "core_profile_exceeds_budget"
    assert dropped.estimated_tokens == service.tokenizer.count(summary)
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.event_type == "context_built"
    assert context_built.payload["task_tokens"] == context.task_tokens
    assert context_built.payload["task_truncated"] is False
    assert context_built.payload["pinned_core_count"] == 0
    assert context_built.payload["pinned_core_tokens"] == 0
    assert context_built.payload["active_task_pages"] == []
    assert context_built.payload["dropped_recent_messages"] == []
    assert context_built.payload["dropped_pages"] == [dropped.model_dump()]


def test_context_builder_uses_raw_evidence_when_page_is_over_budget(service):
    session = service.create_session("test")
    evidence_message = service.ingest(
        session.id,
        MessageCreate(
            role=Role.USER,
            content="[7 May 2023] Caroline attended the LGBTQ support group.",
        ),
    ).message
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Recent distractor about unrelated plans."),
    )
    large_page = MemoryPage(
        id="large_profile_with_source",
        session_id=session.id,
        page_type=PageType.CORE_PROFILE,
        title="Large profile",
        summary="Caroline background and support group details. " * 80,
        source_message_ids=[evidence_message.id],
    )
    service.store.save_page(large_page)

    context = service.build_context(
        session.id,
        "When did Caroline attend the LGBTQ support group?",
        budget=80,
    )

    assert context.retrieved_pages == []
    assert context.pinned_core == []
    assert context.dropped_pages[0].page_id == large_page.id
    assert context.retrieved_evidence
    assert context.retrieved_evidence[0].message_id == evidence_message.id
    assert context.retrieved_evidence[0].page_id == large_page.id
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["retrieved_evidence"][0]["message_id"] == evidence_message.id


def test_context_builder_can_recover_raw_evidence_from_superseded_page(service):
    session = service.create_session("superseded evidence")
    evidence_message = service.ingest(
        session.id,
        MessageCreate(
            role=Role.USER,
            content="[7 May 2023] Caroline attended the LGBTQ support group.",
        ),
    ).message
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Recent distractor."))
    superseded_page = MemoryPage(
        id="old_page_with_source",
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="Old evidence page",
        summary="Caroline attended the support group.",
        source_message_ids=[evidence_message.id],
        superseded_by="newer_page",
    )
    active_page = MemoryPage(
        id="newer_page",
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="New page",
        summary="Unrelated active page.",
        source_message_ids=[],
    )
    service.store.save_page(superseded_page)
    service.store.save_page(active_page)

    context = service.build_context(
        session.id,
        "When did Caroline attend the LGBTQ support group?",
        budget=80,
    )

    assert context.retrieved_pages == []
    assert context.retrieved_evidence
    evidence = context.retrieved_evidence[0]
    assert evidence.message_id == evidence_message.id
    assert evidence.page_id == superseded_page.id
    assert evidence.superseded is True
    assert context.superseded_source_recovered == 1
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["superseded_source_recovered"] == 1
    assert context_built.payload["retrieved_evidence"][0]["superseded"] is True


def test_context_builder_reserves_budget_for_raw_evidence_before_core_pages(service):
    session = service.create_session("evidence reserve")
    service.settings.memoryos_evidence_reserve_ratio = 0.5
    service.settings.memoryos_evidence_reserve_tokens = 64
    service.settings.memoryos_evidence_reserve_min_pages = 1
    evidence_message = service.ingest(
        session.id,
        MessageCreate(
            role=Role.USER,
            content="Caroline attended the LGBTQ support group on 7 May 2023.",
        ),
    ).message
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Recent distractor."))
    core_summary = "Core profile detail about Caroline support group context."
    for index in range(3):
        service.store.save_page(
            MemoryPage(
                id=f"core_page_{index}",
                session_id=session.id,
                page_type=PageType.CORE_PROFILE,
                title=f"Core page {index}",
                summary=core_summary,
                source_message_ids=[],
            )
        )
    service.store.save_page(
        MemoryPage(
            id="evidence_page",
            session_id=session.id,
            page_type=PageType.SOURCE_SUMMARY,
            title="Evidence page",
            summary="Support group evidence.",
            source_message_ids=[evidence_message.id],
        )
    )
    task = "When did Caroline attend the LGBTQ support group?"
    budget = (
        service.tokenizer.count(task)
        + service.tokenizer.count(core_summary) * 3
        + service.tokenizer.count(evidence_message.content)
        - 1
    )

    context = service.build_context(session.id, task, budget=budget)

    assert context.retrieved_evidence
    assert context.retrieved_evidence[0].message_id == evidence_message.id
    assert context.candidate_budget_dropped == 0
    assert len(context.pinned_core) < 3
    assert any(item.reason == "core_profile_exceeds_budget" for item in context.dropped_pages)


def test_context_builder_compacts_long_raw_evidence_to_fit_budget(service):
    session = service.create_session("test")
    service.settings.memoryos_evidence_max_tokens = 32
    evidence_message = service.ingest(
        session.id,
        MessageCreate(
            role=Role.USER,
            content=(
                "[7 May 2023] Caroline attended the LGBTQ support group downtown. "
                + "Unrelated filler about errands and planning. " * 80
            ),
        ),
    ).message
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Recent distractor."))
    large_page = MemoryPage(
        id="large_profile_with_long_source",
        session_id=session.id,
        page_type=PageType.CORE_PROFILE,
        title="Large profile",
        summary="Caroline background and support group details. " * 80,
        source_message_ids=[evidence_message.id],
    )
    service.store.save_page(large_page)
    task = "When did Caroline attend the LGBTQ support group?"
    budget = service.tokenizer.count(task) + service.settings.memoryos_evidence_max_tokens + 4

    context = service.build_context(session.id, task, budget=budget)

    assert context.retrieved_evidence
    evidence = context.retrieved_evidence[0]
    assert evidence.message_id == evidence_message.id
    assert evidence.page_id == large_page.id
    assert "LGBTQ support group" in evidence.text
    assert evidence.estimated_tokens <= service.settings.memoryos_evidence_max_tokens
    assert evidence.estimated_tokens < evidence_message.token_count

def test_context_builder_loads_relevant_smaller_page_under_fixed_budget(service):
    session = service.create_session("small page budget")
    service.settings.recent_message_limit = 1
    service.settings.memoryos_page_window_max_messages = 2
    service.settings.memoryos_page_window_max_tokens = 10_000
    relevant = []
    for content in [
        "Caroline attended the LGBTQ support group on 7 May 2023.",
        "Caroline said the LGBTQ support group met downtown.",
    ]:
        relevant.append(
            service.ingest(session.id, MessageCreate(role=Role.USER, content=content)).message
        )
    for content in [
        "Unrelated travel planning notes. " * 80,
        "Unrelated grocery and weather notes. " * 80,
        "Recent distractor.",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
    service.page(session.id)
    pages = service.store.list_pages(session.id)
    relevant_page = next(
        page
        for page in pages
        if set(relevant_message.id for relevant_message in relevant) <= set(page.source_message_ids)
    )
    task = "When did Caroline attend the LGBTQ support group?"
    budget = (
        service.tokenizer.count(task)
        + service.tokenizer.count(relevant_page.summary)
        + sum(message.token_count for message in relevant)
        + 2
    )

    context = service.build_context(session.id, task, budget=budget)

    loaded_ids = [item.page_id for item in context.retrieved_pages + context.active_task_pages]
    assert relevant_page.id in loaded_ids
    assert relevant_page.id not in {item.page_id for item in context.dropped_pages}

def test_context_builder_drops_recent_messages_over_budget(service):
    session = service.create_session("test")
    for index in range(5):
        service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content=f"这是第 {index} 条很长的近期消息 " * 20),
        )

    context = service.build_context(session.id, "短任务", budget=20)

    assert context.estimated_tokens <= 20
    assert context.dropped_recent_messages
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["dropped_recent_messages"] == context.dropped_recent_messages


def test_context_builder_counts_over_budget_task_truthfully(service):
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="应该被预算丢弃的消息"))
    task = "超长任务 " * 200
    task_tokens = service.tokenizer.count(task)

    context = service.build_context(session.id, task, budget=20)

    assert task_tokens > 20
    assert context.task_tokens == task_tokens
    assert context.task_truncated is True
    assert context.estimated_tokens == task_tokens
    assert context.recent_messages == []
    assert context.dropped_recent_messages
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["task_tokens"] == task_tokens
    assert context_built.payload["task_truncated"] is True


def test_patch_verifier_rejects_missing_old_text(service):
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="用户想做 MemoryOS Lite。"))
    service.ingest(session.id, MessageCreate(role=Role.USER, content="技术栈选择 LangGraph。"))
    service.ingest(session.id, MessageCreate(role=Role.USER, content="需要 source trace。"))
    service.ingest(session.id, MessageCreate(role=Role.USER, content="需要 Context Builder。"))
    page = service.page(session.id)
    assert page is not None

    patch = MemoryPatch(
        operation=PatchOperation.REPLACE,
        target_page_id=page.id,
        old_text="不存在的旧内容",
        new_text="用户不想做 Oncall Agent",
        reason="测试 verifier",
        source_refs=[page.source_message_ids[0]],
    )

    verified = service.commit_patch(session.id, patch)

    assert verified.verified is False
    assert any("old_text" in error for error in verified.errors)


class FakeDraftClient:
    def create_draft(self, messages, context_pages=None):
        return MemoryPageDraft(
            title="fake llm page",
            summary="LLM 生成的记忆页",
            facts=["LLM 生成"],
            source_message_ids=[message.id for message in messages],
        )


class FailingDraftClient:
    def create_draft(self, messages, context_pages=None):
        raise RuntimeError("llm unavailable")

def test_recall_pipeline_defaults_to_v2(tmp_path, monkeypatch):
    from memoryos_lite.config import Settings
    from memoryos_lite.engine import MemoryOSService

    monkeypatch.delenv("MEMORYOS_RECALL_PIPELINE", raising=False)
    settings = Settings(data_dir=tmp_path / ".memoryos")
    service = MemoryOSService(settings=settings)
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="事实 A"))

    assert service.settings.memoryos_recall_pipeline == "v2"

def test_fastembed_provider_falls_back_to_no_embedding_when_unavailable(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_embedding_provider="fastembed",
    )
    store = create_store(settings)
    store.reset()

    with patch(
        "memoryos_lite.retrieval.providers.fastembed_client.FastEmbedClient",
        side_effect=RuntimeError("model unavailable"),
    ):
        service = MemoryOSService(store=store, settings=settings)

    assert service.embedding_client is None


def test_service_wires_archival_qdrant_separately_from_page_qdrant(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        qdrant_url=":memory:",
        qdrant_collection="memoryos_pages_test",
        memoryos_archival_vector_enabled=True,
        memoryos_archival_qdrant_url=":memory:",
        memoryos_archival_qdrant_collection="memoryos_archival_passages_test",
    )

    service = MemoryOSService(
        settings=settings,
        embedding_client=DeterministicEmbeddingClient(),
    )

    assert service.qdrant_store is not None
    assert service.archival_qdrant_store is not None
    assert service.qdrant_store.collection == "memoryos_pages_test"
    assert service.archival_qdrant_store.collection == "memoryos_archival_passages_test"
    assert service.qdrant_store.collection != service.archival_qdrant_store.collection
    assert service.v3_context_composer.archival_searcher.vector_index is not None

# ---------------------------------------------------------------------------
# Error recovery mechanisms (evbundle_6ef398723414454ba7212973e08e05f5)
# Tests: retry logic, graceful degradation, state preservation under failure.
# ---------------------------------------------------------------------------


def test_paging_agent_falls_back_gracefully_when_llm_draft_client_raises(tmp_path):
    """PagingAgent falls back to heuristic mode when the LLM draft client raises,
    and does not corrupt the message store."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_paging_mode="llm",
        openai_api_key="sk-test-dummy",
    )
    store = create_store(settings)
    store.reset()

    with patch(
        "memoryos_lite.legacy_paging.OpenAIPageDraftClient.create_draft",
        side_effect=RuntimeError("llm unavailable"),
    ):
        service = MemoryOSService(store=store, settings=settings)
        session = service.create_session("fallback-test")
        for content in [
            "用户目标是完成 MemoryOS Lite。",
            "技术栈选择 LangGraph 和 FastAPI。",
            "需要 benchmark 对比 Sliding Window 和 Vector RAG。",
            "最终决定不做 Runbook Oncall Agent。",
        ]:
            service.ingest(session.id, MessageCreate(role=Role.USER, content=content))

        # page() must not raise even when the LLM client fails
        service.page(session.id)

    # Messages must be intact regardless of paging outcome
    messages = service.store.list_messages(session.id)
    assert len(messages) == 4
    # Traces must record the paging outcome (skipped or committed)
    traces = service.store.list_traces(session.id)
    paging_events = [t for t in traces if t.event_type in ("paging_skipped", "page_committed")]
    assert paging_events


def test_ingest_preserves_all_messages_when_paging_raises(tmp_path):
    """All ingested messages survive even if page() raises an unexpected error."""
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("ingest-resilience")

    for i in range(3):
        service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content=f"Message {i}: stable fact."),
        )

    with patch.object(service.paging_agent, "create_drafts", side_effect=RuntimeError("boom")):
        try:
            service.page(session.id)
        except RuntimeError:
            pass

    # All messages must still be present — ingest is independent of paging
    messages = service.store.list_messages(session.id)
    assert len(messages) == 3


def test_build_context_returns_empty_package_when_store_list_pages_raises(tmp_path):
    """build_context degrades gracefully when the page store raises, returning
    a valid (possibly empty) ContextPackage without corrupting session state."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recovery_max_attempts=2,
        memoryos_recovery_initial_delay_s=0,
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    service.recovery._sleep = lambda _delay: None
    session = service.create_session("context-degradation")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Alice lives in Shanghai."))

    with patch.object(service.store, "list_pages", side_effect=RuntimeError("db error")):
        context = service.build_context(session.id, "Where does Alice live?", budget=200)

    assert context.session_id == session.id
    assert context.metadata["degraded"] is True
    assert context.metadata["degraded_component"] == "page_store"
    # Whether the service swallows or re-raises, the message must still be intact
    messages = service.store.list_messages(session.id)
    assert len(messages) == 1
    assert messages[0].content == "Alice lives in Shanghai."
    traces = service.store.list_traces(session.id)
    assert any(t.event_type == "recovery_event" for t in traces)
    assert any(t.event_type == "context_degraded" for t in traces)


def test_v3_context_composer_retry_then_degrades_to_recall_pipeline(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_recovery_max_attempts=2,
        memoryos_recovery_initial_delay_s=0,
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    service.recovery._sleep = lambda _delay: None
    session = service.create_session("v3-recovery")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Alice lives in Shanghai."))

    with patch.object(
        service.v3_context_composer,
        "build",
        side_effect=TimeoutError("temporary composer outage"),
    ):
        context = service.build_context(session.id, "Where does Alice live?", budget=200)

    assert context.session_id == session.id
    traces = service.store.list_traces(session.id)
    recovery_events = [t for t in traces if t.event_type == "recovery_event"]
    assert any(t.payload["kind"] == "retry_scheduled" for t in recovery_events)
    assert any(t.event_type == "context_degraded" for t in traces)


def test_page_embedding_failure_degrades_and_records_recovery(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recovery_max_attempts=1,
    )
    service = MemoryOSService(
        settings=settings,
        embedding_client=DeterministicEmbeddingClient(),
    )
    service.recovery._sleep = lambda _delay: None
    session = service.create_session("embedding-recovery")
    page = MemoryPage(
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="Page",
        summary="Alice lives in Shanghai.",
    )

    with patch.object(
        service.embedding_client,
        "embed",
        side_effect=TimeoutError("temporary embedding outage"),
    ):
        service._index_page_embedding(page)

    traces = service.store.list_traces(session.id)
    assert any(t.event_type == "recovery_event" for t in traces)
    assert any(t.payload["kind"] == "degraded" for t in traces if t.event_type == "recovery_event")


def test_embedding_client_failure_does_not_corrupt_page_store(tmp_path):
    """When the embedding client raises during a search, the page store is not
    modified and previously saved pages remain intact."""
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("embedding-failure")

    page = MemoryPage(
        id="stable_page",
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="Stable page",
        summary="Alice lives in Shanghai.",
    )
    service.store.save_page(page)

    with patch.object(
        service.searcher,
        "search",
        side_effect=RuntimeError("embedding service down"),
    ):
        try:
            service.build_context(session.id, "Where does Alice live?", budget=200)
        except RuntimeError:
            pass

    # The page must still be intact after the failed search
    loaded = service.store.load_page("stable_page")
    assert loaded is not None
    assert loaded.summary == "Alice lives in Shanghai."


def test_patch_verifier_rejects_and_preserves_page_on_bad_old_text(tmp_path):
    """A failed patch (bad old_text) must not modify the page content."""
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("patch-recovery")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Database is PostgreSQL."),
    )
    page = MemoryPage(
        id="patch_recovery_page",
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="DB page",
        summary="Database is PostgreSQL.",
        facts=["Database is PostgreSQL."],
    )
    service.store.save_page(page)

    patch = MemoryPatch(
        operation=PatchOperation.REPLACE,
        target_page_id=page.id,
        old_text="Database is MySQL.",  # wrong — does not exist
        new_text="Database is SQLite.",
        reason="test bad patch",
        source_refs=[],
    )
    result = service.commit_patch(session.id, patch)

    assert result.verified is False
    # Page content must be unchanged
    loaded = service.store.load_page(page.id)
    assert loaded is not None
    assert "PostgreSQL" in loaded.summary
    assert "SQLite" not in loaded.summary


def test_multiple_failed_patches_do_not_accumulate_corruption(tmp_path):
    """Repeated failed patches must not corrupt the page incrementally."""
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("multi-patch-recovery")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Stack is LangGraph."),
    )
    page = MemoryPage(
        id="multi_patch_page",
        session_id=session.id,
        page_type=PageType.SOURCE_SUMMARY,
        title="Stack page",
        summary="Stack is LangGraph.",
        facts=["Stack is LangGraph."],
    )
    service.store.save_page(page)

    for _ in range(3):
        bad_patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=page.id,
            old_text="nonexistent text",
            new_text="corrupted content",
            reason="repeated bad patch",
            source_refs=[],
        )
        result = service.commit_patch(session.id, bad_patch)
        assert result.verified is False

    loaded = service.store.load_page(page.id)
    assert loaded is not None
    assert loaded.summary == "Stack is LangGraph."
    assert "corrupted content" not in loaded.summary


def test_store_allows_embeddings_from_different_providers(service):
    session = service.create_session("mixed-embedding-dims")
    first = MemoryItem(
        page_id="page_test",
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="OpenAI sized vector",
        source_message_ids=["msg_001"],
    )
    second = MemoryItem(
        page_id="page_test",
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="fastembed sized vector",
        source_message_ids=["msg_002"],
    )
    service.store.save_items([first, second])

    service.store.set_item_embedding(first.id, [0.1] * 1536)
    service.store.set_item_embedding(second.id, [0.2] * 384)

    embeddings = service.store.get_item_embeddings([first.id, second.id])
    assert len(embeddings[first.id]) == 1536
    assert len(embeddings[second.id]) == 384
