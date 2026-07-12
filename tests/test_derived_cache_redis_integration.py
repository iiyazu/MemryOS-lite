from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from memoryos_lite.cache.derived import CacheStatus, RedisDerivedCache
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import RecallMemorySearcher
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message, Role
from memoryos_lite.store import create_store

redis = pytest.importorskip("redis")


def _delete_namespace(client: Any, namespace: str) -> None:
    keys = list(client.scan_iter(f"{namespace}:*"))
    if keys:
        client.delete(*keys)


class WordTokenizer:
    def count(self, text: str) -> int:
        return len(text.split())


class CountingSearcher:
    def __init__(self) -> None:
        self.calls = 0
        self.inner = RecallMemorySearcher()

    def search(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return self.inner.search(*args, **kwargs)


def test_real_redis_recall_context_cache_miss_then_hit(tmp_path: Path) -> None:
    url = os.environ.get("MEMORYOS_TEST_REDIS_URL")
    if not url:
        pytest.skip("MEMORYOS_TEST_REDIS_URL is not set")

    namespace = f"memoryos:integration:{uuid4().hex}"
    client = redis.Redis.from_url(url, decode_responses=True)
    assert client.ping() is True

    _delete_namespace(client, namespace)
    try:
        settings = Settings(
            data_dir=tmp_path / ".memoryos",
            memoryos_recall_pipeline="v2",
            memoryos_recall_cache_enabled=True,
            memoryos_redis_url=url,
            memoryos_cache_namespace=namespace,
        )
        cache = RedisDerivedCache(client, namespace=namespace, default_ttl_s=60)
        store = create_store(settings)
        store.reset()
        store.add_message(
            Message(
                id="msg_bob",
                session_id="ses",
                role=Role.USER,
                content="Bob moved to Shanghai.",
                metadata={},
                token_count=4,
            )
        )
        searcher = CountingSearcher()
        pipeline = RecallPipeline(
            store=store, settings=settings, tokenizer=WordTokenizer(), cache=cache
        )
        pipeline.recall_searcher = searcher

        first = pipeline.build_context("ses", "Where did Bob move?", budget=200)
        second = pipeline.build_context("ses", "Where did Bob move?", budget=200)

        assert first.metadata["cache"]["status"] == CacheStatus.MISS.value
        assert second.metadata["cache"]["status"] == CacheStatus.HIT.value
        assert searcher.calls == 1
        assert second.retrieved_evidence[0].message_id == "msg_bob"
    finally:
        _delete_namespace(client, namespace)
