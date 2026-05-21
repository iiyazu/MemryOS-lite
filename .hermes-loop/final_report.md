# Memory v3 Final Report

## Completion

- phase-0: completed, target `legacy-stable`
- phase-1: completed, target `legacy-stable`
- phase-2: completed, target `shadow-read`
- phase-3: completed, target `shadow-write`
- phase-4: completed, target `shadow-write`
- phase-5: completed, target `shadow-read`
- phase-6: completed, target `opt-in-v3`
- phase-7: completed, target `bench-candidate`
- phase-8: completed, target `default-candidate`, decision `defer`

## Current Route

- `Settings.resolved_memory_arch` exposes `v3` as the target architecture.
- `MemoryOSService.build_context()` preserves legacy compatibility unless
  `MEMORYOS_MEMORY_ARCH=v3` is explicitly configured.
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- OpenAI embeddings are opt-in via `MEMORYOS_EMBEDDING_PROVIDER=openai`; default
  `auto` stays offline-safe.

## Status

- SQLite remains the authoritative store.
- v1 ContextBuilder remains the compatibility baseline.
- v3 composer emits layered metadata and diagnostics when explicitly enabled.
- Agent kernel supports approval-gated `archive_write` execution when enabled.
- Legacy adapters are retained; default promotion is deferred.

## Verification

- `uv run ruff check .` -> passed
- targeted regression subset -> `8 passed`
- agent citation regression -> `1 passed, 1 warning`
- `uv run pytest -q` -> `355 passed, 1 warning`

## Next Route Decision

Keep v3 as an explicit bench/opt-in path. Do not promote to default until public
benchmark evidence proves that v3 preserves legacy behavior and improves
diagnostic clarity without source-attribution regressions.
