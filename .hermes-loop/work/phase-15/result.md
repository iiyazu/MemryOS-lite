# phase: phase-15

# Phase 15 Result

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle:
`work/phase-15/context_bundle.md`

## Implemented Scope

Phase 15 implemented the K2 hybrid tool-selection boundary in the real opt-in kernel path and then admitted the conditional public maintenance planner sidecar/report slice after the K2 gate was green.

Real chain components:

- `kernel_loop`: changed. `SimpleAgentStepRunner.run_step()` now resolves supplied tool requests through a K2 selection boundary before policy, approval, execution, verification, and trace persistence.
- `public_eval`: changed. The opt-in kernel public probe carries `tool_call_id` across approval replay, and public reports now include proposal-only maintenance planner artifacts.
- `retrieval`: verified as input to public diagnostics; not changed.
- `context_composer`: verified as input to public diagnostics; not changed.
- `answer_projection`: not changed.
- `ingest` and default store behavior: not changed.

## Code Changes

- Added K2 contracts in `src/memoryos_lite/v3_contracts.py` for tool candidates, selector choices, selection origin, and selected request provenance.
- Added `src/memoryos_lite/agent_tool_selection.py` as the constrained K2 boundary. Phase 15 exposes only `archive_write` candidates and fails closed for unsupported, malformed, duplicate, or non-candidate selections.
- Updated `src/memoryos_lite/agent_kernel.py` so non-empty tool requests pass through K2 before policy. It persists `tool_candidates_generated`, `tool_selected`, and `tool_selection_denied`, and binds approval replay to `tool_call_id` plus the request fingerprint.
- Updated `src/memoryos_lite/evals.py` so the public opt-in kernel probe resumes with both `approval_id` and selected `tool_call_id`.
- Added `src/memoryos_lite/public_maintenance_planner.py` with separated `ModelVisiblePlannerInput`, `EvalGoldSidecar`, `MaintenanceProposal`, `MaintenanceArtifact`, and `build_maintenance_artifact()`.
- Updated `src/memoryos_lite/public_benchmarks.py` to attach `model_visible_planner_input`, `eval_gold_sidecar`, and `maintenance_proposal` report fields without changing scoring, judging, retrieval, or answer behavior.

## TDD Evidence

Failing tests added before production changes:

- K2 candidate/selection/fail-closed tests in `tests/test_agent_kernel.py` failed before the kernel was wired through `ToolSelectionBoundary`.
- Public opt-in kernel replay test failed with `approval_replay_denied` before `evals.py` carried `tool_call_id`.
- Planner RED tests in `tests/test_public_benchmarks.py` failed during collection with `ModuleNotFoundError: No module named 'memoryos_lite.public_maintenance_planner'`.

## Verification Commands

- `uv run pytest tests/test_public_benchmarks.py -q` -> `61 passed in 44.15s`
- `uv run pytest tests/test_agent_kernel.py -q` -> `28 passed in 28.48s`
- `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q` -> `2 passed in 0.02s`
- `uv run pytest -q` -> `499 passed, 1 warning in 627.72s`
- `uv run ruff check .` -> `All checks passed!`

## Case-Level Smoke

Command:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --no-llm-answer --no-llm-judge --run-id phase15_locomo5_repair_structural_20260523T211111Z
```

Report:
`.memoryos/evals/phase15_locomo5_repair_structural_20260523T211111Z_locomo.json`

Heartbeat:
`work/phase-15/eval_heartbeat.json`

Case-level structural result:

| case_id | verdict | source_hit | failure_class | judge_status | proposal_type | gold_fields_used | kernel_events |
|---|---|---:|---|---|---|---:|---:|
| `conv-26_qa_001` | fail | true | evidence_hit_answer_fail | not_run | archive_write | false | 0 |
| `conv-26_qa_002` | fail | true | evidence_hit_answer_fail | not_run | archive_write | false | 0 |
| `conv-26_qa_003` | fail | false | retrieval_miss | not_run | archive_write | false | 0 |
| `conv-26_qa_004` | fail | false | retrieval_miss | not_run | archive_write | false | 0 |
| `conv-26_qa_005` | fail | false | retrieval_miss | not_run | archive_write | false | 0 |

Smoke validation:

- All five rows include `model_visible_planner_input`, `eval_gold_sidecar`, and `maintenance_proposal`.
- All proposals are `proposal_only` with `gold_fields_used=false`.
- No row emitted a planner-created `tool_executed` event.
- This was no-LLM projected smoke evidence only. It is not promotion evidence and does not claim benchmark improvement.

## Constraints Check

- `MEMORYOS_MEMORY_ARCH=v3` default preserved.
- Explicit `MEMORYOS_MEMORY_ARCH=v1` fallback preserved.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and was not made default.
- No Letta runtime dependency added.
- No Phase 16 tools added.
- Planner proposals are not executed in Phase 15.
- LoCoMo source localization and outcome remain visible per case.

## Remaining Risk

LoCoMo remains the controlling bottleneck. The structural smoke shows report and proposal boundaries, not quality improvement. Retrieval-miss rows still need later-phase maintenance semantics before any repair or benchmark-quality claim is valid.

## Review Repair

The first review returned FAIL in `work/phase-15/reviews/phase15_review.md`.
God accepted two code findings and rejected the Hermes-state finding with recorded rationale in `work/phase-15/review_verdict.json`.

Repairs applied:

- `build_maintenance_artifact()` now constructs `MaintenanceProposal` shape from `ModelVisiblePlannerInput` only. `EvalGoldSidecar` remains attached for reporting and no longer influences proposal type, arguments, source refs, denial reason, ids, or content.
- `ToolSelectionBoundary` now converts non-cancellation selector/provider exceptions into fallback `tool_selection_denied` before policy/execution.

Repair RED/GREEN:

- `tests/test_public_benchmarks.py::test_planner_eval_sidecar_does_not_change_proposal_shape` failed before repair, then passed.
- `tests/test_agent_kernel.py::test_kernel_selector_unavailable_fails_closed_without_policy_or_mutation` failed before repair, then passed.
