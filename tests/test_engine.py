from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService, PagingAgent
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import (
    MemoryPage,
    MemoryPageDraft,
    MemoryPatch,
    MessageCreate,
    PageType,
    PatchOperation,
    Role,
)
from memoryos_lite.store import create_store


def test_ingest_triggers_paging_and_commits_page(service):
    session = service.create_session("test")
    messages = [
        "用户目标是在 20 天内完成 Agent infra 项目。",
        "已记录目标。",
        "最终决定不做 Runbook Oncall Agent，改做 MemoryOS Lite。",
        "技术栈选择 LangGraph 和 FastAPI。",
    ]
    last_response = None
    for index, content in enumerate(messages):
        role = Role.USER if index != 1 else Role.ASSISTANT
        last_response = service.ingest(session.id, MessageCreate(role=role, content=content))

    assert last_response is not None
    assert last_response.should_page is True

    page = service.page(session.id)

    assert page is not None
    assert page.source_message_ids
    assert "Agent infra" in page.model_dump_json()
    assert "已记录目标" not in page.model_dump_json()


def test_heuristic_pager_filters_generic_assistant_ack(service):
    session = service.create_session("test")
    service.settings.recent_message_limit = 1
    for role, content in [
        (Role.USER, "项目当前数据库选 PostgreSQL。"),
        (Role.ASSISTANT, "已记录数据库选型。"),
        (Role.USER, "继续看 ORM 文档。"),
        (Role.USER, "最新无关。"),
    ]:
        service.ingest(session.id, MessageCreate(role=role, content=content))

    page = service.page(session.id)

    assert page is not None
    assert "项目当前数据库选 PostgreSQL" in page.summary
    assert all("已记录" not in fact for fact in page.facts)
    assert "已记录" not in page.summary


def test_heuristic_pager_summary_keeps_three_ranked_facts(service):
    session = service.create_session("test")
    service.settings.recent_message_limit = 1
    for content in [
        "数据库选 PostgreSQL。",
        "缓存层选 Redis。",
        "队列选 Kafka。",
        "最新无关。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))

    page = service.page(session.id)

    assert page is not None
    assert "数据库选 PostgreSQL" in page.summary
    assert "缓存层选 Redis" in page.summary
    assert "队列选 Kafka" in page.summary


def test_heuristic_pager_summary_skips_long_unstructured_noise(service):
    session = service.create_session("test")
    service.settings.recent_message_limit = 1
    for content in [
        "排期记录：下周整理文档。",
        "第 1 版稳定方案：MemoryOS Lite。",
        "第 1 段无关长噪声：" + "课程安排、排版偏好、天气记录、临时想法。" * 8,
        "最新无关。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))

    page = service.page(session.id)

    assert page is not None
    assert "MemoryOS Lite" in page.summary
    assert "无关长噪声" not in page.summary


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


def test_context_built_trace_includes_active_task_page_details(service):
    session = service.create_session("test")
    task_page = MemoryPage(
        id="task_state_trace",
        session_id=session.id,
        page_type=PageType.TASK_STATE,
        title="Task state",
        summary="当前稳定方案是 MemoryOS Lite。",
    )
    service.store.save_page(task_page)

    context = service.build_context(session.id, "稳定方案是什么？", budget=200)

    assert len(context.active_task_pages) == 1
    context_built = service.store.list_traces(session.id)[-1]
    assert context_built.payload["active_task_pages"] == [context.active_task_pages[0].model_dump()]
    assert context_built.payload["task_tokens"] == context.task_tokens
    assert context_built.payload["task_truncated"] is False
    assert context_built.payload["dropped_recent_messages"] == []


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
    def create_draft(self, messages):
        return MemoryPageDraft(
            title="fake llm page",
            summary="LLM 生成的记忆页",
            facts=["LLM 生成"],
            source_message_ids=[message.id for message in messages],
        )


class FailingDraftClient:
    def create_draft(self, messages):
        raise RuntimeError("llm unavailable")


def test_paging_agent_uses_llm_client_when_enabled(service):
    service.settings.memoryos_paging_mode = "llm"
    agent = PagingAgent(service.settings, llm_client=FakeDraftClient())
    session = service.create_session("test")
    messages = []
    for content in ["事实 A", "事实 B", "事实 C", "事实 D"]:
        response = service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        messages.append(response.message)

    draft, mode, error = agent.create_draft(session.id, messages)

    assert draft is not None
    assert draft.summary == "LLM 生成的记忆页"
    assert mode == "llm"
    assert error is None


def test_paging_agent_falls_back_when_llm_fails(service):
    service.settings.memoryos_paging_mode = "llm"
    agent = PagingAgent(service.settings, llm_client=FailingDraftClient())
    session = service.create_session("test")
    messages = []
    for content in ["事实 A", "事实 B", "事实 C", "事实 D"]:
        response = service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        messages.append(response.message)

    draft, mode, error = agent.create_draft(session.id, messages)

    assert draft is not None
    assert mode == "heuristic_fallback"
    assert "llm unavailable" in str(error)


def test_service_traces_llm_init_fallback(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_paging_mode="llm",
        rot_safe_budget=1,
        recent_message_limit=2,
    )
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("test")
    for content in ["事实 A", "事实 B", "事实 C", "事实 D"]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))

    page = service.page(session.id)
    traces = service.store.list_traces(session.id)

    assert page is not None
    committed = [trace for trace in traces if trace.event_type == "page_committed"][-1]
    assert committed.payload["paging_mode"] == "heuristic_fallback"
    assert "OPENAI_API_KEY" in committed.payload["paging_error"]


def test_page_save_persists_embedding_and_hybrid_fuses_sources(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(
        store=store,
        settings=settings,
        embedding_client=DeterministicEmbeddingClient(),
    )
    session = service.create_session("test")
    for content in [
        "用户目标是在 20 天内完成 Agent infra 项目。",
        "最终决定不做 Runbook Oncall Agent，改做 MemoryOS Lite。",
        "技术栈选择 LangGraph 和 FastAPI。",
        "需要 benchmark 对比 Sliding Window 和 Vector RAG。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
    page = service.page(session.id)

    assert page is not None
    embeddings = service.store.get_page_embeddings([page.id])
    assert page.id in embeddings
    assert len(embeddings[page.id]) == DeterministicEmbeddingClient.DIM

    hits = service.search("用户最终决定做什么项目？", top_k=3, session_id=session.id)
    assert hits
    assert hits[0].source == "hybrid"
    assert "lexical=" in hits[0].reason and "embedding=" in hits[0].reason
