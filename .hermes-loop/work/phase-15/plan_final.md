# phase: phase-15

# Plan Self-Review Verdict

Verdict: PASS.

This review accepts `.hermes-loop/work/phase-15/spec.md` and `.hermes-loop/work/phase-15/plan.md` for the active goal cited by `.hermes-loop/work/phase-15/context_bundle.md`:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

The plan is phase-bound to phase-15, uses the context bundle and dispatch goal, implements K2 before any planner scope, keeps the v3 kernel opt-in, preserves v3 default and v1 fallback behavior, avoids benchmark score targets, and treats planner/report work as conditional, diagnostic, proposal-only work with eval-gold sidecars.

## Blocking Findings

None.

## Required Execution Basis

Execute lane should use these accepted phase-15 artifacts as the controlling implementation basis:

- `.hermes-loop/work/phase-15/context_bundle.md`;
- `.hermes-loop/work/phase-15/god_dispatch.json`;
- `.hermes-loop/work/phase-15/brainstorm.md`;
- `.hermes-loop/work/phase-15/spec.md`;
- `.hermes-loop/work/phase-15/plan.md`.

The accepted mandatory slice is:

1. Add RED focused K2 tests in `tests/test_agent_kernel.py` before production edits.
2. Add minimal K2 contracts in `src/memoryos_lite/v3_contracts.py`.
3. Add a focused `src/memoryos_lite/agent_tool_selection.py` boundary for deterministic candidates, constrained selection, and fail-closed denial.
4. Wire selection into the real `SimpleAgentStepRunner.run_step()` path before policy, approval, execution, verification, and trace persistence.
5. Bind approval replay to the selected `tool_call_id` and existing request fingerprint.
6. Preserve the public benchmark default-off kernel path and update only the opt-in kernel probe resume path in `src/memoryos_lite/evals.py`.
7. Run the focused K2 and public boundary gates before admitting any planner work.

The accepted conditional planner slice is admitted only after the K2 gate is green:

1. Add RED leakage tests first.
2. Add proposal-only public maintenance planner artifacts with separated `ModelVisiblePlannerInput`, `EvalGoldSidecar`, and `MaintenanceProposal`.
3. Keep expected answers, expected source ids, judge labels, gold-derived failure targets, movement labels, and case-specific repair ids out of executable proposal payloads, source refs, candidate ids, archive ids, and memory contents.
4. Preserve case-level LoCoMo source localization and judged outcome fields; do not aggregate away regressions or source-miss risk.

## Non-Blocking Execution Notes

- Treat `archive_write` as the only Phase 15 selectable write candidate. Do not add `core_memory_append`, `core_memory_replace`, `archive_attach`, `core_promotion_request`, retrieval repair execution, or any other Phase 16 tool surface.
- Keep invalid selector output, unavailable selector behavior, selector timeout, non-candidate ids, missing provenance, duplicate ids, policy denial, and replay mismatch fail-closed without mutation.
- Preserve durable trace ordering: `tool_candidates_generated` and either `tool_selected` or `tool_selection_denied` must occur before `tool_policy_decision` for non-empty tool input.
- Keep no-tool runs backwards-compatible; the accepted plan explicitly allows the existing no-tool trace behavior to remain unchanged.
- Planner artifacts, if implemented, are structural diagnostics only. They are not benchmark promotion evidence and must not be sent to `SimpleAgentStepRunner` as executable requests in phase-15.
- Evaluation routing in `plan.md` is accepted: focused kernel/public tests are mandatory; a fixed LoCoMo diagnostic replay is only required if conditional planner/report artifacts are implemented; full LongMemEval plus LoCoMo milestone evaluation is only required if execution changes default retrieval, context composition, answer projection, judge behavior, or public scoring.
- Completion evidence must not claim benchmark improvement, default kernel enablement, or promotion from this phase.

## Review Checklist Result

- Phase binding: PASS.
- Context bundle use: PASS.
- Anti-demo gate: PASS.
- v1 fallback preserved: PASS.
- v3 default preserved: PASS.
- Kernel remains opt-in: PASS.
- No benchmark score targets: PASS.
- No gold-field leakage into executable artifacts: PASS, with conditional tests required before planner implementation.
- TDD RED->GREEN order: PASS.
- K2 before planner: PASS.
- Review/eval routing: PASS.
- Executable without opening Phase 16 tools: PASS.
