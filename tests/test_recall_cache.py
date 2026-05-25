from memoryos_lite.cache import RedisDerivedCache
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import RecallMemorySearcher
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import MemoryItem, MemoryItemType, Message, Role
from memoryos_lite.store import create_store


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.get_calls = 0
        self.set_calls = 0

    def get(self, key: str) -> str | None:
        self.get_calls += 1
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls += 1
        self.values[key] = value
        self.ttls[key] = ex
        return True


class WordTokenizer:
    def count(self, text: str) -> int:
        return len(text.split())


class CountingSearcher:
    def __init__(self) -> None:
        self.calls = 0
        self.inner = RecallMemorySearcher()

    def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.inner.search(*args, **kwargs)


def _settings(tmp_path, *, enabled: bool) -> Settings:
    return Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recall_pipeline="v2",
        memoryos_recall_cache_enabled=enabled,
        memoryos_redis_url="redis://localhost:6379/0",
        memoryos_cache_namespace="memoryos:test",
    )


def _cache() -> RedisDerivedCache:
    return RedisDerivedCache(FakeRedis(), namespace="memoryos:test", default_ttl_s=60)


def _add_message(store, message_id: str, content: str) -> None:  # type: ignore[no-untyped-def]
    store.add_message(
        Message(
            id=message_id,
            session_id="ses",
            role=Role.USER,
            content=content,
            metadata={},
            token_count=len(content.split()),
        )
    )


def test_recall_cache_reuses_package_and_preserves_source_refs(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=True)
    store = create_store(settings)
    store.reset()
    _add_message(store, "msg_bob", "Bob moved to Shanghai.")
    cache = _cache()
    searcher = CountingSearcher()
    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        cache=cache,
    )
    pipeline.recall_searcher = searcher

    first = pipeline.build_context("ses", "Where did Bob move?", budget=200)
    second = pipeline.build_context("ses", "Where did Bob move?", budget=200)

    assert searcher.calls == 1
    assert first.metadata["recall_cache"]["status"] == "miss"
    assert second.metadata["recall_cache"]["status"] == "hit"
    assert second.metadata["episode_backfilled"] == 0
    assert second.retrieved_evidence[0].message_id == "msg_bob"
    assert second.metadata["recall_candidate_message_ids"] == ["msg_bob"]
    assert second.metadata["planned_evidence_message_ids"] == ["msg_bob"]
    source_refs = second.metadata["recall_diagnostics"][0]["source_refs"]
    assert source_refs[0]["source_id"] == "msg_bob"


def test_recall_pipeline_emits_unified_cache_metadata_on_hit(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=True)
    store = create_store(settings)
    store.reset()
    _add_message(store, "msg_bob", "Bob moved to Shanghai.")
    cache = _cache()
    searcher = CountingSearcher()
    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        cache=cache,
    )
    pipeline.recall_searcher = searcher

    pipeline.build_context("ses", "Where did Bob move?", budget=200)
    second = pipeline.build_context("ses", "Where did Bob move?", budget=200)

    assert second.metadata["recall_cache"]["status"] == "hit"
    assert second.metadata["cache"]["status"] == "hit"
    assert second.metadata["cache"]["scope"] == "recall_context_package"
    assert second.metadata["cache"]["key_version"] == "derived-cache-v1"
    assert second.metadata["cache"]["backend"] in {"redis", "noop"}
    assert second.metadata["query_analysis_cache"]["status"] != "hit"
    assert (
        second.metadata["query_analysis_cache"]["fallback_reason"]
        == "recall_context_package_hit"
    )
    assert second.metadata["recall_candidate_cache"]["status"] != "hit"
    assert (
        second.metadata["recall_candidate_cache"]["fallback_reason"]
        == "recall_context_package_hit"
    )


def test_recall_candidate_cache_hits_when_context_budget_changes(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=True)
    store = create_store(settings)
    store.reset()
    _add_message(store, "msg_bob", "Bob moved to Shanghai.")
    cache = _cache()
    searcher = CountingSearcher()
    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        cache=cache,
    )
    pipeline.recall_searcher = searcher

    first = pipeline.build_context("ses", "Where did Bob move?", budget=200)
    second = pipeline.build_context("ses", "Where did Bob move?", budget=120)

    assert searcher.calls == 1
    assert first.metadata["recall_candidate_cache"]["status"] == "miss"
    assert second.metadata["cache"]["status"] == "miss"
    assert second.metadata["recall_candidate_cache"]["status"] == "hit"


def test_recall_cache_watermark_rejects_stale_package_after_session_mutation(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=True)
    store = create_store(settings)
    store.reset()
    _add_message(store, "msg_shanghai", "Bob moved to Shanghai.")
    cache = _cache()
    searcher = CountingSearcher()
    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        cache=cache,
    )
    pipeline.recall_searcher = searcher

    pipeline.build_context("ses", "Where did Bob move?", budget=200)
    _add_message(store, "msg_berlin", "Bob later moved to Berlin.")
    second = pipeline.build_context("ses", "Where did Bob move?", budget=200)

    assert searcher.calls == 2
    assert second.metadata["recall_cache"]["status"] == "miss"
    assert "msg_berlin" in second.metadata["recall_candidate_message_ids"]


def test_query_analysis_cache_hits_when_context_cache_key_changes(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=True)
    store = create_store(settings)
    store.reset()
    _add_message(store, "msg_bob", "Bob moved to Shanghai.")
    cache = _cache()
    searcher = CountingSearcher()
    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        cache=cache,
    )
    pipeline.recall_searcher = searcher

    first = pipeline.build_context("ses", "Where did Bob move?", budget=200)
    second = pipeline.build_context("ses", "Where did Bob move?", budget=120)

    assert searcher.calls == 1
    assert first.metadata["recall_cache"]["status"] == "miss"
    assert second.metadata["recall_cache"]["status"] == "miss"
    assert first.metadata["query_analysis_cache"]["status"] == "miss"
    assert second.metadata["query_analysis_cache"]["status"] == "hit"


def test_recall_cache_disabled_does_not_read_or_write_even_with_cache_client(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=False)
    store = create_store(settings)
    store.reset()
    _add_message(store, "msg_bob", "Bob moved to Shanghai.")
    cache = _cache()
    searcher = CountingSearcher()
    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
        cache=cache,
    )
    pipeline.recall_searcher = searcher

    first = pipeline.build_context("ses", "Where did Bob move?", budget=200)
    second = pipeline.build_context("ses", "Where did Bob move?", budget=200)

    assert searcher.calls == 2
    assert first.metadata["recall_cache"]["status"] == "disabled"
    assert second.metadata["recall_cache"]["status"] == "disabled"
    assert cache.client.get_calls == 0
    assert cache.client.set_calls == 0
    assert cache.client.values == {}


def test_session_watermark_changes_when_item_content_is_updated(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=True)
    store = create_store(settings)
    store.reset()
    store.save_items(
        [
            MemoryItem(
                id="item_profile",
                page_id="page_1",
                session_id="ses",
                item_type=MemoryItemType.PROFILE,
                content="Bob lives in Shanghai.",
                source_message_ids=["msg_bob"],
            )
        ]
    )
    before = store.session_memory_watermark("ses")

    assert store.update_item_content("item_profile", "Bob lives in Berlin.")

    after = store.session_memory_watermark("ses")
    assert after != before
