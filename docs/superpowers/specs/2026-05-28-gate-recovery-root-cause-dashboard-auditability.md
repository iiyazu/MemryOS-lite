# Gate Failure Root Cause: dashboard-auditability-gate-recovery

> Date: 2026-05-28
> Lane ID: self-evolution-clarification_recovery-res_dbd66a03a8e44848a3a095d887a1317a-graph-v1-dashboard-auditability-gate-recovery
> Evidence bundle: evbundle_6cbce74f29d64d05a5ec28928a268465
> Status: root cause identified, fixes proposed

## Summary

The source `dashboard_auditability` run
`res_0bf7c1d41f554bc287052c6779de8caa-graph-v1` produced three dashboard lanes:

| Lane | Gate result | Merge result |
|---|---:|---|
| `dashboard-event-audit-api-impl` | failed | did not merge |
| `dashboard-state-history-api-impl` | passed | merged |
| `dashboard-execution-lineage-api-impl` | passed | merged |

The failed lane was the first dashboard lane, not the later clarification
recovery lane. The recovery lane was spawned because this source run
terminalized with two merged lanes and one `gate_failed` lane.

The direct gate failure was an import-time error while collecting
`tests/test_xmuse_self_evolution.py`:

```text
ImportError: cannot import name 'EvidenceBundleStore' from
'xmuse_core.structuring.verdict_store'
```

That means pytest did not reach the dashboard API tests. The lane failed
because the gate was run against a transient inconsistent worktree where
`src/xmuse_core/platform/review_plane.py` imported `EvidenceBundleStore`, but
`src/xmuse_core/structuring/verdict_store.py` did not yet expose it.

There is also a real dashboard gate-coverage gap: the dashboard API tests live
under the `xmuse-ui` gate profile, but `xmuse-ui` does not select
`xmuse/dashboard_api.py`. Changes to that file are selected by `xmuse-core`,
whose manifest currently does not run `tests/test_xmuse_dashboard_api.py`.

## Evidence

Primary artifacts:

- `xmuse/logs/gates/self-evolution-dashboard_auditability-res_0bf7c1d41f554bc287052c6779de8caa-graph-v1-dashboard-event-audit-api-impl/report.json`
- `xmuse/logs/gates/self-evolution-dashboard_auditability-res_0bf7c1d41f554bc287052c6779de8caa-graph-v1-dashboard-event-audit-api-impl/xmuse-core__pytest.stdout`
- `xmuse/logs/gates/self-evolution-dashboard_auditability-res_0bf7c1d41f554bc287052c6779de8caa-graph-v1-dashboard-state-history-api-impl/report.json`
- `xmuse/logs/gates/self-evolution-dashboard_auditability-res_0bf7c1d41f554bc287052c6779de8caa-graph-v1-dashboard-execution-lineage-api-impl/report.json`
- `xmuse/logs/platform_runner_nobash_20260528_182504.log`
- `xmuse/logs/platform_runner_conc6_20260528_191336.log`
- `xmuse/logs/self_evolution/checkpoint_loop.log`

The failed report says:

- `feature_id`: `...dashboard-event-audit-api-impl`
- `passed`: `false`
- `blocking_passed`: `false`
- `profile_ids`: `["xmuse-core"]`
- `resolution_reasons`: `{"xmuse-core": ["explicit_lane_profile"]}`
- blocking command:
  `uv run pytest -q tests/test_xmuse_quality_gate.py ... tests/test_xmuse_self_evolution.py tests/test_xmuse_self_evolution_checkpoint.py`
- command return code: `2`

The stdout file contains the collection error:

```text
ERROR collecting tests/test_xmuse_self_evolution.py
...
src/xmuse_core/platform/review_plane.py:36: in <module>
    from xmuse_core.structuring.verdict_store import ClarificationStore, EvidenceBundleStore, VerdictStore
E   ImportError: cannot import name 'EvidenceBundleStore' from 'xmuse_core.structuring.verdict_store'
```

The two successful sibling reports both used the same `xmuse-core` profile and
the same pytest command, but returned `0`.

Runner timing confirms the sequence:

- `2026-05-28 19:04:37`: dispatched `dashboard-event-audit-api-impl`
- `2026-05-28 19:13:36`: dispatched `dashboard-state-history-api-impl`
- `2026-05-28 19:13:36`: dispatched `dashboard-execution-lineage-api-impl`
- `2026-05-28 19:18:19`: state-history lane merged
- `2026-05-28 19:21:16`: execution-lineage lane merged
- `2026-05-28 20:13:47`: clarification recovery was spawned from the terminated dashboard run

## Root Cause

The direct root cause was a cross-lane dependency/version skew in the worktree
used by the gate. At gate time:

1. `xmuse-core` ran `tests/test_xmuse_self_evolution.py`.
2. That test imported `xmuse_core.self_evolution`.
3. `xmuse_core.self_evolution.controller` imported
   `xmuse_core.platform.state_normalizer`.
4. Importing `xmuse_core.platform` imported `PlatformOrchestrator`.
5. `PlatformOrchestrator` imported `ReviewPlaneController`.
6. `ReviewPlaneController` imported `EvidenceBundleStore` from
   `xmuse_core.structuring.verdict_store`.
7. `EvidenceBundleStore` was not available in that gate worktree, so collection
   failed with return code `2`.

The current checkout now contains `EvidenceBundleStore` in
`src/xmuse_core/structuring/verdict_store.py`, so the failure was not an
endpoint-specific regression. It was a transient integration mismatch between
review-plane/evidence-bundle code and the structuring store module at the time
the first dashboard lane gated.

## Why Two Later Lanes Merged

`dashboard-state-history-api-impl` and
`dashboard-execution-lineage-api-impl` ran later, after the worktree no longer
had the same import mismatch. Their reports show:

- `profile_ids`: `["xmuse-core"]`
- `resolution_reasons`: `{"xmuse-core": ["explicit_lane_profile"]}`
- the same blocking pytest command as the failed lane
- command return code `0`

The merge log then records both lanes as reviewed worktree changes with no
branch and marks them merged.

Those lanes did not merge because dashboard tests passed under a dashboard
profile. They merged because the selected `xmuse-core` gate passed.

## Contributing Coverage Gap

The dashboard gate profile is not wired to the primary dashboard API file.

`xmuse/gate_profiles.json` defines `xmuse-ui` with:

```json
"diff_selectors": [
  "xmuse/dashboard/**",
  "xmuse/frontend/**"
]
```

but the changed API module is:

```text
xmuse/dashboard_api.py
```

So a `dashboard_api.py` diff does not select `xmuse-ui`, even though that is the
only profile that runs:

```text
tests/test_xmuse_dashboard_api.py
```

Instead, `xmuse/dashboard_api.py` is selected by `xmuse-core` through
`xmuse/**`, and `xmuse-core` does not include
`tests/test_xmuse_dashboard_api.py` in its command args or `test_files`.

This coverage gap did not cause the observed import error, but it did allow the
dashboard endpoint lanes to merge without the endpoint-specific test file being
part of their blocking gate.

## Proposed Fixes

### Fix 1: Make the import contract explicit and gated

Keep `EvidenceBundleStore` available from
`xmuse_core.structuring.verdict_store` because `ReviewPlaneController` imports
it there. Add a narrow regression test that imports the review-plane stack and
asserts the evidence-bundle store symbol is present:

```python
from xmuse_core.structuring.verdict_store import EvidenceBundleStore
from xmuse_core.platform.review_plane import ReviewPlaneController
```

This catches the exact collection failure before an unrelated lane is used as
the canary.

### Fix 2: Route `xmuse/dashboard_api.py` to `xmuse-ui`

Add the root dashboard API file to the UI profile selectors:

```json
"diff_selectors": [
  "xmuse/dashboard_api.py",
  "xmuse/dashboard/**",
  "xmuse/frontend/**"
]
```

This ensures dashboard API diffs select the profile that runs
`tests/test_xmuse_dashboard_api.py`.

### Fix 3: Add dashboard API tests to `xmuse-core` or `strict-product`

Because `xmuse/dashboard_api.py` imports from `xmuse_core`, a core change can
break the dashboard API even when no UI file changes. Add
`tests/test_xmuse_dashboard_api.py` to at least one broad blocking profile that
already covers `xmuse/**` and `src/xmuse_core/**`:

- `xmuse-core`, for direct coverage of xmuse orchestration changes.
- `strict-product`, for catch-all/pre-merge coverage.

The command args and `test_files` manifest should be updated together.

### Fix 4: Record selected profile/test mismatch as a gate warning

When a diff touches a test file that is not included in the selected blocking
profile's command args or manifest, the gate should emit a clear warning or
fail under `unclassified_test_policy = fail`. That would have made the skipped
dashboard test coverage obvious in the first lane.

## Recovery Path

1. Verify the import stack succeeds:

   ```bash
   uv run python -c "from xmuse_core.structuring.verdict_store import EvidenceBundleStore; from xmuse_core.platform.review_plane import ReviewPlaneController; print('ok')"
   ```

2. Verify the selected gate suite no longer collection-errors:

   ```bash
   uv run pytest -q tests/test_xmuse_self_evolution.py tests/test_xmuse_self_evolution_checkpoint.py
   ```

3. Verify dashboard endpoint behavior directly:

   ```bash
   uv run pytest -q tests/test_xmuse_dashboard_api.py
   ```

4. Update `xmuse/gate_profiles.json` so `xmuse/dashboard_api.py` selects
   `xmuse-ui`, and add dashboard tests to a broad blocking profile.

5. Requeue the failed dashboard event-audit work or land an equivalent recovery
   lane after all three checks pass.

## Current Validation Note

Validation on 2026-05-28 confirms the original import failure is no longer
present in the current checkout:

```bash
uv run python -c "from xmuse_core.structuring.verdict_store import EvidenceBundleStore; from xmuse_core.platform.review_plane import ReviewPlaneController; print('ok')"
# ok
```

The dashboard endpoint suite also passes:

```bash
uv run pytest -q tests/test_xmuse_dashboard_api.py
# 84 passed, 7 warnings in 1.66s
```

The self-evolution subset currently fails one different test:

```bash
uv run pytest -q tests/test_xmuse_self_evolution.py tests/test_xmuse_self_evolution_checkpoint.py
# 1 failed, 68 passed in 5.34s
```

The failure is
`test_run_from_stale_evidence_bundle_hydrates_source_lane_signals`, where
`run_from_evidence_bundle()` raises `RuntimeError: source run is not terminal:
running`. This is not the original collection-time `ImportError`; it is a
separate current worktree regression in stale evidence-bundle hydration or
terminal aggregation.

## Acceptance Signal

The recovery is complete when:

- the import check for `EvidenceBundleStore` and `ReviewPlaneController` exits
  `0`;
- `uv run pytest -q tests/test_xmuse_self_evolution.py tests/test_xmuse_self_evolution_checkpoint.py`
  exits `0`;
- `uv run pytest -q tests/test_xmuse_dashboard_api.py` exits `0`;
- `xmuse/dashboard_api.py` selects `xmuse-ui`;
- a broad blocking profile runs `tests/test_xmuse_dashboard_api.py`;
- the dashboard auditability run has no remaining `gate_failed` lineage.
