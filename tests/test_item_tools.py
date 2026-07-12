"""Tests for Phase 2: Letta-style active memory item tools."""

from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import MemoryItemType
from memoryos_lite.store import create_store
from memoryos_lite.tools import create_item_tools


@pytest.fixture()
def svc(tmp_path: Path) -> MemoryOSService:
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
def disabled_svc(tmp_path: Path) -> MemoryOSService:
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


# --- Service-layer tests ---


def test_create_item_stores_and_embeds(svc):
    session = svc.create_session("test")
    item = svc.create_item(session.id, "用户喜欢 Python", "profile")
    assert item is not None
    assert item.content == "用户喜欢 Python"
    assert item.item_type == MemoryItemType.PROFILE
    assert item.session_id == session.id
    embeddings = svc.store.get_item_embeddings([item.id])
    assert item.id in embeddings


def test_create_item_invalid_type_raises(svc):
    session = svc.create_session("test")
    with pytest.raises(ValueError, match="invalid item_type"):
        svc.create_item(session.id, "test", "invalid_type")


def test_search_items_returns_hits(svc):
    session = svc.create_session("test")
    svc.create_item(session.id, "用户喜欢 PostgreSQL 数据库", "knowledge")
    svc.create_item(session.id, "项目用 FastAPI 框架", "knowledge")
    hits = svc.search_items(session.id, "PostgreSQL", top_k=5)
    assert len(hits) >= 1
    assert any("PostgreSQL" in h["content"] for h in hits)


def test_patch_item_updates_and_reembeds(svc):
    session = svc.create_session("test")
    item = svc.create_item(session.id, "用户住在北京", "profile")
    assert item is not None
    result = svc.patch_item(session.id, item.id, "用户住在上海")
    assert "updated" in result
    updated = svc.store.load_item(item.id)
    assert updated is not None
    assert updated.content == "用户住在上海"
    embeddings = svc.store.get_item_embeddings([item.id])
    assert item.id in embeddings


def test_patch_item_session_boundary(svc):
    session_a = svc.create_session("a")
    session_b = svc.create_session("b")
    item = svc.create_item(session_a.id, "test content", "knowledge")
    assert item is not None
    result = svc.patch_item(session_b.id, item.id, "hacked")
    assert "different session" in result


def test_patch_item_not_found(svc):
    session = svc.create_session("test")
    result = svc.patch_item(session.id, "item_nonexistent", "new")
    assert "not found" in result


# --- Disabled mode tests ---


def test_create_item_disabled_returns_none(disabled_svc):
    session = disabled_svc.create_session("test")
    result = disabled_svc.create_item(session.id, "test", "knowledge")
    assert result is None


def test_search_items_disabled_returns_empty(disabled_svc):
    session = disabled_svc.create_session("test")
    result = disabled_svc.search_items(session.id, "test")
    assert result == []


def test_patch_item_disabled_returns_message(disabled_svc):
    session = disabled_svc.create_session("test")
    result = disabled_svc.patch_item(session.id, "item_x", "new")
    assert "disabled" in result.lower()


# --- Tool-level tests ---


def test_memorize_item_tool_happy_path(svc):
    session = svc.create_session("test")
    tools = create_item_tools(svc, session.id)
    memorize = tools[0]
    result = memorize.invoke({"content": "用户喜欢 Vim", "item_type": "behavior"})
    assert "Memorized" in result
    assert "behavior" in result


def test_recall_items_tool_happy_path(svc):
    session = svc.create_session("test")
    svc.create_item(session.id, "用户喜欢 PostgreSQL", "knowledge")
    svc.create_item(session.id, "项目用 React 前端", "knowledge")
    svc.create_item(session.id, "部署在 AWS 云上", "knowledge")
    tools = create_item_tools(svc, session.id)
    recall = tools[1]
    result = recall.invoke({"query": "PostgreSQL", "top_k": 5})
    assert "PostgreSQL" in result


def test_patch_item_tool_happy_path(svc):
    session = svc.create_session("test")
    item = svc.create_item(session.id, "用户住在北京", "profile")
    assert item is not None
    tools = create_item_tools(svc, session.id)
    patch = tools[2]
    result = patch.invoke({"item_id": item.id, "new_content": "用户住在上海"})
    assert "updated" in result.lower()


def test_memorize_item_tool_invalid_type(svc):
    session = svc.create_session("test")
    tools = create_item_tools(svc, session.id)
    memorize = tools[0]
    result = memorize.invoke({"content": "test", "item_type": "invalid"})
    assert "invalid" in result.lower()


def test_memorize_item_tool_disabled(disabled_svc):
    session = disabled_svc.create_session("test")
    tools = create_item_tools(disabled_svc, session.id)
    memorize = tools[0]
    result = memorize.invoke({"content": "test", "item_type": "knowledge"})
    assert "disabled" in result.lower()


def test_item_tool_names_available(svc):
    """Item tools are available via create_item_tools()."""
    from memoryos_lite.tools import create_memory_tools

    session = svc.create_session("test")
    page_tools = create_memory_tools(svc, session.id)
    item_tools = create_item_tools(svc, session.id)
    all_names = {t.name for t in page_tools + item_tools}
    assert "memorize_item" in all_names
    assert "recall_items" in all_names
    assert "patch_item" in all_names


# --- Dual-trigger integration tests ---


def test_orphan_item_recovered_by_build_context(svc):
    """Tool-created orphan items (no real page) are recovered by build_context()."""
    session = svc.create_session("test")
    from memoryos_lite.schemas import MessageCreate, Role

    svc.ingest(session.id, MessageCreate(role=Role.USER, content="我喜欢用 Neovim 编辑器"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="配置了很多插件"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="主要写 Rust 代码"))
    # The latest message is what create_item will bind to as source
    source_msg = svc.store.list_messages(session.id, limit=1)[0]
    # Create multiple orphan items so BM25 has a proper corpus
    item = svc.create_item(session.id, "用户使用 Neovim 编辑器", "behavior")
    svc.create_item(session.id, "用户写 Rust 代码", "knowledge")
    svc.create_item(session.id, "配置了很多 Neovim 插件", "behavior")
    assert item is not None
    assert item.page_id.startswith("orphan_")
    assert source_msg.id in item.source_message_ids
    # Push messages out of recent window (limit=2)
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="其他话题"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="继续讨论"))
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="下一步"))
    # build_context should find the orphan item and promote its source to evidence
    pkg = svc.build_context(session.id, "Neovim 编辑器", budget=2000)
    evidence_ids = {e.message_id for e in pkg.retrieved_evidence}
    assert source_msg.id in evidence_ids
    # Also verify trace
    traces = svc.store.list_traces(session.id)
    item_traces = [t for t in traces if t.event_type == "item_retrieval"]
    assert len(item_traces) == 1
    assert item_traces[0].payload["item_hit_count"] >= 1


def test_search_items_excludes_superseded_by_default(svc):
    """search_items() excludes items under superseded pages by default."""
    from memoryos_lite.schemas import MessageCreate, Role

    session = svc.create_session("test")
    msgs = [
        (Role.USER, "数据库选 MySQL"),
        (Role.USER, "ORM 用 SQLAlchemy"),
        (Role.USER, "部署在 AWS"),
        (Role.USER, "后端用 Django"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # Create item under this page
    item = svc.create_item(session.id, "数据库选型为 MySQL", "knowledge")
    assert item is not None
    # Mark page as superseded
    svc.store.mark_page_superseded(page.id, "page_newer")
    # Default search should NOT find the item
    hits = svc.search_items(session.id, "MySQL", top_k=5)
    item_ids = [h["item_id"] for h in hits]
    assert item.id not in item_ids


def test_search_items_includes_superseded_when_requested(svc):
    """search_items(include_superseded=True) returns items under superseded pages."""
    from memoryos_lite.schemas import MessageCreate, Role

    session = svc.create_session("test")
    msgs = [
        (Role.USER, "数据库选 MySQL"),
        (Role.USER, "ORM 用 SQLAlchemy"),
        (Role.USER, "部署在 AWS"),
        (Role.USER, "后端用 Django"),
    ]
    for role, content in msgs:
        svc.ingest(session.id, MessageCreate(role=role, content=content))
    page = svc.page(session.id)
    assert page is not None
    # Create multiple items so BM25 has a proper corpus
    item = svc.create_item(session.id, "数据库选型为 MySQL 关系型数据库", "knowledge")
    svc.create_item(session.id, "ORM 框架选择 SQLAlchemy", "knowledge")
    svc.create_item(session.id, "云服务商选择 AWS", "knowledge")
    assert item is not None
    svc.store.mark_page_superseded(page.id, "page_newer")
    # With include_superseded=True, item should be found
    hits = svc.search_items(session.id, "MySQL", top_k=5, include_superseded=True)
    item_ids = [h["item_id"] for h in hits]
    assert item.id in item_ids


def test_create_item_default_source_attribution(svc):
    """create_item() binds to latest user message when no source_message_ids given."""
    from memoryos_lite.schemas import MessageCreate, Role

    session = svc.create_session("test")
    svc.ingest(session.id, MessageCreate(role=Role.USER, content="我住在北京"))
    item = svc.create_item(session.id, "用户住在北京", "profile")
    assert item is not None
    assert len(item.source_message_ids) == 1
    latest_msg = svc.store.list_messages(session.id, limit=1)[0]
    assert item.source_message_ids[0] == latest_msg.id
