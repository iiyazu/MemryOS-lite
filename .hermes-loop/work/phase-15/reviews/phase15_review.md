# phase: phase-15

# Phase 15 Review

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle:
`.hermes-loop/work/phase-15/context_bundle.md`

Verdict: FAIL

## Findings

1. Blocking: planner proposals are influenced by eval-only/gold-derived sidecar fields while reporting `gold_fields_used=false`.

   `src/memoryos_lite/public_maintenance_planner.py:55` accepts both `model_visible` and `eval_sidecar`, and `_has_grounding_risk()` at `src/memoryos_lite/public_maintenance_planner.py:92` uses `eval_sidecar.verdict`, `eval_sidecar.judge_status`, and `eval_sidecar.failure_class` to choose a `grounding_risk` proposal instead of an `archive_write` proposal. Those fields are populated from `case_diagnostics` in `src/memoryos_lite/public_benchmarks.py:692`, and `failure_class` is derived from expected-source overlap in `src/memoryos_lite/public_case_diagnostics.py:33` and `src/memoryos_lite/public_case_diagnostics.py:247`. This violates the phase-15 sidecar separation requirement: proposal generation must be based only on model-visible diagnostics, not judge labels or gold-derived failure classes. The current tests at `tests/test_public_benchmarks.py:3527` assert that judge/source-miss labels do not appear in tool args, but they miss that the labels changed the proposal itself while `gold_fields_used` remains false.

   Required repair: make `build_maintenance_artifact()` construct `MaintenanceProposal` from `ModelVisiblePlannerInput` only. Preserve `EvalGoldSidecar` as report-only metadata and do not consult it for `proposal_type`, `tool_name`, `arguments`, `source_refs`, `denial_reason`, ids, or content. Add a failing test that two artifacts with identical `ModelVisiblePlannerInput` and different `EvalGoldSidecar` values produce identical proposals, with `gold_fields_used=false`. Keep judge/failure/movement labels out of executable proposal payloads and out of proposal selection logic.

2. Blocking: selector infrastructure does not fail closed for unavailable selector/LLM failures.

   `ToolSelectionBoundary.resolve()` catches `TimeoutError`, `TypeError`, `ValueError`, and `ValidationError` at `src/memoryos_lite/agent_tool_selection.py:101`, but any other selector failure, such as `RuntimeError`, `ConnectionError`, or provider unavailability, escapes `SimpleAgentStepRunner.run_step()` before `tool_selection_denied` and before trace persistence. The context bundle requires invalid output, unavailable LLM, timeout, missing provenance, and policy denial to fall back or stop without mutation. Timeout is tested, but unavailable selector failure is not.

   Required repair: catch non-cancellation selector exceptions at the K2 boundary and convert them to a fallback/no-op `ToolSelectionResolution` with a durable `tool_selection_denied` payload before policy/execution. Add a focused test with a selector that raises a non-timeout provider/unavailable exception and assert no policy, approval, execution, verification, or memory mutation occurs and that `tool_candidates_generated` then `tool_selection_denied` are persisted.

3. Blocking: non-phase-local Hermes state artifacts are stale/modified in the working tree.

   `.hermes-loop/state.json:3` and `.hermes-loop/state.json:9` are changed to `EXECUTE`, despite phase-15 review being the active handoff and despite the context bundle non-goal to avoid Hermes launcher/reporter/state infrastructure changes except phase-local artifacts. `.hermes-loop/active_job.json:3` is also an untracked root-level artifact for `phase-14` while this review is for `phase-15`. These are stale/non-phase-local state artifacts and should not be part of the phase-15 implementation output.

   Required repair: remove or restore non-phase-local Hermes state artifacts from the implementation diff before ACK. Keep phase-15 evidence under `.hermes-loop/work/phase-15/` only, and let the orchestrator own any legitimate state transition outside this patch.

## Non-Blocking Observations

- K2 is wired into the real `SimpleAgentStepRunner.run_step()` path before policy/execution, and the trace ordering for successful selection is `tool_candidates_generated` then `tool_selected` then `tool_policy_decision`.
- Approval replay is now bound to `tool_call_id` and request fingerprint, and the public opt-in replay path in `src/memoryos_lite/evals.py:781` carries the selected `tool_call_id`.
- `MEMORYOS_MEMORY_ARCH=v3` remains the default, `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback, and `MEMORYOS_AGENT_KERNEL` remains default-off in `src/memoryos_lite/config.py:29`.
- Lane outputs cite the active goal and `context_bundle.md`; no benchmark improvement claim is made from the LoCoMo structural smoke.

## Eval Routing Recommendation

Do not ACK phase-15 yet. Repairs are code-bound and do not require a full milestone LongMemEval plus LoCoMo judge run because default retrieval, context composition, answer projection, judging, and public scoring were not changed. After repair, rerun:

- `uv run pytest tests/test_agent_kernel.py -q`
- `uv run pytest tests/test_public_benchmarks.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- the fixed LoCoMo 5-case no-LLM structural replay if planner report artifacts remain in scope

Milestone full-chain routing is only needed if the repair changes default retrieval, context composer, answer projection, judge behavior, or scoring.
