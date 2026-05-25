from __future__ import annotations

from datetime import UTC, datetime

from memoryos_lite.cache.derived import (
    CACHE_ENTRY_VERSION,
    CACHE_SCHEMA_VERSION,
    CacheEntry,
    CacheFingerprint,
    CacheKeyBuilder,
    CachePayloadType,
    CacheScope,
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

    assert key.startswith(f"memoryos:test:{CACHE_ENTRY_VERSION}:recall_context_package:")
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
