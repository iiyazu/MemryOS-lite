# phase: phase-18

# Execute Goal

/goal Produce phase-18 governance execution artifacts that align with the active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `work/phase-18/context_bundle.md`.
Approved plan: `work/phase-18/plan_final.md`.

## Allowed Real Path

This phase may verify and govern the real MemoryOS v3 public benchmark path only through accepted evidence and phase-local artifacts:

- public eval evidence validity and quarantine decisions;
- source-grounding and case-level diagnostic visibility;
- v3 default, explicit v1 fallback, and opt-in kernel boundary;
- result and review routing under Review Eval Autonomy.

No product behavior changes are allowed in this EXECUTE route.

## Required Artifacts

- `work/phase-18/result.md`
- `work/phase-18/execute_review.md`
- Focused tests: not applicable for this governance-only route because no code, docs, benchmark data, eval reports, or runtime behavior may change. The focused verification artifact is the case-level accepted-evidence matrix plus reviewable read-first coverage.

## Non-Goals And Prohibitions

- Do not run fresh evals, tests, `uv`, `pytest`, `ruff`, or public benchmark commands.
- Do not edit `src/`, `tests/`, `docs/`, benchmark data, eval reports, `state.json`, or `blueprint.md`.
- Do not add demo-only stubs, prompt-only architecture claims, benchmark case-id hacks, expected-answer leaks, or expected-source leaks.
- Do not enable the v3 kernel by default or treat opt-in kernel traces as default v3 promotion evidence.
- Do not use same-slice repair smoke as promotion evidence.
- Do not claim global or chain-level improvement from LongMemEval-only evidence, LoCoMo-only evidence, or aggregate pass rate.

## Repair Boundary

Max repair cycles: 1.

Benchmark scores are diagnostic evidence only, not goal constraints. If review finds invalid evidence, hidden regression classes, leakage risk, or unsupported promotion language, classify the issue as `repair`, `repeat_phase`, `god_adjust`, or `hold`; do not loop on score improvement.
