# memoryos-redis-cache-probe Context Bundle

feature_id: memoryos-redis-cache-probe
generated_at: 2026-05-24T16:29:42Z
control_plane_root: /home/iiyatu/projects/python/memoryOS
worktree: /home/iiyatu/projects/python/memoryOS-memoryos-redis-cache-probe
branch: feat/memoryos-redis-cache-probe
dispatch_base: 4c4712df763c652952a8066060bdb8bb4b37ba0b

## Active Inputs Read

- xmuse/master_state.json feature entry `id == "memoryos-redis-cache-probe"`
- xmuse/prompts/slave_god_prompt.md
- xmuse/contracts/slave_dispatch_template.json
- xmuse/work/features/memoryos-redis-cache-probe/slave_state.json
- xmuse/work/features/memoryos-redis-cache-probe/blueprint.md

## Dispatch State

Master dispatched the lane with a dirty feature worktree. Pre-existing dirty
paths were feature-scoped Redis cache work:

- modified: pyproject.toml
- modified: src/memoryos_lite/config.py
- modified: uv.lock
- untracked: src/memoryos_lite/cache/__init__.py
- untracked: tests/test_config.py
- untracked: tests/test_memory_cache.py
- generated: src/memoryos_lite/cache/__pycache__/__init__.cpython-311.pyc

The prior full-suite result, `596 passed, 1 warning in 1315.81s`, was produced
after those dirty changes existed, so it is not treated as a clean baseline.

## Audit Decision

Adopt and repair the existing feature-scoped changes. They match Phase 0/1 of
the blueprint: Redis is optional via an extra, settings default Redis off, cache
adapters degrade to disabled/error statuses, and tests use fake Redis clients
without requiring a live Redis service.

The missing bounded requirement was deterministic cache key construction that
binds scope, hashed query, session, settings, optional parameters, and a
SQLite-derived watermark string. This turn adds that slice and leaves recall v2
wiring for a later phase.

## Non-Goals For This Turn

- No recall v2 cache lookup/write-through behavior.
- No SQLite store watermark provider beyond accepting a caller-supplied
  watermark string in the key builder.
- No benchmark score claims.
- No Redis requirement for default tests, demos, API startup, or eval commands.
- No change to v3 default, v1 fallback, v2 opt-in recall, kernel default, or
  SQLite authority.
