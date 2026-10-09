"""Tests for item-level retrieval (Phase 1 — Item-Level Evidence RAG)."""

from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.item_searcher import ItemSearcher
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import (
    MemoryItem,
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
        memoryos_recall_pipeline="v1",  # legacy ContextBuilder opt-in
        memoryos_paging_mode="heuristic",
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
        memoryos_recall_pipeline="v1",  # legacy ContextBuilder opt-in
        memoryos_paging_mode="heuristic",
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
