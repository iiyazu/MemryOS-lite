# phase: phase-8

# Plan: Legacy Adapter + Deprecation Decision

## TDD / Verification Order

1. Inspect phase-7 reports and baseline docs.
2. Make the default/defer/deprecate decision.
3. Update docs to match the decision.
4. Verify docs do not contradict feature flags.
5. Run `uv run pytest -q`.

## Proposed Files

- `README.md`
- `docs/source-guide.md`
- `docs/store-interface.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`
- `.hermes-loop/work/phase-8/result.md`
- `.hermes-loop/work/phase-8/execute_review.md`

## Implementation Steps

### 1. Decision check

Read:

- `.memoryos/evals/v3_lme_phase7_smoke_longmemeval.json`
- `.memoryos/evals/v3_locomo_phase7_smoke_locomo.json`
- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`

Expected decision rule:

- choose `default` only if v3 public smoke diagnostics are stable and at least preserve legacy benchmark expectations;
- otherwise choose `defer` and keep v3 opt-in.

### 2. Documentation update

Update docs to state:

- default recall path remains `v1`;
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in;
- `MEMORYOS_MEMORY_ARCH=v3` is bench-candidate / opt-in;
- legacy Page / Item / ContextBuilder paths remain supported adapters during migration.

### 3. Verification

Run:

```bash
uv run pytest -q
```

Expected:

```text
all tests pass
```

### 4. Result artifact

Write `work/phase-8/result.md` with:

- decision;
- evidence summary;
- docs changed;
- verification command and result.
