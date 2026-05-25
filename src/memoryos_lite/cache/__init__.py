"""Optional derived-result cache adapters.

Redis is never authoritative for MemoryOS state. These adapters only store
reconstructable JSON payloads and degrade to misses/errors that callers can
recompute from SQLite.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
from typing import Any, Protocol

from memoryos_lite.cache.derived import (
    CACHE_ENTRY_VERSION,
    CACHE_SCHEMA_VERSION,
    CacheDiagnostics,
    CacheEntry,
    CacheFingerprint,
    CacheKeyBuilder,
    CachePayloadType,
    CacheReadResult,
    CacheScope,
    CacheStatus,
    CacheWriteResult,
    DerivedCache,
    NoopDerivedCache,
    RedisDerivedCache,
    create_derived_cache,
)
from memoryos_lite.config import Settings

CACHE_KEY_VERSION = "keyv1"


@dataclass(frozen=True)
class CacheRead:
    status: str
    value: dict[str, Any] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class CacheWrite:
    status: str
    reason: str | None = None


class MemoryCache(Protocol):
    def get_json(self, key: str) -> CacheRead: ...

    def set_json(
        self,
        key: str,
        value: dict[str, Any],
        *,
        ttl_s: int | None = None,
    ) -> CacheWrite: ...


class NoopMemoryCache:
    def get_json(self, key: str) -> CacheRead:
        return CacheRead(status="disabled")

    def set_json(
        self,
        key: str,
        value: dict[str, Any],
        *,
        ttl_s: int | None = None,
    ) -> CacheWrite:
        return CacheWrite(status="disabled")


class RedisMemoryCache:
    def __init__(
        self,
        client: Any,
        *,
        namespace: str,
        default_ttl_s: int,
    ) -> None:
        self.client = client
        self.namespace = namespace.strip(":")
        self.default_ttl_s = default_ttl_s

    def get_json(self, key: str) -> CacheRead:
        try:
            raw = self.client.get(self._key(key))
        except Exception as exc:  # Redis is optional; callers should recompute.
            return CacheRead(status="error", reason=str(exc))
        if raw is None:
            return CacheRead(status="miss")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            envelope = json.loads(raw)
        except (TypeError, ValueError) as exc:
            return CacheRead(status="corrupt", reason=str(exc))
        if not isinstance(envelope, dict):
            return CacheRead(status="corrupt", reason="cache envelope is not an object")
        if envelope.get("schema_version") != CACHE_SCHEMA_VERSION:
            return CacheRead(status="stale", reason="cache schema version mismatch")
        value = envelope.get("value")
        if not isinstance(value, dict):
            return CacheRead(status="corrupt", reason="cache value is not an object")
        return CacheRead(status="hit", value=value)

    def set_json(
        self,
        key: str,
        value: dict[str, Any],
        *,
        ttl_s: int | None = None,
    ) -> CacheWrite:
        envelope = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "value": value,
        }
        try:
            self.client.set(
                self._key(key),
                json.dumps(envelope, ensure_ascii=False, sort_keys=True),
                ex=self.default_ttl_s if ttl_s is None else ttl_s,
            )
        except Exception as exc:  # Redis is optional; writes must not break callers.
            return CacheWrite(status="error", reason=str(exc))
        return CacheWrite(status="stored")

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"


def build_cache_key(
    *,
    scope: str,
    settings: Settings,
    query: str,
    session_id: str | None = None,
    memory_watermark: str | None = None,
    parameters: Mapping[str, Any] | None = None,
) -> str:
    normalized_query = " ".join(query.split())
    payload = {
        "key_version": CACHE_KEY_VERSION,
        "scope": scope,
        "session_id": session_id,
        "query_sha256": sha256(normalized_query.encode("utf-8")).hexdigest(),
        "memory_watermark": memory_watermark,
        "memory_arch": settings.resolved_memory_arch,
        "recall_pipeline": settings.resolved_recall_pipeline,
        "evidence_candidate_top_k": settings.memoryos_evidence_candidate_top_k,
        "evidence_context_neighbors_before": settings.memoryos_evidence_context_neighbors_before,
        "evidence_context_neighbors_after": settings.memoryos_evidence_context_neighbors_after,
        "parameters": dict(parameters or {}),
    }
    digest = sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return f"{scope}:{CACHE_KEY_VERSION}:{digest}"


def create_memory_cache(
    settings: Settings,
    *,
    redis_client: Any | None = None,
) -> MemoryCache:
    if not settings.memoryos_redis_url:
        return NoopMemoryCache()
    if redis_client is not None:
        return RedisMemoryCache(
            redis_client,
            namespace=settings.memoryos_cache_namespace,
            default_ttl_s=settings.memoryos_cache_default_ttl_s,
        )
    try:
        redis_module = import_module("redis")
    except ImportError:
        return NoopMemoryCache()
    try:
        client = redis_module.Redis.from_url(
            settings.memoryos_redis_url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=True,
        )
    except Exception:
        return NoopMemoryCache()
    return RedisMemoryCache(
        client,
        namespace=settings.memoryos_cache_namespace,
        default_ttl_s=settings.memoryos_cache_default_ttl_s,
    )


__all__ = [
    "CACHE_ENTRY_VERSION",
    "CACHE_SCHEMA_VERSION",
    "CacheRead",
    "CacheDiagnostics",
    "CacheEntry",
    "CacheFingerprint",
    "CacheKeyBuilder",
    "CachePayloadType",
    "CacheReadResult",
    "CacheScope",
    "CacheStatus",
    "CacheWriteResult",
    "CacheWrite",
    "DerivedCache",
    "MemoryCache",
    "NoopDerivedCache",
    "NoopMemoryCache",
    "RedisDerivedCache",
    "RedisMemoryCache",
    "build_cache_key",
    "create_derived_cache",
    "create_memory_cache",
]
