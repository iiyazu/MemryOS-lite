# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Verdict

PASS

The plan is approved for Phase 0 execution. It is bound to `.hermes-loop/work/phase-0/context_bundle.md`, matches the active `GOD_DISPATCH` phase binding, and keeps Phase 0 as a baseline freeze and case harness rather than a behavior-optimization phase.

## Review Checks

| Check | Verdict | Evidence |
|---|---|---|
| Active goal | PASS | `plan.md` quotes the active goal exactly near the top and requires the execute artifacts to quote it exactly. |
| Anti-demo gate | PASS | The plan rejects aggregate-only summaries, requires stable per-case rows, separates LongMemEval and LoCoMo, and forces `repeat` or `adjust` for missing reports, missing taxonomy, failed checks, or hidden diagnostic gaps. |
| v1 fallback | PASS | The plan requires explicit verification that `MEMORYOS_MEMORY_ARCH=v1` fallback remains available and forces non-ACK if it is not verified. |
| v3 default | PASS | The plan uses `MEMORYOS_MEMORY_ARCH=v3` for v3 public smoke and requires default checks in `baseline_case_matrix.md` and `result.md`. |
| Kernel opt-in | PASS | Kernel smoke is run only with `MEMORYOS_AGENT_KERNEL=v1`; the plan requires traces to be absent by default and present only under explicit opt-in. |
| Benchmark overfitting | PASS | The plan forbids case-id hacks, expected-answer leaks, behavior optimization, and claims of benchmark improvement from 5-case smoke. It keeps old RED evidence visible as prior evidence when refreshed results differ. |
| Context bundle usage | PASS | The plan cites the context bundle, requires re-reading it at execution start, and requires `baseline_case_matrix.md`, `result.md`, and `execute_review.md` to cite it. |
| Phase binding | PASS | The plan is for `phase-0`, uses the Phase 0 context and dispatch, and does not promote state from plan text alone. |
| Allowed write scope | PASS | The plan limits normal execute writes to phase-local evidence artifacts and generated eval reports. The only test-write branch is explicitly gated on missing required diagnostics and stops with `adjust` unless later implementation is authorized. It forbids `src/`, `docs/`, `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, review verdict, and ACK changes during normal execution. |

## Non-Blocking Execution Cautions

- If the diagnostic-gap branch is reached, execution must stop at a focused failing test plus `adjust`; production implementation is not authorized by this plan.
- Existing worktree changes to `.hermes-loop/state.json` or `.hermes-loop/blueprint.md` must remain untouched and must not be attributed to Phase 0 execution.
- Optional 30-case/full-chain LLM judge absence must be recorded as a blocker for full-chain milestone claims, not converted into usable ACK evidence.

## Needed Revisions

None.
