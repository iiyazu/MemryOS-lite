# phase: phase-15

# Phase 15 Context Bundle

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase 15 target state: `hybrid-selection-and-diagnostic-planner-ready`.

Implement the K2 hybrid tool-selection boundary first. The opt-in kernel must be able to generate deterministic candidate tools, accept only a constrained selector choice from that candidate set or no-op, fail closed on invalid selector output, and trace `selection_origin` plus `candidate_reason`. Only after that is tested may the phase add diagnostic maintenance planner proposals.

Target real chain components:

- `kernel_loop`: changed, opt-in only under `MEMORYOS_AGENT_KERNEL=v1`.
- `public_eval`: changed only for diagnostic planner/report artifacts if K2 is already tested.
- `retrieval`, `context_composer`, and `answer_projection`: verified as inputs to model-visible diagnostics, not changed unless the plan proves a narrow real-path need.
- `ingest` and default store behavior: not a target except for phase-local trace/proposal persistence if required.

## Why This Phase Exists Now

Phase 14 completed K0/K1: one approved `archive_write` now passes through policy, approval replay checks, execution, post-action verification, tool return, and durable trace. That commit is `a381237`, with a later bookkeeping commit `92d9014`.

The next bottleneck is that the kernel still receives `tool_requests` directly. There is no internal candidate router, no constrained selector, no durable candidate/selected trace, and no tested boundary proving an LLM or diagnostic planner cannot invent out-of-scope tools or leak benchmark gold fields into executable memory actions.

## Current Hypothesis And Disproof

Hypothesis:
A small K2 selector layer can make the opt-in kernel safer and more Letta-like without changing default public benchmark behavior. The selector should be deterministic by default, optionally accept an injected selector for tests/future LLM use, and deny/fallback before policy/execution if the selector output is invalid, non-candidate, missing provenance, or depends on eval-only fields.

Disproof evidence:

- any default `MEMORYOS_AGENT_KERNEL` behavior changes;
- unknown/non-candidate tools reach `tool_policy_decision` or `tool_executed`;
- K2 tests pass only through demo-only code not used by `SimpleAgentStepRunner.run_step()`;
- selector/planner inputs include expected answers, `expected_source_ids`, judge labels, gold-derived target ids, or case-specific repair ids;
- planner proposals are executable before K2 candidate/selection tests pass;
- LoCoMo source localization and judge outcome are aggregated or hidden instead of separated.

## Scope

In scope:

- Add minimal K2 contracts in `src/memoryos_lite/v3_contracts.py`.
- Add kernel-internal candidate generation, selector validation, fallback/deny behavior, and trace events in `src/memoryos_lite/agent_kernel.py` or a small focused helper module.
- Extend focused kernel tests in `tests/test_agent_kernel.py`.
- Preserve public benchmark default-off kernel behavior in `tests/test_public_benchmarks.py`.
- If K2 is fully tested, add a diagnostic planner/proposal helper that consumes model-visible public diagnostics and returns proposal objects plus eval-only sidecars without executing tools.
- Add tests proving gold fields stay in sidecars and every executable proposal records `gold_fields_used=false`.

Non-goals:

- Do not enable the v3 kernel by default.
- Do not add Letta as a dependency.
- Do not add broad tool execution or core memory edit tools; those belong to Phase 16.
- Do not run same-slice repair writes as benchmark promotion evidence.
- Do not optimize for benchmark score targets.
- Do not write expected answers or expected source ids into agent-visible memory, tool arguments, source refs, archive ids, passage links, or promotion candidates.
- Do not modify Hermes launcher/reporter/state infrastructure except phase-local artifacts required by this phase.

## State Snapshot

From `.hermes-loop/state.json` after Phase 14 advance:

- `current_state = GOD_DISPATCH`;
- `current_phase_idx = 15`;
- `execute_lane.phase = phase-15`;
- `execute_lane.state = GOD_DISPATCH`;
- `plan_lane.phase = phase-16`;
- `plan_lane.state = PLAN_STORM`;
- `phase-11.status = superseded`;
- `phase-12.status = completed`;
- `phase-13.status = completed`;
- `phase-14.status = completed`;
- `phase-15.status = in_progress`;
- `phase-16.status = pending`;
- `phase-17.status = pending`;
- `phase-18.status = pending`.

Bootstrap hardening check before this bundle:

- action: `dispatch_incomplete`;
- present phase-15 bootstrap files: none;
- missing phase-15 bootstrap files: `context_bundle.md`, `god_dispatch.json`, `plan_final.md`;
- config blueprint headings: OK;
- state phase ordering: OK.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` as the active blueprint. Relevant sections:

- `Context Bundle Requirement`;
- `Execute Goal Contract`;
- `Full-Chain LLM Judge Gates`;
- `Kernel And Eval Boundary`;
- `Kernel Agent Graduation Blueprint`;
- `Hybrid Tool Selection Boundary`;
- `Phase 15 - Hybrid Tool Selection And Diagnostic Maintenance Planner`;
- `Phase 16 - Kernel Maintenance Tool Surface`;
- `Phase 17 - LoCoMo Maintenance Repair Eval`;
- `Phase 18 - Benchmark Governance And Promotion`.

Promoted amendment sources:

- `.hermes-loop/work/phase-8/blueprint_amendment.md`;
- `.hermes-loop/work/phase-8/blueprint_promotion.md`;
- `.hermes-loop/work/phase-14/blueprint_amendment.md`;
- `.hermes-loop/work/phase-14/kernel_graduation_blueprint_amendment.md`;
- `docs/superpowers/specs/2026-05-24-kernel-agent-graduation-blueprint-design.md`.

Phase 15 blueprint requirements:

- kernel enabled implies hybrid selection is on by default inside the kernel;
- deterministic routing declares allowed candidates and constraints;
- the selector may choose only candidates or no-op;
- invalid output, unavailable LLM, timeout, missing provenance, or policy denial falls back or stops without mutation;
- selection traces record `selection_origin` and `candidate_reason`;
- no maintenance planner proposal is executable until K2 is focused-tested.

## Required MemoryOS Read-First Files

- `src/memoryos_lite/v3_contracts.py`;
- `src/memoryos_lite/agent_kernel.py`;
- `src/memoryos_lite/public_benchmarks.py`;
- `src/memoryos_lite/public_case_diagnostics.py`;
- `src/memoryos_lite/config.py`;
- `src/memoryos_lite/engine.py`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/store.py`;
- `tests/test_agent_kernel.py`;
- `tests/test_public_benchmarks.py`;
- `tests/test_context_composer.py`;
- `tests/test_hermes_hardening.py`.

Current code facts:

- `ToolExecutionRequest` has `session_id`, `tool_name`, `arguments`, `source_refs`, and `approval_id`; it does not yet carry `tool_call_id`, `selection_origin`, or `candidate_reason`.
- `ToolExecutionResult` now carries `verification`.
- `SimpleAgentStepRunner.run_step()` iterates supplied `tool_requests`, then policy, approval, execution, verification, and persistence.
- Trace events currently include policy, approval, execution, verification, replay-denial, replay-skip, and step completion, but not `tool_candidates_generated` or `tool_selected`.
- Public benchmark kernel trace is default-off unless `MEMORYOS_AGENT_KERNEL=v1`.
- Public diagnostics include gold-bearing fields such as `expected_source_ids` and `expected_answer`; Phase 15 must split eval-only sidecars from model-visible planner inputs.

## Required Letta Reference Files

Read these as design references only; do not add Letta as a runtime dependency:

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`;
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`;
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`;
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`.

Useful Letta semantics already observed:

- tool execution is routed through `ToolExecutionManager.execute_tool_async()` and executor classes;
- core memory edits call manager/service methods and enforce read-only blocks;
- archival insertion routes through `PassageManager.insert_passage()`;
- approval handling in `letta_agent_v3.py` binds approvals to tool-call ids and step id;
- context-window accounting reports component-level token usage.

## Relevant Prior Artifacts

- `.hermes-loop/work/phase-13/ack.json`;
- `.hermes-loop/work/phase-13/reflect_phase-13.md`;
- `.hermes-loop/work/phase-14/context_bundle.md`;
- `.hermes-loop/work/phase-14/plan_final.md`;
- `.hermes-loop/work/phase-14/result.md`;
- `.hermes-loop/work/phase-14/execute_review.md`;
- `.hermes-loop/work/phase-14/review_verdict.json`;
- `.hermes-loop/work/phase-14/ack.json`;
- `.hermes-loop/work/phase-14/reflect_phase-14.md`.

Phase 14 evidence:

- `uv run pytest tests/test_agent_kernel.py -q` -> `11 passed`;
- public kernel trace focused tests -> `2 passed`;
- `uv run pytest -q` -> `470 passed, 1 warning`;
- `uv run ruff check .` -> passed;
- no LongMemEval/LoCoMo quality claim because default retrieval/answer/judge/scoring did not change.

Last case-level evidence before Phase 15:

- Phase 13 LME 5-case full-chain LLM judge smoke: `5/5`, source hit `5/5`.
- Phase 13 LoCoMo 5-case full-chain LLM judge smoke: `4/5`, source hit `2/5`.
- LoCoMo remains controlling bottleneck; judge-pass/source-miss cases must be treated as grounding risk, not retrieval success.

Invalid evidence:

- heartbeat retry run ids `phase8_lme50_hb_20260522T160637Z` and `phase8_locomo50_hb_20260522T160637Z` were killed/partial/projected and are invalid for promotion.

## Pass-To-Fail Risks

- K2 selector bypasses policy by producing already-approved requests.
- Invalid selector output silently falls back to `archive_write` and mutates memory.
- Diagnostic planner uses `expected_source_ids` or expected answers in executable payloads.
- Public benchmark default path starts emitting kernel traces when kernel is not enabled.
- K2 trace events are not persisted through the same real kernel/public path.
- Phase accidentally opens Phase 16 tools (`core_memory_append`, `core_memory_replace`, `archive_attach`, `core_promotion_request`) without service contracts.
- LoCoMo failures are hidden behind aggregate pass rate.

## Starting Failing Tests Or Cases

Start with RED tests before production changes:

- `tests/test_agent_kernel.py::test_kernel_generates_candidate_trace_before_selection`;
- `tests/test_agent_kernel.py::test_kernel_denies_selector_non_candidate_without_policy_or_execution`;
- `tests/test_agent_kernel.py::test_kernel_selector_invalid_output_falls_back_to_noop_without_mutation`;
- `tests/test_agent_kernel.py::test_kernel_selected_request_carries_selection_origin_and_candidate_reason`;
- `tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off`;
- if planner scope is reached: tests proving planner model-visible inputs exclude `expected_answer`, `expected_source_ids`, judge labels, gold-derived failure target classes, and case-specific repair ids.

Concrete failing benchmark cases should be selected from the fixed 5/10-case LoCoMo diagnostic replay only after K2 tests pass. They are diagnostic inputs, not score targets.

## Expected Verification Commands

Focused first:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Planner/public diagnostics, if planner scope is implemented:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

Baseline checks unless the plan narrows them with evidence:

```bash
uv run pytest -q
uv run ruff check .
```

Milestone gate:
Phase 15 may require a 5/10-case LoCoMo diagnostic replay for planner artifacts. It should not require 30-case full-chain promotion unless it changes default retrieval, context, answer, judge, or public scoring paths. If review chooses a milestone gate, LongMemEval and LoCoMo must both run in parallel with LLM answer/judge enabled.

## Anti-Demo Usable ACK Criteria

Phase 15 is usable only if:

- K2 selection is wired into the real `SimpleAgentStepRunner.run_step()` path when the kernel is opt-in enabled;
- default kernel-off public benchmark reports remain unchanged;
- candidate and selected trace events are durable and visible in opt-in public kernel traces when applicable;
- non-candidate, invalid, timeout, missing-provenance, unavailable selector, and policy-denied paths fail closed without mutation;
- any planner proposals are deterministic, source-grounded, not executable before K2, and split eval-only sidecars from executable payloads;
- tests cover the fail-closed and leakage boundaries;
- review verdict and ACK reference this context bundle and the active goal;
- no benchmark improvement is claimed without same-case LoCoMo evidence.

## Hard Constraints

- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and must not become default.
- SQLite remains authoritative store.
- Qdrant remains optional only.
- No Letta runtime dependency.
- No case-id hacks, expected-answer leaks, expected-source leaks, or gold-derived executable memory writes.
- No demo-only phase completion.
