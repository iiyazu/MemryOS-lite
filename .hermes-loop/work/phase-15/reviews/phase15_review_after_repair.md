# phase: phase-15

## Findings

Blocking findings: none.

The repaired planner sidecar finding is closed. `build_maintenance_artifact()` now constructs `MaintenanceProposal` from `ModelVisiblePlannerInput` fields only: source ids come from `_model_visible_source_ids(model_visible)`, grounding risk checks call `_has_grounding_risk(model_visible)`, and the archive-write payload uses `model_visible.rendered_answer`, `model_visible.question`, `model_visible.citation_contract_status`, and model-visible source ids only (`src/memoryos_lite/public_maintenance_planner.py:55`, `src/memoryos_lite/public_maintenance_planner.py:59`, `src/memoryos_lite/public_maintenance_planner.py:65`, `src/memoryos_lite/public_maintenance_planner.py:71`). `eval_sidecar` is attached only to the returned artifact and is not consulted for proposal type, tool name, arguments, source refs, denial reason, ids, or content (`src/memoryos_lite/public_maintenance_planner.py:85`). The invariance test builds two artifacts with identical model-visible input and different sidecar verdict/judge/failure/movement values, then asserts proposal equality and no gold strings in arguments (`tests/test_public_benchmarks.py:3527`, `tests/test_public_benchmarks.py:3531`, `tests/test_public_benchmarks.py:3540`, `tests/test_public_benchmarks.py:3552`, `tests/test_public_benchmarks.py:3557`).

The repaired selector/provider unavailable finding is closed. `ToolSelectionBoundary.resolve()` now converts non-timeout selector exceptions into `_fallback_denial()` with reason `selector unavailable: ...` (`src/memoryos_lite/agent_tool_selection.py:101`, `src/memoryos_lite/agent_tool_selection.py:116`, `src/memoryos_lite/agent_tool_selection.py:267`). The runner persists `tool_candidates_generated` and `tool_selection_denied` before the selected-request loop, and policy is reached only for `selected_requests` (`src/memoryos_lite/agent_kernel.py:262`, `src/memoryos_lite/agent_kernel.py:281`, `src/memoryos_lite/agent_kernel.py:304`, `src/memoryos_lite/agent_kernel.py:323`). The new unavailable-provider test raises `RuntimeError`, asserts durable `tool_selection_denied`, and asserts no policy, approval, execution, tool message, or archival mutation (`tests/test_agent_kernel.py:123`, `tests/test_agent_kernel.py:332`, `tests/test_agent_kernel.py:342`, `tests/test_agent_kernel.py:348`, `tests/test_agent_kernel.py:351`, `tests/test_agent_kernel.py:354`).

The Hermes state rejection is sound. The controller bootstrap rule says that when `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` already exist for the execute lane phase, the controller must immediately promote to `EXECUTE` and write `phase_status.md` (`.hermes-loop/god_loop_prompt.md:486`, `.hermes-loop/god_loop_prompt.md:492`, `.hermes-loop/god_loop_prompt.md:504`). The recorded rejection matches that rule and treats `.hermes-loop/active_job.json` as an untracked runtime artifact outside implementation scope (`.hermes-loop/work/phase-15/review_verdict.json:21`, `.hermes-loop/work/phase-15/review_verdict.json:26`). Do not require reverting `.hermes-loop/state.json` for this repair review.

## Verdict

PASS.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle:
`.hermes-loop/work/phase-15/context_bundle.md`

## Eval Routing Decision

Recommend smoke routing, not milestone full-chain LongMemEval plus LoCoMo. The repair touched the opt-in kernel selection boundary and additive planner/report artifacts; default retrieval, context composition, answer projection, judge behavior, and public scoring were not broadened in this repair. The fixed no-LLM LoCoMo structural replay recorded in `result.md` is sufficient for this planner/report repair loop.

## Required Repairs

None. Proceed to ACK if the controller accepts the existing execute evidence. I did not rerun tests in this read-only review lane; this review is based on the requested artifact order and static diff inspection.
