# phase: phase-15

## Basis And Goal

This brainstorm explicitly cites `work/phase-15/context_bundle.md` and follows its active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Read basis:

- `work/phase-15/context_bundle.md` first, as required.
- `work/phase-15/god_dispatch.json`.
- Active blueprint sections: `Context Bundle Requirement`, `Execute Goal Contract`, `Full-Chain LLM Judge Gates`, `Kernel And Eval Boundary`, `Kernel Agent Graduation Blueprint`, `Hybrid Tool Selection Boundary`, `Phase 15`, `Phase 16`, `Phase 17`, and `Phase 18`.
- Current MemoryOS kernel contracts and paths: `src/memoryos_lite/v3_contracts.py`, `src/memoryos_lite/agent_kernel.py`, `src/memoryos_lite/config.py`, `src/memoryos_lite/engine.py`, `src/memoryos_lite/context_composer.py`, `src/memoryos_lite/store.py`, `src/memoryos_lite/evals.py`, `src/memoryos_lite/public_benchmarks.py`, and `src/memoryos_lite/public_case_diagnostics.py`.
- Current focused tests: `tests/test_agent_kernel.py`, `tests/test_public_benchmarks.py`, `tests/test_context_composer.py`, and `tests/test_hermes_hardening.py`.
- Letta reference files listed by the context bundle, used only as design references: block/memory/archive/passage schemas, block/archive/passage managers, tool execution manager, core tool executor, `letta_agent_v3.py`, and context window calculator.

Important existing facts:

- `Settings.memoryos_memory_arch` defaults to `v3`.
- `Settings.memoryos_agent_kernel` defaults to `off`, and `v1` is the only opt-in value.
- `MemoryOSService` constructs `SimpleAgentStepRunner` only when `settings.resolved_agent_kernel == "v1"`.
- Public benchmark code only runs the kernel probe when the kernel is opt-in and memory arch is v3.
- `SimpleAgentStepRunner.run_step()` currently accepts explicit `tool_requests` and sends them directly to policy, approval, execution, verification, tool return, and trace persistence.
- `ToolExecutionRequest` has no `tool_call_id`, `selection_origin`, or `candidate_reason` yet.
- Public case diagnostics contain gold-bearing fields such as `expected_source_ids`, `expected_answer`, verdicts, judge statuses, and failure classes; these must not enter agent-visible selector inputs or executable proposal payloads.

## K2 Hybrid Tool Selection Approaches

### Approach A: Minimal In-Runner K2 Boundary

Add small K2 contracts in `v3_contracts.py`, then wire candidate generation and constrained selection directly inside `SimpleAgentStepRunner.run_step()` before the existing policy loop.

Likely contracts:

- `ToolCandidate`: `tool_call_id`, `tool_name`, `arguments`, `source_refs`, `candidate_reason`, `constraints`, optional `origin_metadata`.
- `ToolSelectionChoice`: candidate `tool_call_id` or explicit no-op, with `selection_origin`.
- Extend `ToolExecutionRequest` with optional `tool_call_id`, `selection_origin`, and `candidate_reason`.

Flow:

```text
run_step(request, tool_requests=None)
-> deterministic candidate generation from provided requests and kernel-visible context
-> trace tool_candidates_generated
-> selector chooses candidate or no-op
-> validate selected id/name/provenance/source requirements
-> trace tool_selected or tool_selection_denied
-> existing policy/approval/execution/verification path
```

For the current public benchmark probe, the explicit `archive_write` request becomes a candidate, not an already-selected executable request. The default selector can be deterministic and pick the only valid candidate. Test selectors can inject invalid, non-candidate, missing-provenance, exception, or no-op behavior.

Tradeoffs:

- Pros: smallest reversible change; proves the real `SimpleAgentStepRunner.run_step()` path; preserves existing public kernel probe while adding candidate/selected trace events; does not open Phase 16 tools.
- Pros: existing policy, approval, replay, verification, store trace, and v3 visibility tests remain the core safety net.
- Cons: selector/router code lives in a growing runner unless kept disciplined; future LLM selector may need extraction later.
- Cons: explicit `tool_requests` remain part of the public API, so tests must prove they are only candidate inputs, not a policy bypass.

### Approach B: Small Helper Module With Router And Selector Protocols

Create a focused helper, for example `agent_tool_selection.py`, with deterministic router, selector protocol, and validation helpers. `SimpleAgentStepRunner` delegates candidate generation/selection to that helper, then continues through policy.

Flow:

```text
SimpleAgentStepRunner.run_step()
-> ToolSelectionRouter.generate_candidates(...)
-> ConstrainedToolSelector.select(...)
-> validate choice against candidates
-> selected ToolExecutionRequest
-> policy/approval/execution/verification
```

Tradeoffs:

- Pros: cleaner boundary; easier to test router and selector validation independently; lines up with the blueprint target `ToolSelectionRouter`.
- Pros: future LLM selector and diagnostic planner can use the same candidate schema without expanding the runner too much.
- Cons: slightly larger surface for Phase 15; a new module can become premature if the only opened candidate is `archive_write`.
- Cons: risk of over-designing registry abstractions before Phase 16 defines graduated tools and service contracts.

### Approach C: Full Tool Registry First

Introduce a registry of all potential maintenance tools, tool descriptions, argument schemas, constraints, policy summaries, selector prompts, and executor bindings, then route K2 through that registry.

Tradeoffs:

- Pros: most Letta-like direction long term; makes selector inputs explicit; could serve Phase 16.
- Cons: too broad for Phase 15. It risks opening `core_memory_append`, `core_memory_replace`, `archive_attach`, or `core_promotion_request` before service contracts and tests exist.
- Cons: larger regression surface for public eval and default behavior.
- Cons: more likely to blur K2 selection with K3 tool-surface work.

## Recommended K2 Path

Recommend Approach B, but with the scope discipline of Approach A.

Implementation should add a tiny selection helper only if it stays focused on:

- deterministic candidates from currently supplied `tool_requests`;
- the single currently supported write candidate, `archive_write`;
- strict candidate-id validation;
- no-op/fail-closed behavior;
- trace payloads containing `selection_origin` and `candidate_reason`;
- preservation of existing policy, approval, execution, verification, and trace persistence.

This is safest and reversible because the new helper can be removed or replaced without changing store schemas or default settings. It proves the real opt-in kernel path and does not require a Letta dependency, broad tool registry, or default public benchmark behavior change.

Minimum RED tests should start with the context bundle’s listed failures:

- candidate trace is generated before selection and before policy;
- selector cannot choose a non-candidate tool;
- invalid selector output falls back to no-op or denial without mutation;
- selected request carries `tool_call_id`, `selection_origin`, and `candidate_reason`;
- public benchmark kernel trace remains default-off;
- opt-in public kernel trace includes candidate/selection events.

The existing `approval_pending` replay tests should be extended so approval metadata binds to `tool_call_id` when present. This matches Letta’s approval binding semantics without copying Letta’s runtime.

## Conditional Planner Proposals Only After K2 Is Testable

Planner work should not start until focused K2 tests pass through the real runner path. If K2 is not testable, the phase should stop at K2 and mark planner scope deferred.

### Planner Approach 1: Report-Only Splitter And Proposal Objects

Add a deterministic diagnostic helper that consumes a public case diagnostic row and returns:

- `model_visible_input`: only retrieved/selected/rendered context ids, answer evidence, v3 diagnostics, component accounting, archival eligibility, source refs, and kernel trace metadata safe for the agent plane.
- `eval_sidecar`: `expected_source_ids`, expected answer, verdict, judge status, failure class, movement status, case id, and overlap fields.
- `proposal`: source-grounded proposal object with `gold_fields_used=false`, or a diagnostic-only denial.

Allowed proposal types should be non-executing:

- `retrieval_repair_note` for retrieval/session localization misses;
- `archive_write` evidence summary only when model-visible evidence is already present;
- `grounding_risk` for judge-pass/source-miss or source-miss-adjacent cases;
- `core_promotion_request` only as pending candidate metadata, not executable core mutation.

Tradeoffs:

- Pros: directly attacks leakage boundary; easy to test with fixture diagnostics; no tool execution.
- Pros: supports LoCoMo case-level analysis without hiding source misses behind aggregate judge pass.
- Cons: does not improve benchmark behavior by itself and must not be presented as improvement.

### Planner Approach 2: Kernel-Candidate Planner

Let the planner emit K2 candidates for the selector, but do not execute them unless explicitly passed through a later approved kernel repair run.

Tradeoffs:

- Pros: closer to the eventual K4/K3 pipeline.
- Cons: easy to accidentally make proposals executable in Phase 15; riskier before Phase 16 tools and service contracts exist.

### Planner Approach 3: Public Benchmark Report Mutation Only

Only add extra fields to public benchmark reports: sidecar split, failure-class proposal labels, and grounding-risk flags.

Tradeoffs:

- Pros: smallest eval/report change.
- Cons: may be too report-only and fail the “benchmark-usable Letta-style agent memory system” direction; could become demo-only if not connected to K2 proposal contracts.

Recommended conditional planner path: Planner Approach 1. It is deterministic, sidecar-oriented, and non-executing. It should be admitted only after K2 has passing focused tests and public kernel default-off behavior is proven.

## Rejected Alternatives

- Enable `MEMORYOS_AGENT_KERNEL=v1` by default: rejected because Phase 15 must preserve kernel opt-in and public benchmark comparability.
- Let public diagnostics directly create `ToolExecutionRequest` objects from failure classes: rejected because it risks executable gold leakage and bypasses K2 candidate validation.
- Add Letta as a runtime dependency: rejected by the context bundle and blueprint; Letta is a reference, not a dependency.
- Open Phase 16 tool surface now: rejected because `core_memory_append`, `core_memory_replace`, `archive_attach`, and `core_promotion_request` need registry, policy, service, verification, trace, and integration tests in Phase 16.
- Treat LoCoMo judge pass as retrieval success: rejected because source-miss judge-pass is explicitly a grounding risk.
- Optimize the implementation to hit benchmark score targets: rejected because Phase 15 is a structural safety and diagnostic-planner phase, not a score-promotion phase.

## Demo-Only Or Partial Completion

This phase would be demo-only or partial if:

- K2 is implemented in a helper or CLI path that is not used by `SimpleAgentStepRunner.run_step()`.
- Candidate/selection traces are returned in memory but not persisted through `store.add_trace`.
- Invalid selector output silently turns into an executable `archive_write`.
- Unknown tools reach `tool_policy_decision` or `tool_executed` as if selected normally.
- Public benchmark traces change when `MEMORYOS_AGENT_KERNEL` is still off.
- Planner objects are shown in a report but lack leakage tests, sidecar split, or `gold_fields_used=false`.
- Planner proposals can execute before K2 fail-closed tests pass.
- LoCoMo case-level regressions are hidden behind aggregate pass counts.
- Same-slice repair writes are used as promotion evidence.

## Pass-To-Fail Risks

- Approval replay may become weaker if `tool_call_id` is added but not bound into pending approval metadata and replay validation.
- A deterministic fallback could accidentally pick the first candidate instead of no-op after invalid selector output.
- Candidate generation could copy explicit `approval_id` into a selected request and bypass pending approval binding.
- Public benchmark opt-in kernel trace assertions will need expected event order updates; default-off tests must remain unchanged.
- `ToolExecutionRequest` schema changes could affect existing tests or serialization if optional fields are not backward-compatible.
- Adding planner fields to reports could change report consumers or Hermes hardening summaries if existing keys are renamed instead of extended.
- A diagnostic planner could overfit LoCoMo failure classes and obscure LongMemEval regression checks if report governance does not separate benchmarks.

## Benchmark Leakage Risks

Fields that must remain eval-only sidecar data:

- `expected_answer`;
- `expected_source_ids`;
- expected/retrieved overlap ids;
- judge labels and reasoning used as final outcome;
- gold-derived `failure_class` when it depends on expected-source overlap;
- movement status against a baseline;
- case-specific repair ids or target ids derived from gold evidence.

Fields that may be model-visible only when they come from real MemoryOS outputs:

- v3 context items and source refs;
- v3 diagnostics and component accounting;
- final context trace source ids;
- rendered answer evidence and cited source ids;
- retrieval candidate ids generated by MemoryOS, not the expected overlap;
- kernel trace events that contain no benchmark gold.

Every executable proposal must assert `gold_fields_used=false`. If a planner cannot produce a source-grounded proposal without eval-only fields, it should emit a diagnostic-only denial instead of a candidate.

## Invariants To Preserve

- `MEMORYOS_MEMORY_ARCH=v3` remains the default.
- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and is not enabled by default.
- SQLite remains the authoritative store; filesystem traces are debug mirrors.
- Qdrant remains optional.
- No Letta runtime dependency is added.
- Public benchmark default path remains maintenance-write-free and kernel-trace-free.
- No benchmark improvement is claimed from this phase.

## Verification Shape

Focused K2 gate:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Public kernel boundary:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Conditional planner/report gate, only if planner scope is implemented:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --no-llm-answer --no-llm-judge
```

Baseline checks if the execute plan touches shared contracts or public reports:

```bash
uv run pytest -q
uv run ruff check .
```
