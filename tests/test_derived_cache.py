from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import get_type_hints

import pytest

from memoryos_lite.cache import (
    CacheEntry as ExportedCacheEntry,
)
from memoryos_lite.cache import (
    CacheKeyBuilder as ExportedCacheKeyBuilder,
)
from memoryos_lite.cache import (
    CacheScope as ExportedCacheScope,
)
from memoryos_lite.cache import (
    CacheStatus as ExportedCacheStatus,
)
from memoryos_lite.cache import (
    DerivedCache as ExportedDerivedCache,
)
from memoryos_lite.cache.derived import (
    CACHE_ENTRY_VERSION,
    CACHE_SCHEMA_VERSION,
    CacheEntry,
    CacheFingerprint,
    CacheKeyBuilder,
    CachePayloadType,
    CacheScope,
    CacheStatus,
    DerivedCache,
    NoopDerivedCache,
    RedisDerivedCache,
    create_derived_cache,
)
from memoryos_lite.config import Settings


def test_cache_key_builder_hashes_query_and_parameters_without_plaintext() -> None:
    settings = Settings(
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
        memoryos_evidence_context_neighbors_before=2,
        memoryos_evidence_context_neighbors_after=1,
        memoryos_evidence_candidate_top_k=7,
    )
    builder = CacheKeyBuilder(namespace="memoryos:test")

    fingerprint = builder.build_fingerprint(
        scope=CacheScope.RECALL_CONTEXT_PACKAGE,
        settings=settings,
        query="Where did Bob move?",
        session_id="ses_1",
        watermark="messages:1:2026-05-25T00:00:00",
        parameters={"budget": 200, "limit": 10},
    )
    key = builder.build_key(
        scope=CacheScope.RECALL_CONTEXT_PACKAGE,
        settings=settings,
        query="Where did Bob move?",
        session_id="ses_1",
        watermark="messages:1:2026-05-25T00:00:00",
        parameters={"budget": 200, "limit": 10},
    )
    changed = builder.build_key(
        scope=CacheScope.RECALL_CONTEXT_PACKAGE,
        settings=settings,
        query="Where did Bob move?",
        session_id="ses_1",
        watermark="messages:2:2026-05-25T00:00:01",
        parameters={"budget": 200, "limit": 10},
    )

    assert (
        key == "memoryos:test:"
        f"{CACHE_ENTRY_VERSION}:recall_context_package:{fingerprint.fingerprint_hash}"
    )
    assert "Where did Bob move" not in key
    assert "ses_1" not in key
    assert key != changed


def test_cache_fingerprint_changes_with_scope_parameters() -> None:
    settings = Settings(memoryos_memory_arch="v3", memoryos_recall_pipeline="v2")
    builder = CacheKeyBuilder(namespace="memoryos:test")

    first = builder.build_fingerprint(
        scope=CacheScope.RECALL_CANDIDATES,
        settings=settings,
        query="Find Alice",
        session_id="ses",
        watermark="wm",
        parameters={"budget": 200, "limit": 10},
    )
    second = builder.build_fingerprint(
        scope=CacheScope.RECALL_CANDIDATES,
        settings=settings,
        query="Find Alice",
        session_id="ses",
        watermark="wm",
        parameters={"budget": 120, "limit": 10},
    )

    assert first.fingerprint_hash != second.fingerprint_hash
    assert first.parameters_hash != second.parameters_hash


def test_cache_entry_round_trip_contains_authority_and_payload_type() -> None:
    fingerprint = CacheFingerprint(
        scope=CacheScope.QUERY_ANALYSIS,
        settings_hash="settings",
        watermark_hash="watermark",
        query_hash="query",
        parameters_hash="parameters",
        fingerprint_hash="fingerprint",
        memory_arch="v3",
        recall_pipeline="v2",
        session_hash=None,
    )
    entry = CacheEntry(
        scope=CacheScope.QUERY_ANALYSIS,
        payload_type=CachePayloadType.QUERY_ANALYSIS,
        fingerprint=fingerprint,
        payload={"kind": "temporal"},
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
        ttl_s=3600,
    )

    dumped = entry.model_dump(mode="json")
    restored = CacheEntry.model_validate(dumped)

    assert restored.schema_version == CACHE_SCHEMA_VERSION
    assert restored.entry_version == CACHE_ENTRY_VERSION
    assert restored.authority["store"] == "sqlite"
    assert restored.authority["store_revision"] == "watermark"
    assert restored.authority["source"] == "derived"
    assert restored.payload == {"kind": "temporal"}


def test_cache_entry_authority_uses_none_revision_without_watermark() -> None:
    fingerprint = CacheFingerprint(
        scope=CacheScope.QUERY_ANALYSIS,
        settings_hash="settings",
        watermark_hash=None,
        query_hash="query",
        parameters_hash="parameters",
        fingerprint_hash="fingerprint",
        memory_arch="v3",
        recall_pipeline="v2",
        session_hash=None,
    )
    entry = CacheEntry(
        scope=CacheScope.QUERY_ANALYSIS,
        payload_type=CachePayloadType.QUERY_ANALYSIS,
        fingerprint=fingerprint,
        payload={},
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
    )

    assert entry.authority == {
        "store": "sqlite",
        "store_revision": "none",
        "source": "derived",
    }


def test_cache_status_values_match_contract() -> None:
    assert {status.value for status in CacheStatus} == {
        "hit",
        "miss",
        "stale",
        "corrupt",
        "invalid",
        "error",
        "disabled",
        "stored",
    }


def test_derived_cache_protocol_matches_backend_contract() -> None:
    assert get_type_hints(DerivedCache)["backend_name"] is str
    assert hasattr(DerivedCache, "get")
    assert hasattr(DerivedCache, "set")
    assert hasattr(DerivedCache, "delete")
    assert hasattr(DerivedCache, "status")
    assert not hasattr(DerivedCache, "read")
    assert not hasattr(DerivedCache, "write")


def test_cache_key_builder_rejects_empty_namespace_after_trimming() -> None:
    for namespace in (":::", "   "):
        with pytest.raises(ValueError, match="namespace"):
            CacheKeyBuilder(namespace=namespace)


def test_cache_key_builder_distinguishes_none_and_empty_watermark() -> None:
    settings = Settings(memoryos_memory_arch="v3", memoryos_recall_pipeline="v2")
    builder = CacheKeyBuilder(namespace="memoryos:test")

    none_watermark = builder.build_fingerprint(
        scope=CacheScope.QUERY_ANALYSIS,
        settings=settings,
        query="Find Alice",
        watermark=None,
    )
    empty_watermark = builder.build_fingerprint(
        scope=CacheScope.QUERY_ANALYSIS,
        settings=settings,
        query="Find Alice",
        watermark="",
    )

    assert none_watermark.watermark_hash is None
    assert empty_watermark.watermark_hash is not None
    assert none_watermark.fingerprint_hash != empty_watermark.fingerprint_hash


def test_serialized_cache_entry_does_not_leak_session_id_or_query_plaintext() -> None:
    settings = Settings(memoryos_memory_arch="v3", memoryos_recall_pipeline="v2")
    builder = CacheKeyBuilder(namespace="memoryos:test")
    fingerprint = builder.build_fingerprint(
        scope=CacheScope.RECALL_CONTEXT_PACKAGE,
        settings=settings,
        query="Where did Bob move?",
        session_id="ses_1",
        watermark="wm",
        parameters={"budget": 200},
    )
    entry = CacheEntry(
        scope=CacheScope.RECALL_CONTEXT_PACKAGE,
        payload_type=CachePayloadType.CONTEXT_PACKAGE,
        fingerprint=fingerprint,
        payload={"answer_kind": "context"},
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
    )

    dumped = entry.model_dump(mode="json")
    raw_json = entry.model_dump_json()
    assert "session_id" not in dumped["fingerprint"]
    assert "session_hash" in dumped["fingerprint"]
    assert "ses_1" not in raw_json
    assert "Where did Bob move" not in raw_json


def test_public_cache_exports_include_derived_contract_types() -> None:
    assert ExportedCacheEntry is CacheEntry
    assert ExportedCacheKeyBuilder is CacheKeyBuilder
    assert ExportedCacheScope is CacheScope
    assert ExportedCacheStatus is CacheStatus
    assert ExportedDerivedCache is DerivedCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes | str] = {}
        self.ttls: dict[str, int | None] = {}

    def get(self, key: str) -> bytes | str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        self.ttls[key] = ex
        return True

    def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0


class FailingRedis:
    def get(self, key: str) -> str | None:
        raise TimeoutError("redis timed out")

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        raise TimeoutError("redis timed out")

    def delete(self, key: str) -> int:
        raise TimeoutError("redis timed out")


def _entry() -> CacheEntry:
    fingerprint = CacheFingerprint(
        scope=CacheScope.QUERY_ANALYSIS,
        settings_hash="settings",
        watermark_hash=None,
        query_hash="query",
        parameters_hash="parameters",
        fingerprint_hash="fingerprint",
        memory_arch="v3",
        recall_pipeline="v2",
        session_hash=None,
    )
    return CacheEntry(
        scope=CacheScope.QUERY_ANALYSIS,
        payload_type=CachePayloadType.QUERY_ANALYSIS,
        fingerprint=fingerprint,
        payload={"kind": "temporal"},
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
        ttl_s=60,
    )


def test_noop_derived_cache_is_disabled() -> None:
    cache = NoopDerivedCache()

    assert cache.backend_name == "noop"
    assert cache.get("key").status == CacheStatus.DISABLED
    assert cache.set("key", _entry()).status == CacheStatus.DISABLED
    assert cache.delete("key").status == CacheStatus.DISABLED


def test_redis_derived_cache_round_trips_entry_with_ttl() -> None:
    client = FakeRedis()
    cache = RedisDerivedCache(client, namespace="memoryos:test", default_ttl_s=60)
    key = "memoryos:test:derived-cache-v1:query_analysis:fingerprint"

    write = cache.set(key, _entry(), ttl_s=30)
    read = cache.get(key)

    assert write.status == CacheStatus.STORED
    assert read.status == CacheStatus.HIT
    assert read.entry is not None
    assert read.entry.payload == {"kind": "temporal"}
    assert client.ttls[key] == 30
    assert key in client.values
    assert f"memoryos:test:{key}" not in client.values


def test_redis_derived_cache_reports_corrupt_and_stale() -> None:
    client = FakeRedis()
    cache = RedisDerivedCache(client, namespace="memoryos:test", default_ttl_s=60)
    bad_json_key = "memoryos:test:derived-cache-v1:query_analysis:bad-json"
    old_schema_key = "memoryos:test:derived-cache-v1:query_analysis:old-schema"
    client.values[bad_json_key] = "not-json"
    client.values[old_schema_key] = json.dumps(
        {"schema_version": 0, "entry_version": CACHE_ENTRY_VERSION, "payload": {}}
    )

    assert cache.get(bad_json_key).status == CacheStatus.CORRUPT
    assert cache.get(old_schema_key).status == CacheStatus.STALE


def test_redis_derived_cache_reports_corrupt_for_invalid_bytes() -> None:
    client = FakeRedis()
    cache = RedisDerivedCache(client, namespace="memoryos:test", default_ttl_s=60)
    key = "memoryos:test:derived-cache-v1:query_analysis:invalid-bytes"
    client.values[key] = b"\xff\xfe"

    result = cache.get(key)

    assert result.status == CacheStatus.CORRUPT
    assert result.reason is not None
    assert "latency_ms" in result.diagnostics


def test_redis_derived_cache_errors_do_not_raise() -> None:
    cache = RedisDerivedCache(FailingRedis(), namespace="memoryos:test", default_ttl_s=60)

    assert cache.get("key").status == CacheStatus.ERROR
    assert cache.set("key", _entry()).status == CacheStatus.ERROR
    assert cache.delete("key").status == CacheStatus.ERROR


def test_create_derived_cache_defaults_to_noop_without_redis_url() -> None:
    cache = create_derived_cache(Settings(memoryos_redis_url=None))

    assert isinstance(cache, NoopDerivedCache)


def test_create_derived_cache_falls_back_to_noop_without_redis_package(
    monkeypatch,
) -> None:
    def missing_redis(name: str):
        assert name == "redis"
        raise ImportError("redis package is not installed")

    monkeypatch.setattr("memoryos_lite.cache.derived.import_module", missing_redis)

    cache = create_derived_cache(Settings(memoryos_redis_url="redis://localhost:6379/0"))

    assert isinstance(cache, NoopDerivedCache)


def test_create_derived_cache_falls_back_to_noop_when_client_creation_fails(
    monkeypatch,
) -> None:
    class FailingRedisFactory:
        @staticmethod
        def from_url(*args, **kwargs):
            raise TimeoutError("redis unavailable")

    class FakeRedisModule:
        Redis = FailingRedisFactory

    def fake_import(name: str):
        assert name == "redis"
        return FakeRedisModule

    monkeypatch.setattr("memoryos_lite.cache.derived.import_module", fake_import)

    cache = create_derived_cache(Settings(memoryos_redis_url="redis://localhost:6379/0"))

    assert isinstance(cache, NoopDerivedCache)


def test_create_derived_cache_uses_injected_redis_client() -> None:
    cache = create_derived_cache(
        Settings(memoryos_redis_url="redis://localhost:6379/0"),
        redis_client=FakeRedis(),
    )

    assert isinstance(cache, RedisDerivedCache)
