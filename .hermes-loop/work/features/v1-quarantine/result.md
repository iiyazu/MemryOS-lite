# feature: v1-quarantine

The v1 quarantine feature is implemented in an isolated worktree:

- worktree: `/home/iiyatu/projects/python/memoryOS-v1-quarantine`
- branch: `chore/v1-quarantine`
- commit: `053281c chore: quarantine v1 context builder`

Implemented boundary:

- `ContextBuilder` implementation moved to `src/memoryos_lite/legacy_context.py`.
- `MemoryOSService.legacy_context_builder` exposes the explicit fallback
  builder.
- `MemoryOSService.context_builder` remains as a compatibility alias.
- `memoryos_lite.engine.ContextBuilder` remains as a compatibility alias.
- Default v3 path is preserved.
- `MEMORYOS_MEMORY_ARCH=v1` fallback is preserved.
- Kernel default remains unchanged.

This feature is ready for master review but is not merged into the main worktree
yet.
