# MemoryOS Redis Cache Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete a bounded Phase 0/1 Redis cache probe slice that is optional, default-off, derived-cache-only, and safe to extend into recall v2 later.

**Architecture:** Add cache settings to `Settings`, a focused cache module with a protocol/no-op/Redis adapter, schema-versioned JSON serialization, and deterministic key construction. Do not wire cache reads into recall or context-building paths in this slice.

**Tech Stack:** Python 3.11+, Pydantic settings, optional `redis` package extra, `pytest`, `ruff`.

---

## Files

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/memoryos_lite/config.py`
- Create/modify: `src/memoryos_lite/cache/__init__.py`
- Create/modify: `tests/test_config.py`
- Create/modify: `tests/test_memory_cache.py`
- Write artifacts under `xmuse/work/features/memoryos-redis-cache-probe/`

## Tasks

- [x] Audit pre-dispatch dirty worktree changes and decide whether to adopt or block.
- [x] Remove generated `src/memoryos_lite/cache/__pycache__` bytecode from the worktree.
- [x] Preserve and verify config tests proving Redis is disabled by default and dependency is optional.
- [x] Preserve and verify cache adapter tests proving no-op fallback, fake Redis round trip, corrupt/stale handling, and client-failure diagnostics.
- [x] Add RED tests for deterministic cache key construction that binds scope, hashed query, session, settings, parameters, and watermark.
- [x] Run the RED test and confirm it fails because `build_cache_key` is missing.
- [x] Implement `build_cache_key()` with raw-query-free SHA-256 key material.
- [x] Run focused cache tests to confirm GREEN.
- [x] Run final focused verification: `uv run pytest tests/test_config.py tests/test_memory_cache.py -q`.
- [x] Run final lint verification: `uv run ruff check src/memoryos_lite/config.py src/memoryos_lite/cache tests/test_config.py tests/test_memory_cache.py`.
- [x] Remove generated `__pycache__` files again after verification.
- [x] Review the diff against invariants: v3 default, v1 fallback, v2 opt-in, kernel default, SQLite authority, Redis default-off.
- [x] Commit the coherent bounded slice on `feat/memoryos-redis-cache-probe`.
- [x] Write result, execute review, review verdict, ACK, and final slave state artifacts.
