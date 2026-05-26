# MemoryOS Redis Cache Probe Rework Plan

feature_id: memoryos-redis-cache-probe
updated_at: 2026-05-25T08:10:19Z
branch: feat/memoryos-redis-cache-probe
worktree: /home/iiyatu/projects/python/memoryOS-memoryos-redis-cache-probe

## Goal

Repair the Master rework blocker: integrated `uv run pytest -q` failed/stalled in public benchmark tests because the test path forced FastEmbed and attempted Hugging Face model access when the model was unavailable.

## Tasks

- [x] Reproduce the narrow public benchmark failure path.
- [x] Add RED coverage for FastEmbed construction failure during `MemoryOSService` startup.
- [x] Implement no-embedding fallback when optional FastEmbed provider construction/import fails.
- [x] Keep test runs deterministic by forcing `HF_HUB_OFFLINE=1` inside pytest.
- [x] Preserve the prior Redis cache probe implementation and default-off cache behavior.
- [x] Run focused public benchmark, Redis cache, engine, lint, scoped mypy, and full pytest verification.
- [x] Commit repair changes on `feat/memoryos-redis-cache-probe`.
- [x] Refresh feature-local result, review, verdict, ACK, and slave state artifacts.

## Non-Goals

- No Redis authority change.
- No benchmark score target or improvement claim.
- No Master-owned artifact writes.
- No merge or approval request.
