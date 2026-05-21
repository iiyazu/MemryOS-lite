# phase: phase-5

# Reflection: Memory Lifecycle + Promotion Policy

Phase 5 completed the lifecycle bridge needed before the v3 composer/kernel can
approve memory mutations.

## What Worked

- Promotion stays candidate-first, which preserves `shadow-read` behavior.
- Automatic extraction and consolidation do not directly mutate core memory.
- Core promotion is approval-gated and provenance-heavy.
- Recall-to-archival and archival-to-core paths now have explicit contracts.

## Risks Carried Forward

- Phase 6 must not bypass lifecycle approval when adding kernel tool execution.
- The composer should consume lifecycle diagnostics without treating candidates
  as committed memories.
- Benchmark reporting must keep retrieval, lifecycle, and answer-quality metrics
  separate.

## Next Route

Promote phase 6 to execute lane. Phase 6 should build the opt-in layered
composer first, then wrap it with a minimal durable kernel step instead of
starting with broad tool execution.
