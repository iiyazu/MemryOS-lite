"""Backend-neutral contracts for derived-result cache entries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from importlib import import_module
from time import perf_counter
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, model_validator

from memoryos_lite.config import Settings

CACHE_SCHEMA_VERSION = 1
CACHE_ENTRY_VERSION = "derived-cache-v1"


class CacheScope(StrEnum):
    QUERY_ANALYSIS = "query_analysis"
    RECALL_CANDIDATES = "recall_candidates"
    RECALL_CONTEXT_PACKAGE = "recall_context_package"


class CachePayloadType(StrEnum):
    QUERY_ANALYSIS = "query_analysis"
    RECALL_CANDIDATES = "recall_candidates"
    CONTEXT_PACKAGE = "context_package"


class CacheStatus(StrEnum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    CORRUPT = "corrupt"
    INVALID = "invalid"
    ERROR = "error"
    DISABLED = "disabled"
    STORED = "stored"


class CacheFingerprint(BaseModel):
    scope: CacheScope
    settings_hash: str
    watermark_hash: str | None = None
    query_hash: str
    parameters_hash: str
    fingerprint_hash: str
    memory_arch: str
    recall_pipeline: str
    session_hash: str | None = None


class CacheEntry(BaseModel):
    schema_version: int = CACHE_SCHEMA_VERSION
    entry_version: str = CACHE_ENTRY_VERSION
    scope: CacheScope
    payload_type: CachePayloadType
    fingerprint: CacheFingerprint
    payload: dict[str, Any]
    created_at: datetime
    ttl_s: int | None = None
    authority: dict[str, str] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_authority(self) -> CacheEntry:
        authority = dict(self.authority)
        authority.setdefault("store", "sqlite")
        authority.setdefault("store_revision", self.fingerprint.watermark_hash or "none")
        authority.setdefault("source", "derived")
        self.authority = authority
        return self


class CacheReadResult(BaseModel):
    status: CacheStatus
    key: str | None = None
    entry: CacheEntry | None = None
    reason: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CacheWriteResult(BaseModel):
    status: CacheStatus
    key: str | None = None
    reason: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CacheDiagnostics(BaseModel):
    status: CacheStatus
    key: str | None = None
    scope: CacheScope | None = None
    reason: str | None = None
    fingerprint_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DerivedCache(Protocol):
    backend_name: str

    def get(self, key: str) -> CacheReadResult: ...

    def set(
        self,
        key: str,
        entry: CacheEntry,
        *,
        ttl_s: int | None = None,
    ) -> CacheWriteResult: ...

    def delete(self, key: str) -> CacheWriteResult: ...

    def status(self) -> CacheDiagnostics: ...


class CacheKeyBuilder:
    def __init__(self, *, namespace: str) -> None:
        self.namespace = namespace.strip().strip(":").strip()
        if not self.namespace:
            raise ValueError("cache namespace must not be empty")

    def build_key(
        self,
        *,
        scope: CacheScope,
        settings: Settings,
        query: str,
        session_id: str | None = None,
        watermark: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> str:
        fingerprint = self.build_fingerprint(
            scope=scope,
            settings=settings,
            query=query,
            session_id=session_id,
            watermark=watermark,
            parameters=parameters,
        )
        return (
            f"{self.namespace}:{CACHE_ENTRY_VERSION}:"
            f"{scope.value}:{fingerprint.fingerprint_hash}"
        )

    def build_fingerprint(
        self,
        *,
        scope: CacheScope,
        settings: Settings,
        query: str,
        session_id: str | None = None,
        watermark: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> CacheFingerprint:
        memory_arch = settings.resolved_memory_arch
        recall_pipeline = settings.resolved_recall_pipeline
        settings_hash = _hash_json(
            {
                "memory_arch": memory_arch,
                "recall_pipeline": recall_pipeline,
                "evidence_candidate_top_k": settings.memoryos_evidence_candidate_top_k,
                "evidence_context_neighbors_before": (
                    settings.memoryos_evidence_context_neighbors_before
                ),
                "evidence_context_neighbors_after": (
                    settings.memoryos_evidence_context_neighbors_after
                ),
            }
        )
        watermark_hash = _hash_text(watermark) if watermark is not None else None
        query_hash = _hash_text(" ".join(query.split()))
        session_hash = _hash_text(session_id) if session_id is not None else None
        parameters_hash = _hash_json(dict(parameters or {}))
        fingerprint_hash = _hash_json(
            {
                "entry_version": CACHE_ENTRY_VERSION,
                "scope": scope.value,
                "settings_hash": settings_hash,
                "watermark_hash": watermark_hash,
                "query_hash": query_hash,
                "parameters_hash": parameters_hash,
                "session_hash": session_hash,
                "memory_arch": memory_arch,
                "recall_pipeline": recall_pipeline,
            }
        )
        return CacheFingerprint(
            scope=scope,
            settings_hash=settings_hash,
            watermark_hash=watermark_hash,
            query_hash=query_hash,
            parameters_hash=parameters_hash,
            fingerprint_hash=fingerprint_hash,
            memory_arch=memory_arch,
            recall_pipeline=recall_pipeline,
            session_hash=session_hash,
        )


class NoopDerivedCache:
    backend_name = "noop"

    def get(self, key: str) -> CacheReadResult:
        return CacheReadResult(status=CacheStatus.DISABLED, key=key)

    def set(
        self,
        key: str,
        entry: CacheEntry,
        *,
        ttl_s: int | None = None,
    ) -> CacheWriteResult:
        return CacheWriteResult(status=CacheStatus.DISABLED, key=key)

    def delete(self, key: str) -> CacheWriteResult:
        return CacheWriteResult(status=CacheStatus.DISABLED, key=key)

    def status(self) -> CacheDiagnostics:
        return CacheDiagnostics(
            status=CacheStatus.DISABLED,
            metadata={"backend": self.backend_name, "enabled": False},
        )


class RedisDerivedCache:
    backend_name = "redis"

    def __init__(
        self,
        client: Any,
        *,
        namespace: str,
        default_ttl_s: int,
    ) -> None:
        self.client = client
        self.namespace = namespace.strip().strip(":").strip()
        self.default_ttl_s = default_ttl_s

    def get(self, key: str) -> CacheReadResult:
        started = perf_counter()
        try:
            raw = self.client.get(key)
        except Exception as exc:  # Redis is optional; callers should recompute.
            return CacheReadResult(
                status=CacheStatus.ERROR,
                key=key,
                reason=str(exc),
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        if raw is None:
            return CacheReadResult(
                status=CacheStatus.MISS,
                key=key,
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            return CacheReadResult(
                status=CacheStatus.CORRUPT,
                key=key,
                reason=str(exc),
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        if not isinstance(payload, dict):
            return CacheReadResult(
                status=CacheStatus.CORRUPT,
                key=key,
                reason="cache entry is not an object",
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return CacheReadResult(
                status=CacheStatus.STALE,
                key=key,
                reason="cache schema version mismatch",
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        if payload.get("entry_version") != CACHE_ENTRY_VERSION:
            return CacheReadResult(
                status=CacheStatus.STALE,
                key=key,
                reason="cache entry version mismatch",
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        try:
            entry = CacheEntry.model_validate(payload)
        except ValidationError as exc:
            return CacheReadResult(
                status=CacheStatus.CORRUPT,
                key=key,
                reason=str(exc),
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        return CacheReadResult(
            status=CacheStatus.HIT,
            key=key,
            entry=entry,
            diagnostics={"latency_ms": _latency_ms(started)},
        )

    def set(
        self,
        key: str,
        entry: CacheEntry,
        *,
        ttl_s: int | None = None,
    ) -> CacheWriteResult:
        started = perf_counter()
        try:
            self.client.set(
                key,
                entry.model_dump_json(),
                ex=self.default_ttl_s if ttl_s is None else ttl_s,
            )
        except Exception as exc:  # Redis is optional; writes must not break callers.
            return CacheWriteResult(
                status=CacheStatus.ERROR,
                key=key,
                reason=str(exc),
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        return CacheWriteResult(
            status=CacheStatus.STORED,
            key=key,
            diagnostics={"latency_ms": _latency_ms(started)},
        )

    def delete(self, key: str) -> CacheWriteResult:
        started = perf_counter()
        try:
            self.client.delete(key)
        except Exception as exc:  # Redis is optional; callers should continue.
            return CacheWriteResult(
                status=CacheStatus.ERROR,
                key=key,
                reason=str(exc),
                diagnostics={"latency_ms": _latency_ms(started)},
            )
        return CacheWriteResult(
            status=CacheStatus.STORED,
            key=key,
            diagnostics={"latency_ms": _latency_ms(started)},
        )

    def status(self) -> CacheDiagnostics:
        return CacheDiagnostics(
            status=CacheStatus.HIT,
            metadata={
                "backend": self.backend_name,
                "enabled": True,
                "namespace": self.namespace,
            },
        )


def create_derived_cache(
    settings: Settings,
    *,
    redis_client: Any | None = None,
) -> DerivedCache:
    if not settings.memoryos_redis_url:
        return NoopDerivedCache()
    if redis_client is not None:
        return RedisDerivedCache(
            redis_client,
            namespace=settings.memoryos_cache_namespace,
            default_ttl_s=settings.memoryos_cache_default_ttl_s,
        )
    try:
        redis_module = import_module("redis")
    except ImportError:
        return NoopDerivedCache()
    try:
        client = redis_module.Redis.from_url(
            settings.memoryos_redis_url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=True,
        )
    except Exception:
        return NoopDerivedCache()
    return RedisDerivedCache(
        client,
        namespace=settings.memoryos_cache_namespace,
        default_ttl_s=settings.memoryos_cache_default_ttl_s,
    )


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _hash_text(raw)


def _latency_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


__all__ = [
    "CACHE_ENTRY_VERSION",
    "CACHE_SCHEMA_VERSION",
    "CacheDiagnostics",
    "CacheEntry",
    "CacheFingerprint",
    "CacheKeyBuilder",
    "CachePayloadType",
    "CacheReadResult",
    "CacheScope",
    "CacheStatus",
    "CacheWriteResult",
    "DerivedCache",
    "NoopDerivedCache",
    "RedisDerivedCache",
    "create_derived_cache",
]
