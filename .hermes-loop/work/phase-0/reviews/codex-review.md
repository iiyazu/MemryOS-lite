# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Verdict

FAIL

Do not create ACK for Phase 0. The benchmark matrix itself is usable, but the phase result/review artifacts fail the God observation requirement for active blueprint/state dirtiness.

## Blocking Finding

1. `result.md` and `execute_review.md` hide the required dirty-state fact for active blueprint/state.

   Evidence:
   - Current `git status --short -- .hermes-loop/state.json .hermes-loop/blueprint.md` shows both files modified.
   - Current `git diff --name-only -- src tests docs benchmarks .hermes-loop/state.json .hermes-loop/blueprint.md` returns `.hermes-loop/blueprint.md` and `.hermes-loop/state.json`.
   - The user/God instruction says these files were already dirty before EXECUTE, and review must not fail solely for that. It also says to fail if Phase 0 result/execute artifacts hide that fact.
   - `.hermes-loop/work/phase-0/result.md` lines 48-59 list the execution write boundary and say `.hermes-loop/state.json` and `.hermes-loop/blueprint.md` were not modified by execution, but do not disclose that they were already dirty before EXECUTE.
   - `.hermes-loop/work/phase-0/execute_review.md` lines 31-40 similarly says those files were not modified by execution, but does not disclose the pre-existing dirty state.

   Impact:
   - A later ACK would make the write boundary look cleaner than the observed worktree, weakening phase binding and auditability.
   - Because active blueprint/state are governance inputs, this cannot be treated as a cosmetic omission.

   Required repeat condition:
   - Repeat Phase 0 artifact finalization so `result.md` and `execute_review.md` explicitly record that `.hermes-loop/state.json` and `.hermes-loop/blueprint.md` were already dirty before EXECUTE, and distinguish that pre-existing dirtiness from allowed Phase 0 writes.

## Non-Blocking Checks

- Behavioral regression: no `src/`, `tests/`, `docs/`, or benchmark data diff was observed in the current targeted diff; Phase 0 appears no-code from the reviewed worktree.
- Source grounding: `baseline_case_matrix.md` separates `source_hit` from `episode_source_hit_at_10`, `planned_evidence_source_hit_at_5`, source overlap, and projected answer status.
- LoCoMo failures: LoCoMo has its own case table with `conv-26_qa_001` through `conv-26_qa_005`; failures are not hidden behind LongMemEval aggregate counts.
- Prompt-hack / leakage risk: no production, test, docs, or benchmark-data changes were observed in the targeted diff; no expected-answer shortcut was found in the reviewed artifacts.
- Benchmark overfitting: Phase 0 records weak 5-case diagnostics and does not claim retrieval, prompt, composer, or kernel improvement.
- Missing diagnostics: the three `phase0_*.json` reports exist, and sampled rows expose `memory_arch`, `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events`.
- Kernel boundary: default LongMemEval/LoCoMo reports have empty `kernel_trace_events`; the opt-in kernel LoCoMo report has 9 trace events.
- v1 fallback / v3 default / kernel opt-in: reviewed artifacts record focused and full test pass evidence, but this ACK gate remains blocked by the write-boundary artifact issue above.

## Decision

repeat
