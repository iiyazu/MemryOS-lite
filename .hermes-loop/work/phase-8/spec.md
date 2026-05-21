# phase: phase-8

# Spec: Legacy Adapter + Deprecation Decision

## Goal

Close the first v3 round with a conservative default/defer decision and documentation that matches the actual verified state.

## Scope

- Decide whether v3 becomes default or remains opt-in.
- Document the active adapter boundaries for v1, v2, and v3.
- Update user-facing docs only where they describe current defaults, benchmark readiness, or migration status.

## Functional Requirements

1. Preserve default `v1` behavior unless phase-7 evidence justifies changing it.
2. Keep `MEMORYOS_RECALL_PIPELINE=v2` as the episode-first opt-in path.
3. Keep `MEMORYOS_MEMORY_ARCH=v3` as the layered composer opt-in path if the default is deferred.
4. Document the phase-8 decision in current baseline docs.
5. Avoid claiming MemoryOS Lite is production-ready.

## Acceptance Criteria

- God issues one of: `default`, `defer`, or `deprecate`.
- If `defer`, docs explicitly state v3 remains opt-in and why.
- Adapter docs keep legacy surfaces readable and do not mark active defaults obsolete.
- `uv run pytest -q` remains green after docs/state changes.
