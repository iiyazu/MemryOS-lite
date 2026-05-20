from unittest.mock import Mock, patch

from memoryos_lite.config import Settings
from memoryos_lite.engine import ItemExtractor, MemoryOSService, OpenAIPageDraftClient, PagingAgent
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


def test_heuristic_pager_adds_temporal_anchors_without_summary_prefix(service):
    session = service.create_session("temporal anchors")
    service.settings.recent_message_limit = 1
    filler = " ".join(f"detail{i}" for i in range(35))
    for role, content in [
        (
            Role.USER,
            "[2023/03/26 (Sun) 22:45] "
            f"{filler} I got back from Sunday mass at St. Mary's Church on March 19th.",
        ),
        (Role.ASSISTANT, "已记录。"),
        (
            Role.USER,
            "[2023/05/28 (Sun) 07:17] "
            f'{filler} I participated in a webinar on "Data Analysis using Python" '
            "two months ago.",
        ),
        (Role.USER, "Recent held back."),
    ]:
        service.ingest(session.id, MessageCreate(role=role, content=content))

    page = service.page(session.id)

    assert page is not None
    assert page.facts[0].startswith("[2023/03/26 (Sun) 22:45]")
    assert "Temporal anchor:" not in page.model_dump_json()
    assert "March 19th" in page.facts[0]
    assert any("two months ago" in fact for fact in page.facts)
    assert all("已记录" not in fact for fact in page.facts)
    assert "March 19th" not in page.summary
    assert "two months ago" not in page.summary


def test_heuristic_pager_profile_check_runs_before_temporal_anchors(service, monkeypatch):
    session = service.create_session("temporal profile")
    service.settings.recent_message_limit = 1
    captured_facts: list[str] = []

    def capture_profile_facts(facts: list[str]) -> bool:
        captured_facts.extend(facts)
        return False

    monkeypatch.setattr(service.paging_agent, "_looks_like_profile", capture_profile_facts)
    filler = " ".join(f"detail{i}" for i in range(35))
    for role, content in [
        (
            Role.USER,
            f"[2023/03/26 (Sun) 22:45] {filler} I live near the event venue on March 19th.",
        ),
        (Role.ASSISTANT, "已记录。"),
        (Role.USER, "[2023/03/27 (Mon) 09:10] Recent held back."),
    ]:
        service.ingest(session.id, MessageCreate(role=role, content=content))

    page = service.page(session.id)

    assert page is not None
    assert page.facts[0].startswith("[2023/03/26 (Sun) 22:45]")
    assert "March 19th" in page.facts[0]
    assert captured_facts
    assert all("March 19th" not in fact for fact in captured_facts)


def test_context_builder_first_multi_evidence_matching_is_narrow(service):
    assert service.context_builder._needs_multi_evidence("Which event did I attend first?") is True
    assert service.context_builder._needs_multi_evidence("What is my first name?") is False
    assert service.context_builder._needs_multi_evidence("What did I think at first?") is False


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


def test_paging_splits_long_session_into_windows_and_preserves_sources(service):
    session = service.create_session("windowed paging")
    service.settings.recent_message_limit = 1
    service.settings.memoryos_page_window_max_messages = 3
    service.settings.memoryos_page_window_max_tokens = 10_000
    ingested_ids = []
    for index in range(10):
        response = service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content=f"Windowed source fact {index}."),
        )
        ingested_ids.append(response.message.id)

    page = service.page(session.id)

    assert page is not None
    pages = service.store.list_pages(session.id)
    assert len(pages) == 3
    assert all(len(memory_page.source_message_ids) <= 3 for memory_page in pages)
    paged_source_ids = {
        source_id for memory_page in pages for source_id in memory_page.source_message_ids
    }
    assert paged_source_ids == set(ingested_ids[:-1])


def test_paging_respects_benchmark_session_boundaries(service):
    session = service.create_session("session boundary paging")
    service.settings.recent_message_limit = 1
    service.settings.memoryos_page_window_max_messages = 50
    service.settings.memoryos_page_window_max_tokens = 10_000
    for benchmark_session in ("D1", "D1", "D2", "D2"):
        service.ingest(
            session.id,
            MessageCreate(
                role=Role.USER,
                content=f"{benchmark_session} source fact.",
                metadata={"benchmark_session_id": benchmark_session},
            ),
        )
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Recent held back."))

    page = service.page(session.id)

    assert page is not None
    pages = service.store.list_pages(session.id)
    assert len(pages) == 2
    messages_by_id = {message.id: message for message in service.store.list_messages(session.id)}
    page_sessions = [
        {
            messages_by_id[source_id].metadata.get("benchmark_session_id")
            for source_id in memory_page.source_message_ids
        }
        for memory_page in pages
    ]
    assert page_sessions == [{"D1"}, {"D2"}]


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
    assert mode == "agentic"
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
        memoryos_llm_provider="openai",
        openai_api_key=None,
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
    # No API key → llm_client is None → heuristic path
    assert committed.payload["paging_mode"] == "heuristic"


def test_recall_pipeline_defaults_to_v1(tmp_path):
    from memoryos_lite.config import Settings
    from memoryos_lite.engine import MemoryOSService

    settings = Settings(data_dir=tmp_path / ".memoryos")
    service = MemoryOSService(settings=settings)
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="事实 A"))

    assert service.settings.memoryos_recall_pipeline == "v1"
    assert service.store.list_episodes(session.id) == []
    assert all(
        trace.event_type != "episode_indexed"
        for trace in service.store.list_traces(session.id)
    )


def test_paging_mode_llm_without_key_returns_heuristic_fallback(service):
    service.settings.memoryos_paging_mode = " LLM "  # whitespace + uppercase
    agent = PagingAgent(service.settings, llm_client=None)
    session = service.create_session("test")
    messages = []
    for content in ["事实 A", "事实 B", "事实 C", "事实 D"]:
        response = service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        messages.append(response.message)

    draft, mode, error = agent.create_draft(session.id, messages)

    assert draft is not None
    assert mode == "heuristic_fallback"
    assert error is not None


def test_paging_mode_invalid_falls_back_to_heuristic(service):
    service.settings.memoryos_paging_mode = "invalid_mode"
    agent = PagingAgent(service.settings, llm_client=None)
    session = service.create_session("test")
    messages = []
    for content in ["事实 A", "事实 B", "事实 C", "事实 D"]:
        response = service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        messages.append(response.message)

    draft, mode, error = agent.create_draft(session.id, messages)

    assert draft is not None
    assert mode == "heuristic"
    assert error is None


def test_agentic_draft_filters_out_of_window_source_ids(service):
    service.settings.memoryos_paging_mode = "llm"

    class CrossWindowDraftClient:
        def create_draft(self, messages, context_pages=None):
            return MemoryPageDraft(
                title="t",
                summary="s",
                source_message_ids=[messages[0].id, "msg_from_other_window"],
            )

    agent = PagingAgent(service.settings, llm_client=CrossWindowDraftClient())
    session = service.create_session("test")
    messages = []
    for content in ["事实 A", "事实 B", "事实 C", "事实 D"]:
        response = service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        messages.append(response.message)

    draft, mode, error = agent.create_draft(session.id, messages)

    assert draft is not None
    assert mode == "agentic"
    assert all(sid in {m.id for m in messages} for sid in draft.source_message_ids)


def test_page_draft_client_uses_deepseek_provider():
    settings = Settings(memoryos_llm_provider="deepseek", deepseek_api_key="sk-test")
    structured = Mock()
    chat = Mock()
    chat.with_structured_output.return_value = structured

    with patch("memoryos_lite.engine.ChatOpenAI", return_value=chat) as chat_cls:
        client = OpenAIPageDraftClient(settings)

    assert client.model is structured
    kwargs = chat_cls.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-flash"
    assert kwargs["base_url"] == "https://api.deepseek.com"
    assert kwargs["api_key"].get_secret_value() == "sk-test"


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
    assert "lexical" in hits[0].reason and "embedding" in hits[0].reason


def test_item_extractor_heuristic(service):
    session = service.create_session("test")
    page = MemoryPage(
        session_id=session.id,
        title="test",
        summary="s",
        facts=["用户住在上海", "技术栈选 Rust"],
        decisions=["不做 Runbook Agent"],
        source_message_ids=["msg_001"],
    )
    extractor = ItemExtractor(service.settings, llm_client=None)
    items = extractor.extract(page, [])

    assert len(items) == 3
    assert all(isinstance(i, MemoryItem) for i in items)
    assert all(i.page_id == page.id for i in items)
    assert all(i.session_id == session.id for i in items)
    contents = [i.content for i in items]
    assert "用户住在上海" in contents
    assert "不做 Runbook Agent" in contents


def test_page_extracts_items(service):
    session = service.create_session("test")
    for content in [
        "用户住在上海。",
        "技术栈选择 Rust。",
        "不做 Runbook Agent，改做 MemoryOS Lite。",
        "需要 benchmark 对比。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))

    page = service.page(session.id)
    assert page is not None

    items = service.store.list_items(session.id)
    assert len(items) > 0
    assert all(i.page_id == page.id for i in items)
    assert all(i.session_id == session.id for i in items)


def test_store_item_embedding(service):
    session = service.create_session("test")
    item = MemoryItem(
        page_id="page_test",
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="用户偏好 Vim",
        source_message_ids=["msg_001"],
    )
    service.store.save_items([item])
    service.store.set_item_embedding(item.id, [0.1] * 1536)
    embeddings = service.store.get_item_embeddings([item.id])
    assert item.id in embeddings
    assert len(embeddings[item.id]) == 1536


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
