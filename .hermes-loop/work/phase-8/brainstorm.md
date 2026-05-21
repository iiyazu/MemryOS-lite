# phase: phase-8

# Brainstorm: Legacy Adapter + Deprecation Decision

## Inputs

- Target state: `default-candidate` or remain `opt-in-v3`
- Research file: `work/phase-8/research.md`
- Current baseline constraint: v1 remains default unless Review and God explicitly approve a default switch.
- Phase-7 evidence path: hard eval plus v3 public LongMemEval / LoCoMo smoke reports.

## Options

### Option A: Promote v3 to default

Switch `MEMORYOS_MEMORY_ARCH` default to `v3`, update docs, and mark v1/v2 as legacy adapters.

Risk: too aggressive. v3 public smoke still needs benchmark proof that recall / archival / core diagnostics are stable, and the current system has no separate production backend.

### Option B: Defer default and keep v3 opt-in

Keep default `v1`, preserve v2 recall opt-in, document v3 as `bench-candidate`, and record why default promotion is deferred.

Risk: less exciting, but it preserves existing benchmark compatibility and avoids overclaiming production readiness.

### Option C: Deprecate legacy paths without default switch

Keep v3 opt-in, but mark `ContextBuilder` / Page / Item routes obsolete now.

Risk: inconsistent. If v3 is not default-ready, legacy paths are still active compatibility surfaces and should not be prematurely deprecated.

## Recommendation

Use Option B.

Phase-8 should issue a clear defer/default decision, keep v3 opt-in unless phase-7 public evidence is strong enough to justify default promotion, and update docs to distinguish:

- current default path
- v2 recall opt-in
- v3 bench-candidate path
- legacy adapter surfaces that remain intentionally supported
