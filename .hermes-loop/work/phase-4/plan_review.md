# phase: phase-4

# PLAN_SELF_REVIEW: Archive And Passage Scope

Verdict: PASS

Reviewed artifacts, in required order:

- `.hermes-loop/work/phase-4/context_bundle.md`
- `.hermes-loop/work/phase-4/god_dispatch.json`
- `.hermes-loop/work/phase-4/brainstorm.md`
- `.hermes-loop/work/phase-4/spec.md`
- `.hermes-loop/work/phase-4/plan.md`

Context citation: `.hermes-loop/work/phase-4/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Findings

No blocking findings.

The current `brainstorm.md`, `spec.md`, and `plan.md` cite `.hermes-loop/work/phase-4/context_bundle.md` and the active goal. They align with `god_dispatch.json`: replace global archival passage retrieval with scoped archive/passage eligibility in the real v3 composer and public benchmark diagnostics.

The plan rejects the stale broad Archival Memory Store direction. It does not continue the old storage/migration-first plan in stale `plan_final.md`; it keeps work narrowed to eligibility contracts, store helpers, composer wiring, and append-only public benchmark diagnostics.

The plan is TDD-oriented and ordered as RED -> GREEN -> REFACTOR -> Smoke And Milestone -> Review. It requires RED tests before production changes for unattached archive exclusion, archival eligibility diagnostics, store/helper invariants, and public benchmark append-only diagnostics. The v1 isolation test may already pass as a guard, but it is still retained as a focused regression gate.

The plan wires scoped archival eligibility into the real v3 path, not a demo/helper-only path. It explicitly changes `V3ContextComposer._archival_items()` to take the request scope, calls a scoped store helper instead of unscoped global `list_archival_passages()`, and passes diagnostics through `MemoryOSService.build_context()` into `public_benchmarks.py`.

The plan preserves the required compatibility boundaries: explicit v1 fallback remains isolated, v3 remains the default memory architecture, and `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off. It also avoids Letta runtime dependency, Qdrant/new production DB scope, benchmark case-id hacks, expected-answer leaks, and aggregate-only benchmark claims.

The plan keeps LongMemEval and LoCoMo regressions visible. It requires separate milestone reporting, pass-to-fail/fail-to-pass accounting, failure classes, and explicit case-level tracking for the listed LongMemEval and LoCoMo cases from `god_dispatch.json`.

The mandatory verification is realistic and complete for this phase: focused RED/GREEN commands, focused phase suite, `uv run pytest -q`, `uv run ruff check .`, and 30-case full-chain LongMemEval and LoCoMo evals. It also states the allowed blocker fallback: if LLM provider access blocks full-chain judging, record the exact blocker, run deterministic no-LLM fallback smokes, and do not mark the full-chain milestone satisfied.

## Required Fixes

None before execution.

Execution should discard the stale `plan_final.md` content and use a regenerated scoped final plan based on `.hermes-loop/work/phase-4/plan.md`, not the old Archival Memory Store plan.
