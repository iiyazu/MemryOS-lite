import json

import memoryos_lite.cache as cache_module
from memoryos_lite.cache import (
    NoopMemoryCache,
    RedisMemoryCache,
    build_cache_key,
    create_memory_cache,
)
from memoryos_lite.config import Settings


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        self.ttls[key] = ex
        return True


class FailingRedis:
    def get(self, key: str) -> str | None:
        raise TimeoutError("redis timed out")

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        raise TimeoutError("redis timed out")


def test_cache_factory_returns_noop_when_redis_url_is_unset() -> None:
    cache = create_memory_cache(Settings(memoryos_redis_url=None))

    assert isinstance(cache, NoopMemoryCache)
    assert cache.get_json("any").status == "disabled"
    assert cache.set_json("any", {"value": 1}).status == "disabled"


def test_cache_factory_uses_injected_redis_client_when_enabled() -> None:
    client = FakeRedis()
    settings = Settings(memoryos_redis_url="redis://localhost:6379/0")

    cache = create_memory_cache(settings, redis_client=client)

    assert isinstance(cache, RedisMemoryCache)


def test_redis_cache_round_trips_json_with_schema_envelope_and_ttl() -> None:
    client = FakeRedis()
    cache = RedisMemoryCache(
        client,
        namespace="memoryos:test",
        default_ttl_s=60,
    )

    write = cache.set_json("query:abc", {"message_ids": ["msg_1"], "source_refs": ["msg_1"]})
    read = cache.get_json("query:abc")

    assert write.status == "stored"
    assert read.status == "hit"
    assert read.value == {"message_ids": ["msg_1"], "source_refs": ["msg_1"]}
    assert client.ttls["memoryos:test:query:abc"] == 60


def test_redis_cache_treats_corrupt_values_as_misses() -> None:
    client = FakeRedis()
    client.values["memoryos:test:bad"] = "not json"
    cache = RedisMemoryCache(client, namespace="memoryos:test", default_ttl_s=60)

    read = cache.get_json("bad")

    assert read.status == "corrupt"
    assert read.value is None


def test_redis_cache_treats_schema_mismatch_as_stale() -> None:
    client = FakeRedis()
    client.values["memoryos:test:old"] = json.dumps(
        {"schema_version": 0, "value": {"message_ids": ["msg_1"]}}
    )
    cache = RedisMemoryCache(client, namespace="memoryos:test", default_ttl_s=60)

    read = cache.get_json("old")

    assert read.status == "stale"
    assert read.value is None


def test_redis_cache_degrades_to_error_status_on_client_failure() -> None:
    cache = RedisMemoryCache(FailingRedis(), namespace="memoryos:test", default_ttl_s=60)

    read = cache.get_json("query:abc")
    write = cache.set_json("query:abc", {"value": 1})

    assert read.status == "error"
    assert read.value is None
    assert "timed out" in (read.reason or "")
    assert write.status == "error"
    assert "timed out" in (write.reason or "")


def test_cache_factory_returns_noop_when_redis_dependency_is_missing(monkeypatch) -> None:
    def missing_import(name: str):
        raise ImportError(name)

    monkeypatch.setattr(cache_module, "import_module", missing_import)

    cache = create_memory_cache(Settings(memoryos_redis_url="redis://localhost:6379/0"))

    assert isinstance(cache, NoopMemoryCache)


def test_cache_key_binds_scope_query_settings_session_and_watermark() -> None:
    settings = Settings(
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
        memoryos_evidence_context_neighbors_before=2,
        memoryos_evidence_context_neighbors_after=1,
        memoryos_evidence_candidate_top_k=5,
    )

    key = build_cache_key(
        scope="recall_candidates",
        settings=settings,
        session_id="session_a",
        query="Where did Bob move?",
        memory_watermark="messages:1|episodes:1",
        parameters={"budget": 200},
    )
    same_key = build_cache_key(
        scope="recall_candidates",
        settings=settings,
        session_id="session_a",
        query="  Where did Bob   move? ",
        memory_watermark="messages:1|episodes:1",
        parameters={"budget": 200},
    )
    changed_watermark_key = build_cache_key(
        scope="recall_candidates",
        settings=settings,
        session_id="session_a",
        query="Where did Bob move?",
        memory_watermark="messages:2|episodes:2",
        parameters={"budget": 200},
    )
    changed_settings_key = build_cache_key(
        scope="recall_candidates",
        settings=settings.model_copy(update={"memoryos_recall_pipeline": "v1"}),
        session_id="session_a",
        query="Where did Bob move?",
        memory_watermark="messages:1|episodes:1",
        parameters={"budget": 200},
    )

    assert key == same_key
    assert key.startswith("recall_candidates:")
    assert "Where did Bob move" not in key
    assert key != changed_watermark_key
    assert key != changed_settings_key


def test_query_analysis_cache_key_is_global_and_uses_query_hash() -> None:
    settings = Settings(memoryos_memory_arch="v3", memoryos_recall_pipeline="v1")

    key = build_cache_key(
        scope="query_analysis",
        settings=settings,
        query="Find Alice's private detail",
    )

    assert key.startswith("query_analysis:")
    assert "Alice" not in key
    assert "session" not in key
