# phase: phase-4

# Review Failure Discussion

## Root Cause

Phase 4 failed because `archival_eligibility.selected_*` is populated from pre-budget archival search hits, while the final context package can later drop those same archival items during budget selection. This makes diagnostics overstate selected evidence: a passage can be reported as selected even when it is absent from the actual benchmark context.

This is a source-grounding correctness bug, not a blueprint mismatch. The review evidence shows scoped archival retrieval, append-only public diagnostics, v1 isolation, v3 default preservation, and kernel default-off preservation are already mostly in place.

## Scope

The remaining implementation scope is narrow:

- add a RED test for budget-dropped archival hits not appearing as selected;
- make selected archival diagnostics post-budget, or explicitly split pre-budget matches from final selected items;
- keep LongMemEval and LoCoMo case-level results separate, with LoCoMo `0/30` visible;
- regenerate or supersede stale phase-4 review and ACK artifacts only after the diagnostic fix.

No evidence requires changing the phase objective, enabling the v3 kernel by default, rewriting storage, or hiding benchmark regressions.

## Recommendation

Continue fixing phase-4 in `EXECUTE`.

Do not escalate to `GOD_ADJUST` yet: the failure is an implementation/diagnostic consistency bug inside the accepted phase-4 contract. Escalation would be appropriate only if the post-budget diagnostic fix reveals that the current archive eligibility contract cannot represent final context inclusion, or if required full-chain evaluation is blocked by a structural blueprint problem rather than provider/runtime availability.

Do not pause: the blocker has a concrete reproduction and a small required test/fix path.

## Minimum Verification

Before usable ACK:

- focused RED/GREEN test for budget-dropped archival passage selection;
- focused phase-4 suite covering archival store/searcher, context composer, engine, and public benchmarks;
- `uv run pytest -q`;
- `uv run ruff check .`;
- full-chain LongMemEval 30 and LoCoMo 30 when provider access is available, or deterministic no-LLM fallback with the provider blocker recorded and no full-chain success claim.

