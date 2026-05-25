# feature: xmuse-core-state-extraction

/goal: Extract Master state validation, active controller resolution, and status projection into `src/xmuse_core/core` while keeping `xmuse/hermes_hardening.py` as the compatibility facade.

## Real Paths

- Add `src/xmuse_core/__init__.py`.
- Add `src/xmuse_core/core/__init__.py`.
- Add `src/xmuse_core/core/paths.py`.
- Add `src/xmuse_core/core/schema.py`.
- Add `src/xmuse_core/core/state.py`.
- Add `src/xmuse_core/core/status.py`.
- Modify `xmuse/hermes_hardening.py`.
- Add `tests/test_xmuse_core_schema.py`.
- Add `tests/test_xmuse_core_state.py`.
- Add `tests/test_xmuse_core_status.py`.
- Write feature-local artifacts under `xmuse/work/features/xmuse-core-state-extraction/`.

## Required Artifacts

- `api_dependency_map.md`
- `baseline.md`
- `dry_run_validator.md`
- `result.md`
- `execute_review.md`
- `review_verdict.json`
- `ack.json`
- updated `slave_state.json`

## Non-Goals

- Do not modify `xmuse/master_state.json`, `xmuse/master_status.json`, `xmuse/master_status.md`, `xmuse/approvals/**`, or `xmuse/master/features/**`.
- Do not create `xmuse/__init__.py` or `src/xmuse/`.
- Do not modify MemoryOS product code, benchmarks, retrieval, store, eval, or archive logic.
- Do not move `classify_feature_reconcile_state()`.
- Do not introduce external framework, runner, or memory adapter dependencies.
- Do not claim benchmark improvement.

## Prohibitions

- Demo-only wrappers are not sufficient; the real compatibility path must delegate to the new core package.
- Benchmark output is diagnostic only and must not be used as a promotion target.
- Core modules must not write files, call git/subprocess, start jobs, or import MemoryOS product modules.

## Repair Budget

Max repair cycles: 3.
