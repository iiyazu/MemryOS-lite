from __future__ import annotations

from datetime import UTC, datetime
from typing import get_type_hints

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
        key
        == "memoryos:test:"
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
        session_id=None,
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
        session_id=None,
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
    try:
        CacheKeyBuilder(namespace=":::")
    except ValueError as exc:
        assert "namespace" in str(exc)
    else:
        raise AssertionError("empty cache namespace should be rejected")


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
