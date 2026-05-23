# phase: phase-15

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Decision: reject the blocking scope finding in `task1_spec_review.md` as based on the wrong baseline, then rerun spec review with corrected scope.

Reason:

- `.hermes-loop/state.json` was modified by God before Task 1, as required by the Phase Bootstrap Safety rule after `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` existed. It is not a Task 1 implementer change and must not be reverted.
- `.hermes-loop/active_job.json` was already an untracked runtime/control artifact noted before Phase 15 execution. It is intentionally excluded from commits and not a Task 1 implementer output.
- Task 1's actual implementation scope remains `tests/test_agent_kernel.py` plus `.hermes-loop/work/phase-15/task1_red.md`.

Required action:
Run a corrected spec review that treats controller bootstrap files and preexisting runtime artifacts as baseline/control-plane context, not Task 1 scope drift. Only Task 1 changes should be judged for Task 1 acceptance.
