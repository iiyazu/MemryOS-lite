"""Tests for item-level retrieval (Phase 1 — Item-Level Evidence RAG)."""

from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.item_searcher import ItemSearcher
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import (
    MemoryItem,
    MemoryItemType,
    MessageCreate,
    Role,
)
from memoryos_lite.store import create_store


@pytest.fixture()
def embedding_client():
    return DeterministicEmbeddingClient()


@pytest.fixture()
def item_service(tmp_path: Path) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_item_extraction=True,
        memoryos_memory_arch="v1",
    )
    store = create_store(settings)
    store.reset()
    client = DeterministicEmbeddingClient()
    return MemoryOSService(store=store, settings=settings, embedding_client=client)


@pytest.fixture()
def no_item_service(tmp_path: Path) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_item_extraction=False,
        memoryos_memory_arch="v1",
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


# --- Unit tests for ItemSearcher ---


def test_item_bm25_search_returns_matching_items():
    items = [
        MemoryItem(
            page_id="page_1",
            session_id="s1",
            content="用户喜欢 PostgreSQL 数据库",
            source_message_ids=["msg_1"],
        ),
        MemoryItem(
            page_id="page_1",
            session_id="s1",
            content="项目使用 FastAPI 框架",
            source_message_ids=["msg_2"],
        ),
        MemoryItem(
            page_id="page_1",
            session_id="s1",
            content="部署在 AWS 上",
            source_message_ids=["msg_3"],
        ),
    ]
    searcher = ItemSearcher()
    hits = searcher.search(items, "PostgreSQL", top_k=5)
    assert len(hits) >= 1
    assert hits[0].item.content == "用户喜欢 PostgreSQL 数据库"
    assert hits[0].score > 0


def test_item_bm25_no_match_returns_empty():
    items = [
        MemoryItem(
            page_id="page_1",
            session_id="s1",
            content="项目使用 FastAPI 框架",
            source_message_ids=["msg_1"],
        ),
    ]
    searcher = ItemSearcher()
    hits = searcher.search(items, "Redis", top_k=5)
    assert hits == []


def test_item_embedding_search_with_deterministic_client(embedding_client):
    items = [
        MemoryItem(
            id="item_a",
            page_id="page_1",
            session_id="s1",
            content="用户住在北京",
            source_message_ids=["msg_1"],
        ),
        MemoryItem(
            id="item_b",
            page_id="page_1",
            session_id="s1",
            content="项目截止日期是下周五",
            source_message_ids=["msg_2"],
        ),
    ]
    embeddings = {
        "item_a": embedding_client.embed("用户住在北京"),
        "item_b": embedding_client.embed("项目截止日期是下周五"),
    }
    searcher = ItemSearcher(embedding_client=embedding_client)
    hits = searcher.search(items, "用户住在北京", embeddings=embeddings, top_k=5)
    assert len(hits) >= 1
    assert hits[0].item.id == "item_a"
    assert hits[0].score > 0


def test_item_rrf_fusion_combines_bm25_and_embedding(embedding_client):
    items = [
        MemoryItem(
            id="item_a",
            page_id="page_1",
            session_id="s1",
            content="用户住在北京朝阳区",
            source_message_ids=["msg_1"],
        ),
        MemoryItem(
            id="item_b",
            page_id="page_1",
            session_id="s1",
            content="项目截止日期是下周五",
            source_message_ids=["msg_2"],
        ),
        MemoryItem(
            id="item_c",
            page_id="page_1",
            session_id="s1",
            content="另一个无关的条目关于天气",
            source_message_ids=["msg_3"],
        ),
    ]
    embeddings = {
        "item_a": embedding_client.embed("用户住在北京朝阳区"),
        "item_b": embedding_client.embed("项目截止日期是下周五"),
        "item_c": embedding_client.embed("另一个无关的条目关于天气"),
    }
    searcher = ItemSearcher(embedding_client=embedding_client)
    hits = searcher.search(items, "北京朝阳", embeddings=embeddings, top_k=5)
    assert len(hits) >= 1
    assert hits[0].item.id == "item_a"


# --- Integration tests: item retrieval in build_context ---


def test_item_hit_promotes_evidence_when_page_summary_misses(item_service):
    """Item retrieval recovers evidence that page-level search would miss.

    Scenario: page summary does NOT contain 'Kubernetes', but an item does.
    The target message is outside the recent window so it can only be
    recovered via item evidence.
    """
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "我们用 FastAPI 做后端"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "部署用 Kubernetes 集群"),
        (Role.USER, "数据库选 PostgreSQL"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # Add more messages so k8s_msg falls outside recent_message_limit=2
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="继续讨论其他话题"))
    svc.ingest(session.id, MessageCreate(role=Role.ASSISTANT, content="好的，请说"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="前端用 React"))
    # Manually create an item that has 'Kubernetes' but page summary may not
    all_msgs = svc.store.list_messages(session.id)
    k8s_msg = all_msgs[2]
    assert "Kubernetes" in k8s_msg.content
    item = MemoryItem(
        page_id=page.id,
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="部署环境使用 Kubernetes 集群",
        source_message_ids=[k8s_msg.id],
    )
    svc.store.save_items([item])
    svc._index_item_embedding(item)
    # Query for Kubernetes — item should promote evidence
    pkg = svc.build_context(session.id, "Kubernetes 部署方案", budget=2000)
    evidence_ids = {e.message_id for e in pkg.retrieved_evidence}
    assert k8s_msg.id in evidence_ids


def test_extraction_disabled_skips_item_retrieval(no_item_service):
    """When memoryos_item_extraction=False, no item search runs."""
    svc = no_item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "我们用 Redis 做缓存"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "Redis 版本是 7.0"),
        (Role.USER, "集群模式部署"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    svc.page(session.id)
    # Even if items existed, they shouldn't be searched
    svc.build_context(session.id, "Redis 配置", budget=2000)
    # No item_retrieval trace should be emitted
    traces = svc.store.list_traces(session.id)
    item_traces = [t for t in traces if t.event_type == "item_retrieval"]
    assert item_traces == []


def test_superseded_parent_page_items_excluded(item_service):
    """Items under a superseded page are not searched by item retrieval."""
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "我住在上海"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "工作是后端开发"),
        (Role.USER, "用 Python 写代码"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # Create item under this page
    msg = svc.store.list_messages(session.id)[0]
    item = MemoryItem(
        page_id=page.id,
        session_id=session.id,
        item_type=MemoryItemType.PROFILE,
        content="用户住在上海",
        source_message_ids=[msg.id],
    )
    svc.store.save_items([item])
    svc._index_item_embedding(item)
    # Mark page as superseded
    svc.store.mark_page_superseded(page.id, "page_newer")
    # Query — item retrieval should find 0 hits (parent superseded)
    svc.build_context(session.id, "用户住在哪里", budget=2000)
    traces = svc.store.list_traces(session.id)
    item_traces = [t for t in traces if t.event_type == "item_retrieval"]
    # No item_retrieval trace emitted because active_items is empty
    assert item_traces == []


def test_deduplication_same_source_from_page_and_item(item_service):
    """Same source_message_id from page evidence and item evidence appears once."""
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "数据库选 PostgreSQL"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "ORM 用 SQLAlchemy"),
        (Role.USER, "部署在 AWS RDS"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # The page's source_message_ids should include the PostgreSQL message
    pg_msg = svc.store.list_messages(session.id)[0]
    # Create an item that also references the same message
    item = MemoryItem(
        page_id=page.id,
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="数据库选型为 PostgreSQL",
        source_message_ids=[pg_msg.id],
    )
    svc.store.save_items([item])
    svc._index_item_embedding(item)
    pkg = svc.build_context(session.id, "PostgreSQL 数据库", budget=2000)
    # Count how many times pg_msg.id appears in evidence
    evidence_msg_ids = [e.message_id for e in pkg.retrieved_evidence]
    assert evidence_msg_ids.count(pg_msg.id) <= 1


def test_item_retrieval_trace_event_emitted(item_service):
    """When items are searched, an item_retrieval trace event is emitted."""
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "我喜欢用 Vim 编辑器"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "配置了很多插件"),
        (Role.USER, "主要写 Go 代码"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    vim_msg = svc.store.list_messages(session.id)[0]
    item = MemoryItem(
        page_id=page.id,
        session_id=session.id,
        item_type=MemoryItemType.BEHAVIOR,
        content="用户使用 Vim 编辑器",
        source_message_ids=[vim_msg.id],
    )
    svc.store.save_items([item])
    svc._index_item_embedding(item)
    svc.build_context(session.id, "Vim 编辑器", budget=2000)
    traces = svc.store.list_traces(session.id)
    item_traces = [t for t in traces if t.event_type == "item_retrieval"]
    assert len(item_traces) == 1
    payload = item_traces[0].payload
    assert "item_hit_count" in payload
    assert "promoted_evidence_count" in payload
    assert "promoted_source_message_ids" in payload


def test_heuristic_items_narrow_source_ids(item_service):
    """Heuristic item extraction narrows source_message_ids per item,
    so only the relevant source message is promoted — not all page sources."""
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "我们用 Kubernetes 部署服务"),
        (Role.USER, "数据库选 PostgreSQL"),
        (Role.USER, "前端用 React 框架"),
        (Role.USER, "后端用 FastAPI"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # Check that heuristic items have narrowed source IDs
    items = svc.store.list_items(session.id)
    assert len(items) > 0
    # ALL items should have narrowed source IDs (≤3), not the full page set
    for item in items:
        assert len(item.source_message_ids) <= 3
        assert len(item.source_message_ids) < len(page.source_message_ids)


def test_without_items_target_source_not_in_evidence(tmp_path):
    """A/B test: without item retrieval, a message whose content uses an
    abbreviation is NOT found by page-level BM25 for the full-term query.
    With a precise item (full term), it IS recovered."""
    # --- A: without items ---
    settings_no_items = Settings(
        data_dir=tmp_path / ".memoryos_a",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_item_extraction=False,
        memoryos_memory_arch="v1",
    )
    store_a = create_store(settings_no_items)
    store_a.reset()
    svc_a = MemoryOSService(store=store_a, settings=settings_no_items)
    session_a = svc_a.create_session("test")
    # Raw message uses abbreviation "K8s", not "Kubernetes"
    msgs = [
        (Role.USER, "容器编排用 K8s 集群"),
        (Role.USER, "数据库选 PostgreSQL"),
        (Role.USER, "前端用 React 框架"),
        (Role.USER, "后端用 FastAPI"),
    ]
    for role, content in msgs:
        svc_a.ingest(session_a.id, MessageCreate(role=role, content=content))
    svc_a.page(session_a.id)
    # Push target out of recent window
    svc_a.ingest(session_a.id, MessageCreate(role=Role.USER, content="讨论测试策略"))
    svc_a.ingest(session_a.id, MessageCreate(role=Role.USER, content="CI 用 GitHub Actions"))
    svc_a.ingest(session_a.id, MessageCreate(role=Role.USER, content="监控用 Prometheus"))
    all_msgs_a = svc_a.store.list_messages(session_a.id)
    k8s_msg_a = all_msgs_a[0]
    assert "K8s" in k8s_msg_a.content
    # Query uses full term "Kubernetes" — page-level BM25 won't match "K8s"
    pkg_a = svc_a.build_context(session_a.id, "Kubernetes 部署方案", budget=2000)
    assert k8s_msg_a.id not in {e.message_id for e in pkg_a.retrieved_evidence}
    # No item_retrieval trace
    traces_a = svc_a.store.list_traces(session_a.id)
    assert not [t for t in traces_a if t.event_type == "item_retrieval"]

    # --- B: with items (item uses full term "Kubernetes") ---
    settings_items = Settings(
        data_dir=tmp_path / ".memoryos_b",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_item_extraction=True,
        memoryos_memory_arch="v1",
    )
    store_b = create_store(settings_items)
    store_b.reset()
    client = DeterministicEmbeddingClient()
    svc_b = MemoryOSService(store=store_b, settings=settings_items, embedding_client=client)
    session_b = svc_b.create_session("test")
    for role, content in msgs:
        svc_b.ingest(session_b.id, MessageCreate(role=role, content=content))
    svc_b.page(session_b.id)
    svc_b.ingest(session_b.id, MessageCreate(role=Role.USER, content="讨论测试策略"))
    svc_b.ingest(session_b.id, MessageCreate(role=Role.USER, content="CI 用 GitHub Actions"))
    svc_b.ingest(session_b.id, MessageCreate(role=Role.USER, content="监控用 Prometheus"))
    all_msgs_b = svc_b.store.list_messages(session_b.id)
    k8s_msg_b = all_msgs_b[0]
    # Add a precise item with full term "Kubernetes" pointing to the K8s message
    page_b = svc_b.store.list_pages(session_b.id, include_superseded=False)[0]
    item = MemoryItem(
        page_id=page_b.id,
        session_id=session_b.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="部署环境使用 Kubernetes 集群",
        source_message_ids=[k8s_msg_b.id],
    )
    svc_b.store.save_items([item])
    svc_b._index_item_embedding(item)
    pkg_b = svc_b.build_context(session_b.id, "Kubernetes 部署方案", budget=2000)
    evidence_ids_b = {e.message_id for e in pkg_b.retrieved_evidence}
    # With item, target IS in evidence
    assert k8s_msg_b.id in evidence_ids_b


def test_item_evidence_filters_generic_ack(item_service):
    """Generic ack messages are not promoted as item evidence."""
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "数据库选 PostgreSQL"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "ORM 用 SQLAlchemy"),
        (Role.USER, "部署在 AWS"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    all_msgs = svc.store.list_messages(session.id)
    ack_msg = all_msgs[1]
    assert "好的" in ack_msg.content
    # Create item that references the ack message
    item = MemoryItem(
        page_id=page.id,
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="数据库选型为 PostgreSQL",
        source_message_ids=[ack_msg.id],
    )
    svc.store.save_items([item])
    svc._index_item_embedding(item)
    # Push messages out of recent window
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="继续"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="下一步"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="其他话题"))
    pkg = svc.build_context(session.id, "PostgreSQL 数据库", budget=2000)
    # The ack message should NOT be in evidence
    evidence_ids = {e.message_id for e in pkg.retrieved_evidence}
    assert ack_msg.id not in evidence_ids


def test_item_evidence_dedup_with_recent_messages(item_service):
    """Messages already in recent_messages are not duplicated as evidence."""
    svc = item_service
    session = svc.create_session("test")
    msgs = [
        (Role.USER, "我们用 Redis 做缓存"),
        (Role.ASSISTANT, "好的"),
        (Role.USER, "Redis 版本是 7.0"),
        (Role.USER, "集群模式部署 Redis"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # The last message is in recent window (limit=2)
    all_msgs = svc.store.list_messages(session.id)
    recent_msg = all_msgs[-1]
    # Create item referencing the recent message
    item = MemoryItem(
        page_id=page.id,
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="Redis 集群模式部署",
        source_message_ids=[recent_msg.id],
    )
    svc.store.save_items([item])
    svc._index_item_embedding(item)
    pkg = svc.build_context(session.id, "Redis 集群", budget=2000)
    # recent_msg should be in recent_messages, NOT duplicated in evidence
    recent_ids = {m.id for m in pkg.recent_messages}
    evidence_ids = {e.message_id for e in pkg.retrieved_evidence}
    if recent_msg.id in recent_ids:
        assert recent_msg.id not in evidence_ids
