# memoryos-redis-cache-probe Execute Review

feature_id: memoryos-redis-cache-probe
reviewed_at: 2026-05-24T16:37:09Z
base: 4c4712df763c652952a8066060bdb8bb4b37ba0b
head: fcccff6052e5073a6ebb98da4bc724ce8244edb2

## Review Scope

Read-only review of the bounded Phase 0/1 implementation:

- `pyproject.toml`
- `uv.lock`
- `src/memoryos_lite/config.py`
- `src/memoryos_lite/cache/__init__.py`
- `tests/test_config.py`
- `tests/test_memory_cache.py`

An external Codex read-only review was attempted with the same base/head and
requirements, but the tool timed out after 120 seconds without returning
findings. This artifact is therefore based on local self-review plus executed
verification.

## Findings

No blocking issues found for the bounded Phase 0/1 slice.

## Checks

- Default behavior: Redis is disabled when `MEMORYOS_REDIS_URL` is unset and
  `create_memory_cache()` returns `NoopMemoryCache`.
- Optional dependency: `redis` is only present as a project extra, not a default
  dependency.
- Failure fallback: missing Redis import, Redis construction failure, get
  failure, and set failure degrade to no-op/error statuses rather than raising
  to callers.
- Serialization: Redis values use a schema-versioned envelope; corrupt and
  incompatible values are treated as corrupt/stale misses.
- Source attribution: the focused round-trip test preserves `source_refs`.
- Key safety: cache keys include scope, key version, hashed normalized query,
  optional session, memory arch, recall pipeline, top-k/neighbors, parameters,
  and watermark; raw query text is not embedded in keys.
- Defaults: v3 default, v1 fallback, v2 opt-in, kernel default off, and SQLite
  authority are preserved.
- Benchmark policy: no benchmark score movement is claimed.

## Residual Risks

- Full blueprint Phase 2 recall cache probe is not implemented in this bounded
  turn.
- The memory watermark is accepted as a key-builder input; the SQLite-derived
  provider still needs a later implementation and tests.
- Full-suite and eval promotion gates were not rerun after this final commit.
