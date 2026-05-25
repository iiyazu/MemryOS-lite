# memoryos-redis-cache-probe Result

feature_id: memoryos-redis-cache-probe
completed_at: 2026-05-24T16:37:09Z
branch: feat/memoryos-redis-cache-probe
worktree: /home/iiyatu/projects/python/memoryOS-memoryos-redis-cache-probe
head_commit: fcccff6052e5073a6ebb98da4bc724ce8244edb2
status: usable_bounded_phase_0_1

## Implemented

- Audited and adopted the pre-dispatch Redis feature-scoped dirty changes.
- Removed generated `src/memoryos_lite/cache/__pycache__` bytecode before final status.
- Added optional Redis dependency as a `redis` project extra; Redis is not in default dependencies.
- Added Redis cache settings:
  - `memoryos_redis_url: None` by default.
  - `memoryos_cache_namespace: "memoryos:v1"`.
  - `memoryos_cache_default_ttl_s: 300`.
- Added `memoryos_lite.cache`:
  - `MemoryCache` protocol.
  - `NoopMemoryCache`.
  - `RedisMemoryCache`.
  - schema-versioned JSON envelopes.
  - corrupt/stale/error statuses that callers can treat as recompute/no-op.
  - `create_memory_cache()` factory with optional Redis import and injected fake-client support.
  - `build_cache_key()` binding scope, hashed normalized query, session id, memory arch, recall pipeline, recall-neighbor/top-k settings, caller parameters, and caller-supplied memory watermark.
- Added focused tests for config defaults, optional dependency, adapter behavior, source-ref JSON round trip, failure fallback, schema mismatch, and key construction.

## Verification

- RED: `uv run pytest tests/test_memory_cache.py -q`
  - Result: expected collection error before implementation because `build_cache_key` was missing.
- GREEN/focused: `uv run pytest tests/test_config.py tests/test_memory_cache.py -q`
  - Result: `14 passed in 0.03s`.
- Lint: `uv run ruff check src/memoryos_lite/config.py src/memoryos_lite/cache tests/test_config.py tests/test_memory_cache.py`
  - Result: `All checks passed!`.
- Invariant smoke: `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags tests/test_engine.py::test_recall_pipeline_defaults_to_v1 -q`
  - Result: `3 passed in 1.47s`.
- Diff hygiene: `git diff --check 4c4712df763c652952a8066060bdb8bb4b37ba0b..HEAD`
  - Result: exit 0, no whitespace errors.

One attempted extra smoke command used a stale test selector
`tests/test_engine.py::test_service_defaults_to_v1_recall_pipeline`; pytest
reported no matching test and no tests ran. That command is not counted as
passing evidence; it was replaced by the valid invariant smoke command above.

## Invariants

- v3 default preserved.
- v1 fallback preserved.
- Recall v2 remains opt-in.
- Agent kernel remains off by default.
- SQLite remains authoritative; Redis stores derived JSON only and is not wired
  into store mutation or recall behavior.
- Redis remains optional and default-off.
- Source refs are preserved by JSON round trip in the focused cache test.
- No benchmark score target or improvement claim is made.

## Not Implemented In This Bounded Slice

- Recall v2 miss/hit write-through cache behavior.
- SQLite-derived memory watermark provider.
- Real Redis manual probe command.
- Integrated full-suite, public benchmark, or hard eval promotion evidence.
