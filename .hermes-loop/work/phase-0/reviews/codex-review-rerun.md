# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Verdict

PASS

The previous FAIL review in `.hermes-loop/work/phase-0/reviews/codex-review.md` is superseded by this rerun because `.hermes-loop/work/phase-0/result.md` and `.hermes-loop/work/phase-0/execute_review.md` now disclose the pre-existing dirty governance files separately from Phase 0 execution writes.

## Rerun Findings

- Stale FAIL blocker resolved: `result.md` records that `.hermes-loop/state.json` and `.hermes-loop/blueprint.md` were already dirty before Phase 0 EXECUTE and are not counted as Phase 0 execution writes; `execute_review.md` records the same distinction.
- Active goal and phase binding are preserved in `context_bundle.md`, `god_dispatch.json`, `plan_final.md`, `baseline_case_matrix.md`, `result.md`, and `execute_review.md`.
- Context bundle usage is adequate: reviewed Phase 0 artifacts cite `.hermes-loop/work/phase-0/context_bundle.md`, and the current baseline matrix follows its no-code baseline-freeze scope.
- Anti-demo gate is satisfied for Phase 0: the artifacts do not claim retrieval, context composer, answer prompt, kernel behavior, or full-chain LLM judge improvement; optional 30-case LLM judge is explicitly not claimed.
- v3 default, v1 fallback, and kernel opt-in are recorded and consistent with a direct `Settings` check: default resolves to `memory_arch=v3`, explicit `memoryos_memory_arch="v1"` resolves to `v1`, and default kernel remains `off`.
- Kernel traces are absent in the default LongMemEval and LoCoMo Phase 0 reports and present only in the explicit `MEMORYOS_AGENT_KERNEL=v1` LoCoMo smoke report.
- Source grounding is not collapsed into aggregate `source_hit`: `baseline_case_matrix.md` separates `episode_source_hit_at_10`, `planned_evidence_source_hit_at_5`, source overlap, projected answer status, and taxonomy.
- LoCoMo remains separated from LongMemEval with its own case table and visible failures for `conv-26_qa_001` through `conv-26_qa_005`.
- Benchmark overfitting or leakage was not introduced in the reviewed diff: targeted diff shows no `src/`, `tests/`, `docs/`, or `benchmarks/` changes.
- Missing failing tests are not a blocker for this no-code Phase 0 rerun because the required diagnostics are present in the refreshed reports; the focused and full test results are recorded as passing.
- Stale phase artifacts are corrected in the reviewed Phase 0 result/review files: they now use `# phase: phase-0`, quote the active goal, and no longer present the old Phase 3 result/review content.

## Worktree Notes

- Current targeted diff still shows `.hermes-loop/blueprint.md` and `.hermes-loop/state.json` dirty, but the rerun blocker was disclosure, not cleanliness; that disclosure is now present.
- `.hermes-loop/work/phase-0/review_verdict.json` still contains the stale FAIL verdict and was intentionally not edited in this rerun.
- `.hermes-loop/work/phase-0/ack.json` is absent/deleted in the current worktree and was intentionally not edited in this rerun.

## ACK

ACK is allowed for Phase 0 usable baseline freeze after this rerun review, subject to the orchestrator updating verdict/ACK artifacts in a separate authorized step. This PASS does not authorize default kernel enablement or any behavior optimization claim.
