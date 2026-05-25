# xmuse-core-state-extraction Context Bundle

Feature: `xmuse-core-state-extraction`
Branch: `feat/xmuse-core-state-extraction`
Worktree: `/home/iiyatu/projects/python/memoryOS-xmuse-core-state-extraction`
Recorded: `2026-05-25T04:16:33Z`

## Inputs Read

- `xmuse/prompts/slave_god_prompt.md`
- `xmuse/contracts/slave_dispatch_template.json`
- `xmuse/work/features/xmuse-core-state-extraction/slave_state.json`
- `xmuse/work/features/xmuse-core-state-extraction/blueprint.md`

`xmuse/jobs/xmuse-core-state-extraction.json` was requested by dispatch but is absent in this worktree. The blueprint and slave dispatch contract contain the actionable requirements, so this is recorded as a dispatch artifact gap rather than a product blocker.

## Feature Boundary

This lane is a control-plane migration only. It may modify `src/xmuse_core/**`, `xmuse/hermes_hardening.py`, focused Hermes/xmuse tests, and feature-local artifacts. It must not modify `xmuse/master_state.json`, `xmuse/master_status.*`, `xmuse/approvals/**`, `xmuse/master/features/**`, MemoryOS product code, benchmark data, or another worktree.

## Implementation Shape

- New reusable core package boundary: `src/xmuse_core/`.
- Pure validation constants and `validate_master_state()` live in `xmuse_core.core.schema`.
- Read-only state loading and active controller resolution live in `xmuse_core.core.state`.
- Pure path helpers live in `xmuse_core.core.paths`.
- Pure status/queue projection lives in `xmuse_core.core.status`.
- `xmuse/hermes_hardening.py` remains the runtime compatibility facade.
- Merge gate behavior stays in `xmuse/hermes_hardening.py`; core status accepts an injected validator and blocks merge-requested features when no validator is supplied.

## Compatibility Constraints

- Runtime `xmuse/` remains a non-package directory.
- No `src/xmuse/` package is introduced.
- `classify_feature_reconcile_state()` remains in the shim.
- Default v3 MemoryOS behavior, v1 fallback, and kernel opt-in are not touched.
- Benchmark scores are not used as goals or promotion evidence.
