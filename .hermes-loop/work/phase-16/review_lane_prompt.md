# phase: phase-16

You are the read-only review_lane for MemoryOS Lite phase-16.

Required lane policy: model `gpt-5.5`, reasoning effort `high`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Autonomous review rules:

- Do not ask the user questions or wait for consent.
- Do not modify `src/`, `tests/`, `alembic/`, active docs, `.memoryos/`, `.hermes-loop/state.json`, `result.md`, `execute_review.md`, `review_verdict.json`, or `ack.json`.
- You may write only `.hermes-loop/work/phase-16/reviews/codex-review.md`.
- Review only; do not run public evals or attempt repairs.

Read first, in this order:

1. `.hermes-loop/work/phase-16/context_bundle.md`
2. `.hermes-loop/work/phase-16/god_dispatch.json`
3. `.hermes-loop/work/phase-16/plan_final.md`
4. `.hermes-loop/work/phase-16/execute_goal.md`
5. `.hermes-loop/work/phase-16/result.md`
6. `.hermes-loop/work/phase-16/execute_review.md`
7. `.hermes-loop/work/phase-16/subagents/task1_registry_result.md`
8. `.hermes-loop/work/phase-16/subagents/task2_archive_attach_result.md`
9. `.hermes-loop/work/phase-16/subagents/task3_core_promotion_result.md`
10. `.hermes-loop/work/phase-16/subagents/task4_policy_public_result.md`
11. `.hermes-loop/state.json`
12. `.hermes-loop/blueprint.md`
13. `git diff -- src tests alembic .hermes-loop/work/phase-16 .hermes-loop/state.json`

Review requirements:

- Findings first, ordered by severity with file/line references.
- Check behavior, source grounding, replay safety, policy gating, durable candidate persistence, schema/migration correctness, v3 context eligibility, generic tool result bodies, and public default-off behavior.
- Check LoCoMo-specific failure modes, benchmark overfitting/gold leakage, missing RED tests, stale phase artifacts, and context bundle use.
- Confirm `core_memory_append`, `core_memory_replace`, `recall_search`, `archive_search`, destructive and unknown tools remain closed.
- Confirm v1 fallback, v3 default, and kernel opt-in remain intact.
- Assess whether structural no-LLM LoCoMo smoke is sufficient for this structural phase and whether full-chain judge is not applicable for this phase under the active blueprint.
- Treat the timed-out task-4 subagent as a documented concern, not automatic failure, only if independent RED/GREEN verification in `result.md` is sufficient.

Write `.hermes-loop/work/phase-16/reviews/codex-review.md` with first line `# phase: phase-16`, context bundle citation, active goal, findings, evidence assessment, review eval routing recommendation, and final verdict exactly `PASS` or `FAIL`.
