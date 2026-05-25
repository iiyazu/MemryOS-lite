# feature: memoryos-redis-cache-probe

## Goal / User-Visible Value

Add an optional Redis-backed cache probe for MemoryOS Lite so retrieval and
context-building performance can be measured and improved without changing the
authoritative memory model.

This feature is a performance infrastructure lane. It must prove that Redis can
reduce repeated query/retrieval work while preserving current MemoryOS behavior,
source attribution, and deterministic fallback when Redis is unavailable.

This feature must not describe MemoryOS Lite as production-ready MemoryOS.

## Status

Planned feature lane. This feature is registered in
`xmuse/master_state.json` and must remain in planning until Master
dispatches a Slave.

Master must create/confirm the isolated worktree before dispatching a Slave.

## Baseline Context

Current project baseline:

- `MEMORYOS_MEMORY_ARCH=v3` is the default layered composer path.
- `MEMORYOS_MEMORY_ARCH=v1` fallback must remain available.
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- SQLite is the authoritative store.
- Filesystem pages and traces are debug/audit mirrors only.
- Qdrant is optional for ANN/vector experiments.
- Redis is not currently a dependency.

Existing local performance behavior:

- Token counting has an in-process LRU cache.
- Lexical page search caches an in-process BM25 index by page id/version.
- Recall v2 currently rebuilds query analysis, episode list, recall entries,
  and search results per call.

## Scope

In:

- Add Redis as an optional, default-off dependency/configuration path.
- Add a small cache abstraction that supports deterministic no-op fallback.
- Add cache key construction that binds session, query, pipeline settings, code
  namespace version, and SQLite-derived memory watermark.
- Cache safe derived results for repeated calls, starting with query analysis
  and recall candidate packages.
- Add explicit invalidation or stale-entry rejection for message/episode/page
  mutations that affect recall/context results.
- Emit diagnostics that show cache enabled/disabled, hit/miss/stale/error, key
  namespace, and fallback reason without leaking full message text.
- Add focused unit tests with an in-memory fake Redis client and no required
  external Redis service.
- Add an optional manual probe command or documented env recipe that can run
  against a real local Redis instance.

Out:

- Making Redis authoritative for messages, episodes, pages, core memory,
  archival memory, embeddings, traces, or eval reports.
- Requiring Redis for default tests, API startup, demos, or public benchmarks.
- Changing default MemoryOS behavior when `MEMORYOS_REDIS_URL` is unset.
- Using Redis to hide stale evidence, benchmark regressions, or missing source
  refs.
- Archive RAG implementation, Qdrant replacement, or vector database migration.
- Benchmark-specific hacks or score targets.
- Enabling `MEMORYOS_RECALL_PIPELINE=v2` or `MEMORYOS_AGENT_KERNEL=v1` by
  default.
- Merge. Master owns integrated tests, approval artifacts, and final merge
  decision.

## Proposed Design

Redis support should be introduced as a narrow adapter:

```text
Settings
  -> CacheConfig
  -> MemoryCache protocol
      -> NoopMemoryCache
      -> RedisMemoryCache

MemoryStore / recall path
  -> SQLite authoritative reads and writes
  -> watermark provider
  -> cache key builder
  -> optional cache lookup
  -> recompute on miss/stale/error
  -> write-through derived cache entry
```

Redis entries are derived artifacts only. Each value must be reconstructable from
SQLite and current settings. If Redis is unavailable, corrupt, stale, or returns
an incompatible schema version, MemoryOS must recompute from SQLite and continue.

## Candidate Cache Scopes

Phase 1 should keep the cache scopes conservative:

- Query analysis cache:
  - input: normalized query text;
  - settings: analyzer namespace/version;
  - output: deterministic `QueryAnalysis`.
- Recall candidate cache:
  - input: session id, retrieval query/task hash, recall pipeline, memory arch,
    neighbor settings, top-k, and memory watermark;
  - output: serializable hit/candidate metadata sufficient to rebuild the
    `ContextPackage` evidence list without losing source refs.

Later phases may explore:

- embedding/vector cache for query embeddings;
- context package fragment cache;
- archive passage candidate cache after archive-rag defines stable archive
  semantics.

Later phases must remain optional and separately justified by tests or probe
data.

## Cache Key And Invalidation Requirements

Every cache key must bind enough context to make stale entries unselectable:

- feature namespace/version, for example `memoryos:v1`;
- cache scope, for example `query_analysis` or `recall_candidates`;
- session id when session-scoped;
- stable hash of task/retrieval query;
- `MEMORYOS_MEMORY_ARCH`;
- `MEMORYOS_RECALL_PIPELINE`;
- relevant settings such as neighbor counts and top-k;
- SQLite-derived memory watermark for the affected session.

The first implementation may use a conservative watermark based on the latest
`created_at`/`updated_at` values and counts for messages, episodes, pages, core
memory, and archive records that affect the cached scope. A later refinement may
replace this with an explicit revision table if needed.

Mutations must either:

- change the watermark used in cache keys; or
- explicitly invalidate the affected namespace/session keys.

It is acceptable for the first lane to prefer stale-entry rejection through
watermarked keys over broad Redis key deletion.

## Allowed Files

Product code:

- `pyproject.toml`
- `src/memoryos_lite/config.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/retrieval/query_analyzer.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- new focused modules under `src/memoryos_lite/cache/`
- `src/memoryos_lite/observability.py` if cache metrics are added.

Tests:

- `tests/test_memory_cache.py`
- `tests/test_recall_cache.py`
- `tests/test_config.py`
- narrowly scoped performance/probe tests if they are deterministic and do not
  require a live Redis service.

Docs/artifacts:

- `docs/store-interface.md` if the watermark contract is documented.
- `docs/public-benchmark-diagnosis.md` only if diagnostics semantics change.
- `xmuse/work/features/memoryos-redis-cache-probe/*` feature-local
  artifacts.

Not allowed:

- `xmuse/work/features/archive-rag/*`
- `xmuse/work/features/benchmark-layer-organization/*`
- `xmuse/work/features/xmuse-console/*`
- `xmuse/history/`
- `xmuse/legacy/root-loop/`
- benchmark fixture rewrites unless a focused test explicitly requires a new
  hermetic fixture.

## Invariants

- SQLite remains authoritative.
- Redis cache is optional and default-off.
- No default behavior changes when Redis settings are unset.
- No source refs may be dropped by cache serialization/deserialization.
- Cache failures must degrade to recompute, not user-visible failure, unless the
  user explicitly enables a strict diagnostic mode.
- v1 fallback, v3 default, v2 opt-in recall, and kernel opt-in defaults remain
  unchanged.
- Public benchmark `source_hit` must not be reinterpreted as pure cache or
  retrieval success.
- Cache diagnostics must not leak raw message text or secrets.

## Implementation Phases

### Phase 0: Contract And RED Tests

Goal:

Define cache configuration, protocol boundaries, key requirements, and fallback
behavior through tests before adding Redis implementation details.

Required outcomes:

- Tests prove Redis is disabled by default.
- Tests prove invalid Redis URL/client failure falls back to no-op cache.
- Tests prove cache keys include session/query/settings/watermark context.
- Tests prove source refs survive a cache round trip for recall candidates.

Suggested commands:

```bash
uv run pytest tests/test_memory_cache.py tests/test_config.py -q
uv run ruff check src/memoryos_lite/config.py src/memoryos_lite/cache tests/test_memory_cache.py
```

### Phase 1: Optional Redis Adapter

Goal:

Add `MemoryCache`, `NoopMemoryCache`, and `RedisMemoryCache` without wiring the
cache into behavior-critical paths.

Required outcomes:

- `MEMORYOS_REDIS_URL` enables Redis only when set.
- Redis package is optional at runtime unless Redis is enabled.
- Serialization includes schema version and cache scope.
- Corrupt/incompatible values are treated as misses.
- Unit tests use fake Redis and do not require a running Redis server.

Suggested commands:

```bash
uv run pytest tests/test_memory_cache.py -q
uv run ruff check src/memoryos_lite/cache tests/test_memory_cache.py
```

### Phase 2: Recall Cache Probe

Goal:

Wire cache lookups into safe recall v2 derived results behind an explicit cache
setting. The implementation must not affect v1 recall/default behavior.

Required outcomes:

- With Redis/cache disabled, current tests and outputs remain unchanged.
- With fake Redis enabled, repeated v2 recall calls report miss then hit.
- Mutating session memory changes watermark and prevents stale reuse.
- Retrieved evidence, message ids, packet metadata, diagnostics, and source refs
  match uncached results.

Suggested commands:

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run pytest tests/test_recall_pipeline.py tests/test_recall_cache.py -q
uv run pytest tests/test_engine.py::test_recall_pipeline_defaults_to_v1 -q
```

### Phase 3: Diagnostics And Manual Probe

Goal:

Make cache behavior observable enough to decide whether Redis should remain a
first-class optional optimization.

Required outcomes:

- Context package metadata or trace events expose cache hit/miss/stale/fallback
  status.
- A documented local probe can compare repeated recall/context latency with and
  without Redis.
- Probe output is diagnostic only and cannot be used as a benchmark score claim.

Suggested commands:

```bash
uv run pytest tests/test_memory_cache.py tests/test_recall_cache.py tests/test_recall_pipeline.py -q
uv run ruff check src/memoryos_lite/cache src/memoryos_lite/retrieval tests/test_memory_cache.py tests/test_recall_cache.py
```

### Phase 4: Full Verification And ACK

Goal:

Prepare the feature for Master review without relying on Redis availability in
CI/default local verification.

Required outcomes:

- Focused tests pass.
- Existing hardening and recall tests pass.
- `uv run pytest -q` passes or any unrelated existing failure is documented with
  evidence.
- `uv run ruff check .` passes or scoped lint rationale is documented.
- `uv run mypy src` result is recorded.
- Slave produces `result.md`, `execute_review.md`, `review_verdict.json`, and
  `ack.json`.

## Review Gates

Slave may report `ack_level=usable` only if:

- Redis remains optional and default-off.
- No authoritative data moves out of SQLite.
- Cache miss/error/stale paths recompute from SQLite.
- Source refs and evidence metadata are byte-for-byte or structurally equivalent
  to uncached output.
- v1 fallback and v3 default behavior are preserved.
- Focused cache tests and recall tests pass.
- Any real Redis probe is clearly labeled diagnostic and not required for
  default verification.

Master must not move this lane to merge review if:

- Redis is required for normal test execution.
- Cache keys omit memory watermark or settings that affect recall results.
- Cache hits can return stale evidence after session mutation.
- Cached recall output drops source attribution or diagnostics.
- The implementation claims benchmark improvement without a fixed-slice
  comparison and non-cache regression guard.

## Expected Artifacts

Slave-owned:

- `xmuse/work/features/memoryos-redis-cache-probe/context_bundle.md`
- `xmuse/work/features/memoryos-redis-cache-probe/brainstorm.md`
- `xmuse/work/features/memoryos-redis-cache-probe/plan.md`
- `xmuse/work/features/memoryos-redis-cache-probe/plan_final.md`
- `xmuse/work/features/memoryos-redis-cache-probe/result.md`
- `xmuse/work/features/memoryos-redis-cache-probe/execute_review.md`
- `xmuse/work/features/memoryos-redis-cache-probe/review_verdict.json`
- `xmuse/work/features/memoryos-redis-cache-probe/ack.json`
- `xmuse/work/features/memoryos-redis-cache-probe/slave_state.json`

Master-owned:

- `xmuse/master/features/memoryos-redis-cache-probe/master_review.json`
- `xmuse/master/features/memoryos-redis-cache-probe/integrated_tests.json`
- `xmuse/approvals/memoryos-redis-cache-probe/merge_approval_request.json`
- `xmuse/approvals/memoryos-redis-cache-probe/merge_approval.json`
- `xmuse/approvals/memoryos-redis-cache-probe/merge_decision.json`
- `xmuse/approvals/memoryos-redis-cache-probe/post_merge_verification.json`
