# Production Derived Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade derived cache layer for MemoryOS Lite recall/context reads while keeping SQLite authoritative and preserving default behavior.

**Architecture:** Introduce a backend-neutral `DerivedCache` contract with typed cache entries, centralized key building, conservative watermark-plus-TTL invalidation, Redis/no-op backends, and metadata diagnostics. Migrate the current v2 recall cache to this contract while preserving existing `recall_cache` and `query_analysis_cache` metadata compatibility fields.

**Tech Stack:** Python 3.11, Pydantic, SQLite/SQLAlchemy store, Redis optional extra, pytest, ruff, mypy.

---

## File Structure

- Create `src/memoryos_lite/cache/derived.py`
  - Owns `CacheScope`, `CacheStatus`, `CachePayloadType`, `CacheFingerprint`, `CacheEntry`, `CacheReadResult`, `CacheWriteResult`, `CacheDiagnostics`, `DerivedCache`, `NoopDerivedCache`, `RedisDerivedCache`, and `CacheKeyBuilder`.
- Modify `src/memoryos_lite/cache/__init__.py`
  - Re-export the new derived cache types and keep existing imports compatible.
  - Move existing Redis/no-op logic toward the new contract without breaking old tests.
- Modify `src/memoryos_lite/config.py`
  - Add scope TTL settings with validators.
- Modify `src/memoryos_lite/store.py`
  - Keep `session_memory_watermark()` as the first watermark provider and add a compact provider method if needed.
- Modify `src/memoryos_lite/retrieval/recall_pipeline.py`
  - Use `DerivedCache` for query analysis and recall context package caching.
  - Preserve `recall_cache` and `query_analysis_cache` metadata.
- Modify `src/memoryos_lite/context_composer.py`
  - Continue surfacing cache diagnostics through layer metadata.
- Create `tests/test_derived_cache.py`
  - Unit tests for key builder, envelope validation, backends, and diagnostics.
- Create `tests/test_derived_cache_redis_integration.py`
  - Optional real Redis smoke tests gated by `MEMORYOS_TEST_REDIS_URL`.
- Modify `tests/test_recall_cache.py`
  - Validate recall pipeline through the new contract.
- Modify `tests/test_config.py`
  - Validate scope TTL settings.
- Modify `docs/store-interface.md`
  - Document derived cache authority and invalidation semantics.

## Task 1: Cache Entry And Key Builder

**Files:**
- Create: `src/memoryos_lite/cache/derived.py`
- Test: `tests/test_derived_cache.py`

- [ ] **Step 1: Write failing tests for cache entry and key builder**

Add this to `tests/test_derived_cache.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_derived_cache.py -q
```

Expected: import failure for `memoryos_lite.cache.derived`.

- [ ] **Step 3: Implement cache entry and key builder**

Create `src/memoryos_lite/cache/derived.py`:

```python
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

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
    session_id: str | None = None


class CacheEntry(BaseModel):
    schema_version: int = CACHE_SCHEMA_VERSION
    entry_version: str = CACHE_ENTRY_VERSION
    scope: CacheScope
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ttl_s: int
    authority: dict[str, str] = Field(
        default_factory=lambda: {"store": "sqlite", "source": "derived"}
    )
    fingerprint: CacheFingerprint
    payload_type: CachePayloadType
    payload: dict[str, Any]
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_authority_revision(self) -> CacheEntry:
        self.authority.setdefault("store", "sqlite")
        self.authority.setdefault("source", "derived")
        self.authority.setdefault("store_revision", self.fingerprint.watermark_hash or "none")
        return self


class CacheReadResult(BaseModel):
    status: CacheStatus
    entry: CacheEntry | None = None
    reason: str | None = None
    latency_ms: float | None = None


class CacheWriteResult(BaseModel):
    status: CacheStatus
    reason: str | None = None
    latency_ms: float | None = None


class CacheDiagnostics(BaseModel):
    enabled: bool
    backend: str
    scope: CacheScope
    status: CacheStatus
    key_version: str = CACHE_ENTRY_VERSION
    watermark_hash: str | None = None
    latency_ms: float | None = None
    fallback_reason: str | None = None
    write_status: CacheStatus | None = None


class DerivedCache(Protocol):
    backend_name: str

    def get(self, key: str) -> CacheReadResult: ...

    def set(self, key: str, entry: CacheEntry, *, ttl_s: int | None = None) -> CacheWriteResult: ...

    def delete(self, key: str) -> CacheWriteResult: ...

    def status(self) -> dict[str, Any]: ...


class CacheKeyBuilder:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace.strip(":")
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
        return f"{self.namespace}:{CACHE_ENTRY_VERSION}:{scope.value}:{fingerprint.fingerprint_hash}"

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
        settings_payload = {
            "memory_arch": settings.resolved_memory_arch,
            "recall_pipeline": settings.resolved_recall_pipeline,
            "evidence_candidate_top_k": settings.memoryos_evidence_candidate_top_k,
            "neighbors_before": settings.memoryos_evidence_context_neighbors_before,
            "neighbors_after": settings.memoryos_evidence_context_neighbors_after,
        }
        parameters_payload = dict(parameters or {})
        settings_hash = _hash_json(settings_payload)
        watermark_hash = _hash_text(watermark) if watermark is not None else None
        query_hash = _hash_text(" ".join(query.split()))
        parameters_hash = _hash_json(parameters_payload)
        fingerprint_hash = _hash_json(
            {
                "entry_version": CACHE_ENTRY_VERSION,
                "scope": scope.value,
                "session_id": session_id,
                "settings_hash": settings_hash,
                "watermark_hash": watermark_hash,
                "query_hash": query_hash,
                "parameters_hash": parameters_hash,
            }
        )
        return CacheFingerprint(
            scope=scope,
            settings_hash=settings_hash,
            watermark_hash=watermark_hash,
            query_hash=query_hash,
            parameters_hash=parameters_hash,
            fingerprint_hash=fingerprint_hash,
            memory_arch=settings.resolved_memory_arch,
            recall_pipeline=settings.resolved_recall_pipeline,
            session_id=session_id,
        )


def _hash_text(value: str | None) -> str:
    return sha256((value or "").encode("utf-8")).hexdigest()


def _hash_json(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
```

- [ ] **Step 4: Export derived cache types**

Modify `src/memoryos_lite/cache/__init__.py` to import and export the new names:

```python
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
)
```

Add these names to `__all__`.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_derived_cache.py -q
uv run ruff check src/memoryos_lite/cache tests/test_derived_cache.py
```

Expected: all tests pass and ruff reports `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/cache/derived.py src/memoryos_lite/cache/__init__.py tests/test_derived_cache.py
git commit -m "feat: add derived cache key contract"
```

## Task 2: Noop And Redis Derived Backends

**Files:**
- Modify: `src/memoryos_lite/cache/derived.py`
- Modify: `src/memoryos_lite/cache/__init__.py`
- Test: `tests/test_derived_cache.py`

- [ ] **Step 1: Write failing backend tests**

Append to `tests/test_derived_cache.py`:

```python
import json

from memoryos_lite.cache.derived import (
    NoopDerivedCache,
    RedisDerivedCache,
    create_derived_cache,
)


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
    )
    return CacheEntry(
        scope=CacheScope.QUERY_ANALYSIS,
        payload_type=CachePayloadType.QUERY_ANALYSIS,
        fingerprint=fingerprint,
        payload={"kind": "temporal"},
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


def test_redis_derived_cache_errors_do_not_raise() -> None:
    cache = RedisDerivedCache(FailingRedis(), namespace="memoryos:test", default_ttl_s=60)

    assert cache.get("key").status == CacheStatus.ERROR
    assert cache.set("key", _entry()).status == CacheStatus.ERROR
    assert cache.delete("key").status == CacheStatus.ERROR


def test_create_derived_cache_defaults_to_noop_without_redis_url() -> None:
    cache = create_derived_cache(Settings(memoryos_redis_url=None))

    assert isinstance(cache, NoopDerivedCache)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_derived_cache.py -q
```

Expected: import failure for `NoopDerivedCache`, `RedisDerivedCache`, or `create_derived_cache`.

- [ ] **Step 3: Implement backends**

Append to `src/memoryos_lite/cache/derived.py`:

```python
from importlib import import_module
from time import perf_counter


class NoopDerivedCache:
    backend_name = "noop"

    def get(self, key: str) -> CacheReadResult:
        return CacheReadResult(status=CacheStatus.DISABLED)

    def set(self, key: str, entry: CacheEntry, *, ttl_s: int | None = None) -> CacheWriteResult:
        return CacheWriteResult(status=CacheStatus.DISABLED)

    def delete(self, key: str) -> CacheWriteResult:
        return CacheWriteResult(status=CacheStatus.DISABLED)

    def status(self) -> dict[str, Any]:
        return {"backend": self.backend_name, "enabled": False}


class RedisDerivedCache:
    backend_name = "redis"

    def __init__(self, client: Any, *, namespace: str, default_ttl_s: int) -> None:
        self.client = client
        self.namespace = namespace.strip(":")
        self.default_ttl_s = default_ttl_s

    def get(self, key: str) -> CacheReadResult:
        started = perf_counter()
        try:
            raw = self.client.get(key)
        except Exception as exc:
            return CacheReadResult(
                status=CacheStatus.ERROR,
                reason=str(exc),
                latency_ms=self._latency(started),
            )
        if raw is None:
            return CacheReadResult(status=CacheStatus.MISS, latency_ms=self._latency(started))
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError) as exc:
            return CacheReadResult(
                status=CacheStatus.CORRUPT,
                reason=str(exc),
                latency_ms=self._latency(started),
            )
        if not isinstance(decoded, dict):
            return CacheReadResult(
                status=CacheStatus.CORRUPT,
                reason="cache entry is not an object",
                latency_ms=self._latency(started),
            )
        if decoded.get("schema_version") != CACHE_SCHEMA_VERSION:
            return CacheReadResult(
                status=CacheStatus.STALE,
                reason="cache schema version mismatch",
                latency_ms=self._latency(started),
            )
        try:
            entry = CacheEntry.model_validate(decoded)
        except Exception as exc:
            return CacheReadResult(
                status=CacheStatus.CORRUPT,
                reason=str(exc),
                latency_ms=self._latency(started),
            )
        return CacheReadResult(
            status=CacheStatus.HIT,
            entry=entry,
            latency_ms=self._latency(started),
        )

    def set(self, key: str, entry: CacheEntry, *, ttl_s: int | None = None) -> CacheWriteResult:
        started = perf_counter()
        try:
            self.client.set(
                key,
                entry.model_dump_json(),
                ex=self.default_ttl_s if ttl_s is None else ttl_s,
            )
        except Exception as exc:
            return CacheWriteResult(
                status=CacheStatus.ERROR,
                reason=str(exc),
                latency_ms=self._latency(started),
            )
        return CacheWriteResult(status=CacheStatus.STORED, latency_ms=self._latency(started))

    def delete(self, key: str) -> CacheWriteResult:
        started = perf_counter()
        try:
            self.client.delete(key)
        except Exception as exc:
            return CacheWriteResult(
                status=CacheStatus.ERROR,
                reason=str(exc),
                latency_ms=self._latency(started),
            )
        return CacheWriteResult(status=CacheStatus.STORED, latency_ms=self._latency(started))

    def status(self) -> dict[str, Any]:
        return {"backend": self.backend_name, "enabled": True, "namespace": self.namespace}

    @staticmethod
    def _latency(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)


def create_derived_cache(settings: Settings, *, redis_client: Any | None = None) -> DerivedCache:
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
```

`RedisDerivedCache` must use the key passed by `CacheKeyBuilder` exactly. Do not
prefix it again in the backend; changing `memoryos_cache_namespace` is already
reflected in the generated key and intentionally causes a full cache miss.

- [ ] **Step 4: Export backend types**

Modify `src/memoryos_lite/cache/__init__.py` exports to include:

```python
from memoryos_lite.cache.derived import (
    NoopDerivedCache,
    RedisDerivedCache,
    create_derived_cache,
)
```

Add these names to `__all__`.

- [ ] **Step 5: Run backend tests**

Run:

```bash
uv run pytest tests/test_derived_cache.py tests/test_memory_cache.py -q
uv run ruff check src/memoryos_lite/cache tests/test_derived_cache.py tests/test_memory_cache.py
uv run mypy src/memoryos_lite/cache
```

Expected: all pass. The existing `tests/test_memory_cache.py` must remain compatible.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/cache/derived.py src/memoryos_lite/cache/__init__.py tests/test_derived_cache.py
git commit -m "feat: add derived cache backends"
```

## Task 3: Scoped TTL Settings

**Files:**
- Modify: `src/memoryos_lite/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Append to `tests/test_config.py`:

```python
def test_derived_cache_scope_ttl_defaults_are_positive() -> None:
    settings = Settings()

    assert settings.memoryos_cache_query_analysis_ttl_s == 3600
    assert settings.memoryos_cache_recall_candidates_ttl_s == 300
    assert settings.memoryos_cache_context_package_ttl_s == 300


def test_derived_cache_scope_ttls_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(memoryos_cache_query_analysis_ttl_s=0)
    with pytest.raises(ValidationError):
        Settings(memoryos_cache_recall_candidates_ttl_s=0)
    with pytest.raises(ValidationError):
        Settings(memoryos_cache_context_package_ttl_s=0)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_config.py::test_derived_cache_scope_ttl_defaults_are_positive tests/test_config.py::test_derived_cache_scope_ttls_must_be_positive -q
```

Expected: attribute errors for new settings.

- [ ] **Step 3: Add settings and validator**

Modify `src/memoryos_lite/config.py`:

```python
    memoryos_cache_query_analysis_ttl_s: int = 3600
    memoryos_cache_recall_candidates_ttl_s: int = 300
    memoryos_cache_context_package_ttl_s: int = 300
```

Add a validator:

```python
    @field_validator(
        "memoryos_cache_default_ttl_s",
        "memoryos_cache_query_analysis_ttl_s",
        "memoryos_cache_recall_candidates_ttl_s",
        "memoryos_cache_context_package_ttl_s",
    )
    @classmethod
    def validate_cache_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("cache TTL settings must be positive")
        return value
```

Replace the old single-field TTL validator with this multi-field validator.

- [ ] **Step 4: Run config tests**

Run:

```bash
uv run pytest tests/test_config.py -q
uv run ruff check src/memoryos_lite/config.py tests/test_config.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/config.py tests/test_config.py
git commit -m "feat: add scoped cache ttl settings"
```

## Task 4: Migrate RecallPipeline To DerivedCache

**Files:**
- Modify: `src/memoryos_lite/retrieval/recall_pipeline.py`
- Modify: `tests/test_recall_cache.py`
- Test: `tests/test_derived_cache.py`

- [ ] **Step 1: Write failing recall compatibility tests**

Add this to `tests/test_recall_cache.py`:

```python
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
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_recall_cache.py::test_recall_pipeline_emits_unified_cache_metadata_on_hit -q
uv run pytest tests/test_recall_cache.py::test_recall_candidate_cache_hits_when_context_budget_changes -q
```

Expected: first test fails on missing `metadata["cache"]`; second test fails
because the searcher still runs again when only context budget changes.

- [ ] **Step 3: Update RecallPipeline constructor**

Modify `src/memoryos_lite/retrieval/recall_pipeline.py` imports:

```python
from memoryos_lite.cache.derived import (
    CACHE_ENTRY_VERSION,
    CacheDiagnostics,
    CacheEntry,
    CacheKeyBuilder,
    CachePayloadType,
    CacheScope,
    CacheStatus,
    DerivedCache,
    NoopDerivedCache,
    create_derived_cache,
)
```

Change the constructor cache type:

```python
        cache: DerivedCache | None = None,
```

Initialize:

```python
        self.cache = cache if cache is not None else self._default_cache(settings)
        self.cache_key_builder = CacheKeyBuilder(settings.memoryos_cache_namespace)
```

- [ ] **Step 4: Replace recall context package read path**

In `build_context()`, compute:

```python
        memory_watermark = self.store.session_memory_watermark(session_id)
        recall_cache_status = self._cache_status(CacheScope.RECALL_CONTEXT_PACKAGE, CacheStatus.DISABLED)
        recall_cache_key: str | None = None
        recall_fingerprint = None
        if self.settings.memoryos_recall_cache_enabled:
            recall_fingerprint = self.cache_key_builder.build_fingerprint(
                scope=CacheScope.RECALL_CONTEXT_PACKAGE,
                settings=self.settings,
                session_id=session_id,
                query=query,
                watermark=memory_watermark,
                parameters={
                    "budget": budget,
                    "task_sha256": self._hash_text(task),
                    "top_k": 10,
                    "neighbors_before": self.settings.memoryos_evidence_context_neighbors_before,
                    "neighbors_after": self.settings.memoryos_evidence_context_neighbors_after,
                },
            )
            recall_cache_key = self.cache_key_builder.build_key(
                scope=CacheScope.RECALL_CONTEXT_PACKAGE,
                settings=self.settings,
                session_id=session_id,
                query=query,
                watermark=memory_watermark,
                parameters={
                    "budget": budget,
                    "task_sha256": self._hash_text(task),
                    "top_k": 10,
                    "neighbors_before": self.settings.memoryos_evidence_context_neighbors_before,
                    "neighbors_after": self.settings.memoryos_evidence_context_neighbors_after,
                },
            )
            cached = self.cache.get(recall_cache_key)
            recall_cache_status = self._cache_status(
                CacheScope.RECALL_CONTEXT_PACKAGE,
                cached.status,
                reason=cached.reason,
                latency_ms=cached.latency_ms,
                watermark_hash=recall_fingerprint.watermark_hash,
            )
            if cached.status == CacheStatus.HIT and cached.entry is not None:
                if cached.entry.fingerprint != recall_fingerprint:
                    recall_cache_status = self._cache_status(
                        CacheScope.RECALL_CONTEXT_PACKAGE,
                        CacheStatus.STALE,
                        reason="cached context package fingerprint mismatch",
                        latency_ms=cached.latency_ms,
                        watermark_hash=recall_fingerprint.watermark_hash,
                    )
                else:
                    package = self._package_from_entry(cached.entry)
                    if package is not None:
                        package.metadata["episode_backfilled"] = created
                        package.metadata["cache"] = recall_cache_status
                        package.metadata["recall_cache"] = recall_cache_status
                        package.metadata["query_analysis_cache"] = self._cache_status(
                            CacheScope.QUERY_ANALYSIS,
                            CacheStatus.DISABLED,
                            reason="recall_context_package_hit",
                        )
                        package.metadata["recall_candidate_cache"] = self._cache_status(
                            CacheScope.RECALL_CANDIDATES,
                            CacheStatus.DISABLED,
                            reason="recall_context_package_hit",
                        )
                        package.metadata["recall_memory_watermark"] = memory_watermark
                        return package
```

- [ ] **Step 5: Replace query analysis cache**

Replace `_analyze_query()` with:

```python
    def _analyze_query(self, query: str) -> tuple[QueryAnalysis, dict[str, object]]:
        if not self.settings.memoryos_recall_cache_enabled:
            return self.query_analyzer.analyze(query), self._cache_status(
                CacheScope.QUERY_ANALYSIS,
                CacheStatus.DISABLED,
            )

        fingerprint = self.cache_key_builder.build_fingerprint(
            scope=CacheScope.QUERY_ANALYSIS,
            settings=self.settings,
            query=query,
            parameters={},
        )
        key = self.cache_key_builder.build_key(
            scope=CacheScope.QUERY_ANALYSIS,
            settings=self.settings,
            query=query,
            parameters={},
        )
        cached = self.cache.get(key)
        status = self._cache_status(
            CacheScope.QUERY_ANALYSIS,
            cached.status,
            reason=cached.reason,
            latency_ms=cached.latency_ms,
        )
        if cached.status == CacheStatus.HIT and cached.entry is not None:
            try:
                if cached.entry.fingerprint != fingerprint:
                    raise ValueError("cached query analysis fingerprint mismatch")
                if cached.entry.scope != CacheScope.QUERY_ANALYSIS:
                    raise ValueError("cached query analysis scope mismatch")
                if cached.entry.payload_type != CachePayloadType.QUERY_ANALYSIS:
                    raise ValueError("cached query analysis payload type mismatch")
                analysis = QueryAnalysis(QueryKind(str(cached.entry.payload["kind"])))
                return analysis, status
            except (KeyError, ValueError, TypeError):
                status = self._cache_status(
                    CacheScope.QUERY_ANALYSIS,
                    CacheStatus.CORRUPT,
                    reason="cached query analysis failed validation",
                    latency_ms=cached.latency_ms,
                )

        analysis = self.query_analyzer.analyze(query)
        entry = CacheEntry(
            scope=CacheScope.QUERY_ANALYSIS,
            payload_type=CachePayloadType.QUERY_ANALYSIS,
            fingerprint=fingerprint,
            payload={"kind": analysis.kind.value},
            ttl_s=self.settings.memoryos_cache_query_analysis_ttl_s,
        )
        write = self.cache.set(
            key,
            entry,
            ttl_s=self.settings.memoryos_cache_query_analysis_ttl_s,
        )
        status["write_status"] = write.status.value
        if write.reason:
            status["write_reason"] = write.reason
        return analysis, status
```

- [ ] **Step 6: Add recall candidate cache**

Replace the direct `self.recall_searcher.search(...)` call with:

```python
        hits, candidate_cache_status = self._recall_candidates(
            recall_entries=recall_entries,
            query=query,
            analysis=analysis,
            memory_watermark=memory_watermark,
            preserve_session_neighbors=preserve_session_neighbors,
        )
```

In both `package.metadata.update({...})` blocks, add:

```python
                    "recall_candidate_cache": candidate_cache_status,
```

Add these helpers to `RecallPipeline`:

```python
    def _recall_candidates(
        self,
        *,
        recall_entries: list[RecallMemoryEntry],
        query: str,
        analysis: QueryAnalysis,
        memory_watermark: str,
        preserve_session_neighbors: bool,
    ) -> tuple[list[EpisodeHit], dict[str, object]]:
        parameters = {
            "top_k": 10,
            "neighbors_before": self.settings.memoryos_evidence_context_neighbors_before,
            "neighbors_after": self.settings.memoryos_evidence_context_neighbors_after,
            "preserve_session_neighbors": preserve_session_neighbors,
        }
        if not self.settings.memoryos_recall_cache_enabled:
            hits = self.recall_searcher.search(
                cast(Any, recall_entries),
                query,
                top_k=10,
                analysis=analysis,
                neighbors_before=self.settings.memoryos_evidence_context_neighbors_before,
                neighbors_after=self.settings.memoryos_evidence_context_neighbors_after,
                preserve_neighbors=preserve_session_neighbors,
            )
            return hits, self._cache_status(
                CacheScope.RECALL_CANDIDATES,
                CacheStatus.DISABLED,
            )

        fingerprint = self.cache_key_builder.build_fingerprint(
            scope=CacheScope.RECALL_CANDIDATES,
            settings=self.settings,
            query=query,
            watermark=memory_watermark,
            parameters=parameters,
        )
        key = self.cache_key_builder.build_key(
            scope=CacheScope.RECALL_CANDIDATES,
            settings=self.settings,
            query=query,
            watermark=memory_watermark,
            parameters=parameters,
        )
        cached = self.cache.get(key)
        status = self._cache_status(
            CacheScope.RECALL_CANDIDATES,
            cached.status,
            reason=cached.reason,
            latency_ms=cached.latency_ms,
            watermark_hash=fingerprint.watermark_hash,
        )
        if cached.status == CacheStatus.HIT and cached.entry is not None:
            if cached.entry.fingerprint != fingerprint:
                status = self._cache_status(
                    CacheScope.RECALL_CANDIDATES,
                    CacheStatus.STALE,
                    reason="cached recall candidates fingerprint mismatch",
                    latency_ms=cached.latency_ms,
                    watermark_hash=fingerprint.watermark_hash,
                )
            else:
                hits = self._hits_from_candidate_entry(cached.entry, recall_entries)
                if hits is not None:
                    return hits, status
                status = self._cache_status(
                    CacheScope.RECALL_CANDIDATES,
                    CacheStatus.CORRUPT,
                    reason="cached recall candidates failed validation",
                    latency_ms=cached.latency_ms,
                    watermark_hash=fingerprint.watermark_hash,
                )

        hits = self.recall_searcher.search(
            cast(Any, recall_entries),
            query,
            top_k=10,
            analysis=analysis,
            neighbors_before=self.settings.memoryos_evidence_context_neighbors_before,
            neighbors_after=self.settings.memoryos_evidence_context_neighbors_after,
            preserve_neighbors=preserve_session_neighbors,
        )
        entry = CacheEntry(
            scope=CacheScope.RECALL_CANDIDATES,
            payload_type=CachePayloadType.RECALL_CANDIDATES,
            fingerprint=fingerprint,
            payload={"hits": [self._candidate_from_hit(hit) for hit in hits]},
            ttl_s=self.settings.memoryos_cache_recall_candidates_ttl_s,
            diagnostics={"hits_count": len(hits)},
        )
        write = self.cache.set(
            key,
            entry,
            ttl_s=self.settings.memoryos_cache_recall_candidates_ttl_s,
        )
        status["write_status"] = write.status.value
        if write.reason:
            status["write_reason"] = write.reason
        return hits, status

    @staticmethod
    def _candidate_from_hit(hit: EpisodeHit) -> dict[str, object]:
        return {
            "message_id": hit.episode.message_id,
            "score": hit.score,
            "reason": hit.reason,
            "source": hit.source,
            "rank_features": dict(hit.rank_features),
            "neighbor_of": hit.neighbor_of,
            "packet_metadata": dict(hit.packet_metadata),
            "diagnostics": [
                diagnostic.model_dump(mode="json") for diagnostic in hit.diagnostics
            ],
        }

    @staticmethod
    def _hits_from_candidate_entry(
        entry: CacheEntry,
        recall_entries: list[RecallMemoryEntry],
    ) -> list[EpisodeHit] | None:
        if entry.scope != CacheScope.RECALL_CANDIDATES:
            return None
        if entry.payload_type != CachePayloadType.RECALL_CANDIDATES:
            return None
        raw_hits = entry.payload.get("hits")
        if not isinstance(raw_hits, list):
            return None
        by_message_id = {entry.message_id: entry for entry in recall_entries}
        hits: list[EpisodeHit] = []
        try:
            for raw in raw_hits:
                if not isinstance(raw, dict):
                    return None
                message_id = str(raw["message_id"])
                episode = by_message_id.get(message_id)
                if episode is None:
                    return None
                raw_rank_features = raw.get("rank_features", {})
                raw_packet_metadata = raw.get("packet_metadata", {})
                raw_diagnostics = raw.get("diagnostics", [])
                if not isinstance(raw_rank_features, dict):
                    return None
                if not isinstance(raw_packet_metadata, dict):
                    return None
                if not isinstance(raw_diagnostics, list):
                    return None
                hits.append(
                    EpisodeHit(
                        episode=episode,
                        score=float(raw["score"]),
                        reason=str(raw["reason"]),
                        source=str(raw.get("source", "recall_memory")),
                        diagnostics=tuple(
                            DiagnosticEvent.model_validate(diagnostic)
                            for diagnostic in raw_diagnostics
                            if isinstance(diagnostic, dict)
                        ),
                        rank_features={
                            str(key): float(value)
                            for key, value in raw_rank_features.items()
                        },
                        neighbor_of=(
                            None
                            if raw.get("neighbor_of") is None
                            else str(raw.get("neighbor_of"))
                        ),
                        packet_metadata=dict(raw_packet_metadata),
                    )
                )
        except (KeyError, TypeError, ValueError, ValidationError):
            return None
        return hits
```

- [ ] **Step 7: Replace context package write**

In both `package.metadata.update({...})` blocks in `build_context()`, add:

```python
                    "cache": recall_cache_status,
```

Update both calls from `_store_recall_package(recall_cache_key, package)` to:

```python
            self._store_recall_package(recall_cache_key, recall_fingerprint, package)
```

Replace `_store_recall_package()` with:

```python
    def _store_recall_package(
        self,
        recall_cache_key: str | None,
        recall_fingerprint,
        package: ContextPackage,
    ) -> None:
        if (
            not self.settings.memoryos_recall_cache_enabled
            or recall_cache_key is None
            or recall_fingerprint is None
        ):
            return
        entry = CacheEntry(
            scope=CacheScope.RECALL_CONTEXT_PACKAGE,
            payload_type=CachePayloadType.CONTEXT_PACKAGE,
            fingerprint=recall_fingerprint,
            payload={"package": package.model_dump(mode="json")},
            ttl_s=self.settings.memoryos_cache_context_package_ttl_s,
            diagnostics={
                "source_refs_count": sum(
                    len(diagnostic.get("source_refs", []))
                    for diagnostic in package.metadata.get("recall_diagnostics", [])
                    if isinstance(diagnostic, dict)
                ),
                "planned_ids_count": len(package.metadata.get("planned_evidence_message_ids", [])),
                "candidate_cache_status": package.metadata.get("recall_candidate_cache", {}).get("status"),
            },
        )
        write = self.cache.set(
            recall_cache_key,
            entry,
            ttl_s=self.settings.memoryos_cache_context_package_ttl_s,
        )
        cache_metadata = package.metadata.get("cache")
        if isinstance(cache_metadata, dict):
            cache_metadata["write_status"] = write.status.value
            if write.reason:
                cache_metadata["write_reason"] = write.reason
```

- [ ] **Step 8: Add compatibility helpers**

Add:

```python
    @staticmethod
    def _package_from_entry(entry: CacheEntry) -> ContextPackage | None:
        if entry.scope != CacheScope.RECALL_CONTEXT_PACKAGE:
            return None
        if entry.payload_type != CachePayloadType.CONTEXT_PACKAGE:
            return None
        package_value = entry.payload.get("package")
        if not isinstance(package_value, dict):
            return None
        try:
            return ContextPackage.model_validate(package_value)
        except ValidationError:
            return None

    def _cache_status(
        self,
        scope: CacheScope,
        status: CacheStatus,
        *,
        reason: str | None = None,
        latency_ms: float | None = None,
        watermark_hash: str | None = None,
    ) -> dict[str, object]:
        diagnostics = CacheDiagnostics(
            enabled=self.settings.memoryos_recall_cache_enabled,
            backend=self.cache.backend_name,
            scope=scope,
            status=status,
            watermark_hash=watermark_hash,
            latency_ms=latency_ms,
            fallback_reason=reason,
        )
        return diagnostics.model_dump(mode="json", exclude_none=True)
```

Keep `recall_cache` and `query_analysis_cache` metadata by assigning the unified
status dictionaries to those keys.

Update `_default_cache()` to return the new contract:

```python
    @staticmethod
    def _default_cache(settings: Settings) -> DerivedCache:
        if not settings.memoryos_recall_cache_enabled:
            return NoopDerivedCache()
        return create_derived_cache(settings)
```

- [ ] **Step 9: Run focused recall tests**

Run:

```bash
uv run pytest tests/test_recall_cache.py tests/test_derived_cache.py -q
uv run ruff check src/memoryos_lite/retrieval/recall_pipeline.py tests/test_recall_cache.py
uv run mypy src/memoryos_lite/retrieval/recall_pipeline.py src/memoryos_lite/cache
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add src/memoryos_lite/retrieval/recall_pipeline.py tests/test_recall_cache.py tests/test_derived_cache.py
git commit -m "feat: migrate recall cache to derived cache contract"
```

## Task 5: Context Composer Diagnostics And Documentation

**Files:**
- Modify: `src/memoryos_lite/context_composer.py`
- Modify: `docs/store-interface.md`
- Test: `tests/test_context_composer.py`

- [ ] **Step 1: Write failing composer metadata test**

Add a focused assertion to an existing v3 recall/composer test or create this test
in `tests/test_context_composer.py`:

```python
def test_v3_composer_preserves_cache_diagnostics_metadata(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
        memoryos_recall_cache_enabled=True,
        memoryos_redis_url="redis://localhost:6379/0",
    )
    service = MemoryOSService(store=create_store(settings), settings=settings)
    session = service.create_session("cache diagnostics")
    service.ingest(session.id, "Bob moved to Shanghai.")

    package = service.build_context(session.id, "Where did Bob move?")

    recall_layers = [item for item in package.layers if item.layer == "recall"]
    assert recall_layers
    assert "cache" in recall_layers[0].metadata
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_preserves_cache_diagnostics_metadata -q
```

Expected: missing `cache` metadata.

- [ ] **Step 3: Preserve cache diagnostics in v3 layer metadata**

Modify `src/memoryos_lite/context_composer.py` recall metadata mapping:

```python
            "cache": recall.metadata.get("cache", {}),
            "recall_cache": recall.metadata.get("recall_cache", {}),
            "query_analysis_cache": recall.metadata.get("query_analysis_cache", {}),
```

- [ ] **Step 4: Document derived cache semantics**

Append to `docs/store-interface.md`:

```markdown
## Derived Cache

The derived cache is optional and never authoritative. SQLite remains the source
of truth for memory state and source refs.

Derived cache entries may store query analysis, recall candidates, and recall
context packages. Keys include memory architecture, recall pipeline, settings
fingerprint, query hash, scope parameters, and a SQLite-derived memory
watermark. Watermark changes force a new key; TTL is a fallback stale-data guard.

Redis failures, corrupt entries, stale entries, and validation failures fall
back to SQLite recomputation. Cache diagnostics are surfaced in
`ContextPackage.metadata` and v3 layer metadata.
```

- [ ] **Step 5: Run tests and docs checks**

Run:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_preserves_cache_diagnostics_metadata -q
uv run ruff check src/memoryos_lite/context_composer.py tests/test_context_composer.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/context_composer.py tests/test_context_composer.py docs/store-interface.md
git commit -m "docs: document derived cache semantics"
```

## Task 6: Optional Real Redis Integration Smoke

**Files:**
- Create: `tests/test_derived_cache_redis_integration.py`

- [ ] **Step 1: Write gated Docker/Redis smoke test**

Create `tests/test_derived_cache_redis_integration.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from memoryos_lite.cache.derived import CacheStatus, RedisDerivedCache
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import RecallMemorySearcher
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message, Role
from memoryos_lite.store import create_store

redis = pytest.importorskip("redis")


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


@pytest.mark.integration
def test_real_redis_recall_context_cache_miss_then_hit(tmp_path: Path) -> None:
    url = os.environ.get("MEMORYOS_TEST_REDIS_URL")
    if not url:
        pytest.skip("MEMORYOS_TEST_REDIS_URL is not set")
    client = redis.Redis.from_url(url, decode_responses=True)
    assert client.ping() is True
    client.flushdb()
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recall_pipeline="v2",
        memoryos_recall_cache_enabled=True,
        memoryos_redis_url=url,
        memoryos_cache_namespace="memoryos:integration",
    )
    cache = RedisDerivedCache(client, namespace="memoryos:integration", default_ttl_s=60)
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
    pipeline = RecallPipeline(store=store, settings=settings, tokenizer=WordTokenizer(), cache=cache)
    pipeline.recall_searcher = searcher

    first = pipeline.build_context("ses", "Where did Bob move?", budget=200)
    second = pipeline.build_context("ses", "Where did Bob move?", budget=200)

    assert first.metadata["cache"]["status"] == CacheStatus.MISS.value
    assert second.metadata["cache"]["status"] == CacheStatus.HIT.value
    assert searcher.calls == 1
    assert second.retrieved_evidence[0].message_id == "msg_bob"
```

- [ ] **Step 2: Run skipped-by-default test**

Run:

```bash
uv run pytest tests/test_derived_cache_redis_integration.py -q
```

Expected: skipped when `MEMORYOS_TEST_REDIS_URL` is unset.

- [ ] **Step 3: Run real Redis test when Redis is available**

Start Redis externally or with Docker:

```bash
docker run -d --rm --name memoryos-derived-cache-test -p 127.0.0.1:6379:6379 redis:7-alpine
MEMORYOS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 uv run --extra redis pytest tests/test_derived_cache_redis_integration.py -q
docker stop memoryos-derived-cache-test
```

Expected: one integration test passes and the container is stopped.

- [ ] **Step 4: Commit**

```bash
git add tests/test_derived_cache_redis_integration.py
git commit -m "test: add derived cache redis integration smoke"
```

## Task 7: Final Verification

**Files:**
- No source changes unless verification exposes a defect.

- [ ] **Step 1: Run focused cache suite**

Run:

```bash
uv run pytest tests/test_derived_cache.py tests/test_memory_cache.py tests/test_recall_cache.py -q
```

Expected: all pass.

- [ ] **Step 2: Run static checks**

Run:

```bash
uv run ruff check src/memoryos_lite/cache src/memoryos_lite/retrieval/recall_pipeline.py src/memoryos_lite/context_composer.py tests/test_derived_cache.py tests/test_recall_cache.py tests/test_context_composer.py
uv run mypy src/memoryos_lite/cache src/memoryos_lite/retrieval/recall_pipeline.py src/memoryos_lite/context_composer.py
```

Expected: ruff reports `All checks passed!`; mypy reports success for checked files.

- [ ] **Step 3: Run full suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass. Report exact pass/warning count.

- [ ] **Step 4: Confirm architecture constraints**

Run:

```bash
uv run pytest tests/test_config.py tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_engine.py::test_recall_pipeline_defaults_to_v1 -q
```

Expected: all pass, confirming default v3, v1 fallback, and kernel-off behavior remain intact.

- [ ] **Step 5: Commit final docs or fixes**

If verification required small fixes, commit them:

```bash
git add src/memoryos_lite tests docs
git commit -m "fix: finalize derived cache verification"
```

If verification required no fixes, do not create an empty commit.
