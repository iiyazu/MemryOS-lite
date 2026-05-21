# phase: phase-8

# Final Plan: Legacy Adapter + Deprecation Decision

## Decision Gate

Use phase-7 evidence to choose one outcome:

- `default`: only if v3 public smoke evidence supports default promotion.
- `defer`: keep v3 opt-in when evidence is insufficient or mixed.
- `deprecate`: only for paths that are no longer active compatibility surfaces.

Expected current outcome: `defer`.

## Tasks

1. Read phase-7 result artifacts and public smoke reports.
2. Update baseline docs to describe the active default / opt-in matrix.
3. Record that v3 is `bench-candidate` but not default unless evidence proves otherwise.
4. Keep legacy v1/v2 adapter docs active and avoid obsolete claims.
5. Run `uv run pytest -q`.
6. Write phase-8 result, review, final ACK, and state transition.
