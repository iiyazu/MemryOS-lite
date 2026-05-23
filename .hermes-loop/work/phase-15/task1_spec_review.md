# phase: phase-15

FAIL

## Blocking Findings

1. Task 1 scope is not clean in the current worktree. `git diff --name-only` shows `.hermes-loop/state.json` modified in addition to `tests/test_agent_kernel.py`, and `git status --short` shows `.hermes-loop/active_job.json` as an untracked non-phase-local artifact. Task 1 was required to stay limited to tests plus the phase-bound artifact; these files are outside that boundary.

## Passing Checks

- `tests/test_agent_kernel.py` is test-only and adds no production code.
- No `src/` files are changed, so there is no production code change, benchmark default path change, or default kernel enablement in the code diff.
- `.hermes-loop/work/phase-15/task1_red.md` is phase-bound, starts with `# phase: phase-15`, records the active goal, and reports the expected RED result: `uv run pytest tests/test_agent_kernel.py -q` exited 2 on `ModuleNotFoundError: No module named 'memoryos_lite.agent_tool_selection'`.
- The added tests cover candidate trace before policy: `test_kernel_generates_candidate_trace_before_selection` expects `tool_candidates_generated` and `tool_selected` before `tool_policy_decision`, and checks `selection_origin`, `candidate_reason`, and generated `tool_call_id`.
- The added tests cover non-candidate denial before policy/execution/mutation: `test_kernel_denies_selector_non_candidate_without_policy_or_execution` injects a non-candidate selector, expects `tool_selection_denied`, excludes policy and execution events, and asserts no archival memory write.
- The added tests cover selector failure fallback/no mutation: `test_kernel_selector_invalid_output_falls_back_to_noop_without_mutation` injects a timeout selector, expects fallback denial, excludes policy, and asserts no archival memory write.
- The added tests cover selected provenance through approval replay: `test_kernel_selected_request_carries_selection_origin_and_candidate_reason` carries the pending `tool_call_id` into replay and expects the replayed `tool_selected` trace to preserve the id, deterministic origin, and candidate reason.
- The added tests cover tampered `tool_call_id` replay denial: `test_kernel_rejects_approval_replay_with_tampered_tool_call_id` expects `approval_replay_denied`, no grant, no execution, no verification, no archival write, and no tool message.
- No benchmark score targets were added in the Task 1 artifact or test diff.

## Required Fixes

1. Remove or otherwise resolve the out-of-scope `.hermes-loop/state.json` modification before accepting Task 1 as scope-clean.
2. Remove or account for the out-of-scope `.hermes-loop/active_job.json` untracked file before accepting Task 1 as scope-clean.
3. Keep the current test-only K2 RED coverage; no production changes are required for Task 1 review.
