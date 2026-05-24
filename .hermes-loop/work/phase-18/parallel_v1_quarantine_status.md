# Parallel V1 Quarantine Status

This is an operator status note for GOD during Phase 18.

Parallel work has started in a separate git worktree:

- worktree: `/home/iiyatu/projects/python/memoryOS-v1-quarantine`
- branch: `chore/v1-quarantine`
- base commit: `71a1b6c chore: advance to phase 18`

Scope:

- Quarantine the legacy v1 `ContextBuilder` implementation behind an explicit
  legacy module/boundary.
- Preserve `MEMORYOS_MEMORY_ARCH=v1` fallback behavior.
- Preserve default v3 behavior.
- Preserve `MEMORYOS_AGENT_KERNEL=v1` as opt-in only.

Current quarantine direction:

- Move legacy `ContextBuilder` implementation out of `engine.py` into a
  dedicated legacy context module.
- Keep a compatibility alias for existing tests/callers that still inspect
  `service.context_builder` or import `ContextBuilder`.
- Do not delete v1 behavior.

Governance constraint:

- This parallel branch is not part of Phase 18 promotion evidence.
- Phase 18 should not claim benchmark improvement from this quarantine work.
- Phase 18 eval/ACK evidence should remain tied to its own working tree and
  artifacts, not to `/home/iiyatu/projects/python/memoryOS-v1-quarantine`.
