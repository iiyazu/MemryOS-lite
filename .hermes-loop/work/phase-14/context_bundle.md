# phase: phase-14

# Phase 14 Context Bundle

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase: `phase-14`.

Name: Opt-In Kernel Memory Action Verification.

Target state: `agent-loop-memory-usable`.

Target chain components:

- `kernel_loop`: opt-in memory action loop, policy decision, approval, execution, replay integrity, post-action verification, and trace durability.
- `store`: durable writes caused by kernel memory actions, including archival memory history and archive attachment state.
- `retrieval`: follow-up verification that a successful memory action is visible through the intended retrieval/context path.
- `context_composer`: v3 selected evidence and component trace visibility after a memory action.
- `answer_projection`: not applicable unless the public answer path changes.
- `public_eval`: verify default-off behavior; do not use kernel trace as benchmark improvement evidence.

## Why This Phase Exists Now

`state.json` currently has phase 14 in `GOD_DISPATCH`.
Phase 13 completed the core-memory lifecycle: source-backed promotions update
live core blocks in place, preserve history, enforce read-only boundaries, and
render through the v3 composer. Phase 12 already proved the archival/RAG bridge
for same-session attached archive passages. Phase 13 reflection added a narrow
root eval-isolation amendment for future parallel benchmark gates.

The opt-in kernel path still has a narrower contract than the Letta-style loop:
it can request approval, resume approval, run `archive_write`, and persist tool
traces, but the action is not yet the main audited cycle
`observe -> choose action -> request tool -> policy -> approve -> execute -> verify -> trace`.

This phase should make the opt-in kernel loop auditable without turning it on by
default and without claiming benchmark quality movement from trace-only work.

## Current Hypothesis

The smallest credible phase-14 implementation is to keep `archive_write` as the
only supported kernel tool unless RED evidence proves a broader tool surface is
needed, then add an explicit post-action verification step that proves a
successful memory action became visible in the real store and v3 context path.

Expected loop contract:

```text
observe v3 context
-> request memory action
-> policy decision
-> approval pending or resumed approval
-> execute supported tool
-> verify durable memory/context visibility
-> trace verification result
```

Disconfirming evidence:

- current `SimpleAgentStepRunner` already emits durable verification traces for
  successful memory actions;
- `archive_write` already proves same-session store and v3-context visibility as
  part of the kernel step, not only in a later focused test;
- unsupported tools are already denied, replay-safe, and explicitly audited for
  all memory action names this phase would expose;
- adding `core_memory_*` tools is necessary to satisfy the phase goal and can be
  done without bypassing the phase-13 lifecycle gates.

## Scope

Allowed:

- add phase-14 RED tests before production changes;
- verify or change `SimpleAgentStepRunner`, `SimpleToolExecutionManager`, and
  related v3 contracts for post-action verification and trace payloads;
- keep `archive_write` as the only supported kernel tool unless RED evidence
  shows the phase is otherwise demo-only;
- test unsupported core-memory tool names as explicit denials if they remain
  outside the phase;
- verify that successful `archive_write` writes archival memory, creates or
  preserves the same-session archive attachment, and becomes selectable through
  the v3 composer;
- update the public kernel opt-in trace smoke only if the trace shape changes.

Non-goals:

- do not enable `MEMORYOS_AGENT_KERNEL=v1` by default;
- do not change benchmark scoring, judge semantics, or answer projection;
- do not silently fallback unsupported tools to another action;
- do not broaden into a full Letta fork or add Letta as a runtime dependency;
- do not claim LongMemEval or LoCoMo improvement from kernel trace visibility;
- do not re-open phase-11 LoCoMo retrieval work unless the kernel phase changes
  default public context behavior.

## State Snapshot

From `.hermes-loop/state.json` at this execute refresh:

- `current_state = EXECUTE`;
- `current_phase_idx = 14`;
- `execute_lane.phase = phase-14`;
- `execute_lane.state = EXECUTE`;
- `plan_lane.phase = phase-15`;
- `plan_lane.state = PLAN_STORM`;
- `research_lane.phases = []`;
- `review_lane.active = false`;
- `phase-11.status = superseded`;
- `phase-12.status = completed`;
- `phase-13.status = completed`;
- `phase-14.status = in_progress`;
- `phase-15.status = pending`;
- `phase-16.status = pending`;
- `phase-17.status = pending`;
- `phase-18.status = pending`.

Controller refresh note, `2026-05-24T00:00:00+08:00`:

- `work/phase-14/god_dispatch.json`, `brainstorm.md`, `spec.md`, `plan.md`,
  `plan_review.md`, `plan_final.md`, `research.md`, and phase-14 amendment
  drafts already exist and are phase-bound to `phase-14`;
- `work/phase-14/ack.json`, `review_verdict.json`, and `result.md` are still
  absent, so no stale completion artifact was consumed;
- root state now says `current_state = EXECUTE`; phase bootstrap safety is
  satisfied because `context_bundle.md`, `god_dispatch.json`, and
  `plan_final.md` all exist for `phase-14`;
- this refresh confirmed current `src/memoryos_lite/agent_kernel.py` and
  `tests/test_agent_kernel.py` still have the minimal durable sequence around
  approved `archive_write`:
  `approval_pending -> approval_granted -> tool_executed`, with no
  `tool_verified` trace event or test expectation yet;
- Letta reference refresh confirmed the relevant boundary remains tool-call
  identity, approval response validation, structured tool returns, and manager
  routed memory mutation; MemoryOS should borrow that contract without adding
  Letta as a dependency.

Earlier `GOD_DISPATCH` records remain historical only. The active controller
state is now `EXECUTE`, so phase-14 may proceed with TDD implementation from
`plan_final.md`.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` as the active blueprint. Relevant sections:

- `Current Baseline And Phase 8 Evidence`;
- `Hard Constraints`;
- `Letta Reference Policy`;
- `Context Bundle Requirement`;
- `Full-Chain LLM Judge Gates`;
- `Phase 13 - Core Memory Lifecycle`;
- `Phase 14 - Opt-In Kernel Memory Action Verification`;
- `Phase 15 - Hybrid Tool Selection And Diagnostic Maintenance Planner`;
- `Phase 16 - Kernel Maintenance Tool Surface`;
- `Phase 17 - LoCoMo Maintenance Repair Eval`;
- `Phase 18 - Benchmark Governance And Promotion`.

Promoted amendment source:

- `.hermes-loop/work/phase-8/blueprint_amendment.md`;
- `.hermes-loop/work/phase-8/blueprint_promotion.md`;
- `.hermes-loop/work/phase-14/blueprint_amendment.md`;
- `.hermes-loop/work/phase-14/kernel_graduation_blueprint_amendment.md`.

The phase-8 amendment is already promoted into the root blueprint. It remains
the rationale for conservative benchmark language, visible pass-to-fail lists,
and LoCoMo-first caution.

## Required Read-First Files

MemoryOS:

- `.hermes-loop/work/current_goal.md`;
- `.hermes-loop/state.json`;
- `.hermes-loop/blueprint.md`;
- `.hermes-loop/work/phase-13/result.md`;
- `.hermes-loop/work/phase-13/ack.json`;
- `.hermes-loop/work/phase-13/review_verdict.json`;
- `.hermes-loop/work/phase-13/reflect_phase-13.md`;
- `.hermes-loop/work/phase-11/case_matrix.md`;
- `.hermes-loop/work/phase-11/review_verdict.json`;
- `docs/known-issues.md`;
- `docs/public-benchmark-diagnosis.md`;
- `docs/agentic-memory-roadmap-zh.md`;
- `src/memoryos_lite/agent_kernel.py`;
- `src/memoryos_lite/engine.py`;
- `src/memoryos_lite/evals.py`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/core_memory.py`;
- `src/memoryos_lite/memory_lifecycle.py`;
- `src/memoryos_lite/store.py`;
- `src/memoryos_lite/v3_contracts.py`;
- `tests/test_agent_kernel.py`;
- `tests/test_memory_lifecycle.py`;
- `tests/test_context_composer.py`;
- `tests/test_public_benchmarks.py`.

Letta reference files, design-only:

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

Borrow semantics for core memory blocks, archive/passage scope, attached
archives, tool-mediated writes, durable tool results, approval boundaries, and
component accounting. Do not port Letta internals wholesale.

## Relevant Prior Evidence

Phase 13 usable ACK:

- `work/phase-13/context_bundle.md`;
- `work/phase-13/red_tests.md`;
- `work/phase-13/result.md`;
- `work/phase-13/review_verdict.json`;
- `work/phase-13/ack.json`.

Phase 13 proved:

- approved archival-to-core candidates update existing live core blocks in place;
- duplicate live core labels fail closed;
- direct store updates require actor/reason/source refs;
- read-only core blocks reject direct store update and delete attempts;
- v3 composer renders approved core promotion value, provenance, and source refs;
- full suite and ruff passed at phase 13;
- kernel remained opt-in and default public kernel traces stayed empty.

Phase 11 remains the controlling LoCoMo warning:

- LongMemEval 30 full-chain LLM judge: `30 pass / 0 fail`;
- LoCoMo 30 full-chain LLM judge: `20 pass / 10 fail`;
- LoCoMo pass-to-fail: `conv-26_qa_028`;
- source-miss judged-pass risk: `conv-26_qa_005`;
- unchanged LoCoMo failures: `conv-26_qa_003`, `conv-26_qa_004`,
  `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`,
  `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`,
  `conv-26_qa_025`;
- all rows used `memory_arch=v3`;
- kernel traces were empty because the kernel was not enabled.

Phase 13 public smokes were structural and not promotion evidence:

- LongMemEval 5 projected/no-judge v3 smoke: `1 pass / 4 fail`;
- LoCoMo 5 projected/no-judge v3 smoke: `0 pass / 5 fail`;
- kernel trace events remained empty because the default kernel was off.

Phase 13 reflection recorded a narrow root eval-isolation amendment for
parallel public benchmark gates and smokes. Do not use shared default
`.memoryos` stores for parallel promotion evidence.

## Pass-To-Fail Risks

- enabling or testing the kernel in a way that leaks into default public v3 runs;
- treating a successful trace as a benchmark-quality improvement;
- adding broad core-memory tools that bypass phase-13 provenance and read-only
  guards;
- verifying by checking only a tool result payload, not the real store/context
  visibility;
- permitting approval replay with tampered `session_id`, `tool_name`, or
  requested action;
- silently executing unsupported tools or omitting denial traces;
- changing public eval trace shape without updating opt-in tests.

## RED Evidence To Start From

No phase-14 RED has been recorded yet. Start by adding failing tests before
production changes, preferably:

- a successful approved `archive_write` emits a durable post-action verification
  trace after `tool_executed`;
- the verification trace proves store write, same-session archive attachment,
  archival passage selection, and source refs through the v3 composer;
- unsupported memory tool names such as `core_memory_update` or
  `memory_deprecate` are denied explicitly unless the plan intentionally
  implements them;
- approval replay denial still produces no memory write, no tool message, and no
  verification trace;
- public benchmark kernel trace remains empty by default and includes the new
  verification event only when `MEMORYOS_AGENT_KERNEL=v1` is set.

## Expected Verification Commands

Focused phase-local commands for execute-lane later:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

If context/composer verification is changed:

```bash
uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q
```

Baseline checks before review:

```bash
uv run pytest -q
uv run ruff check .
```

Milestone public eval is not automatically required if the phase only changes
the opt-in kernel path and leaves default public v3 context/answer behavior
unchanged. If the plan changes default public context, run LongMemEval and LoCoMo
30-case full-chain LLM judge in parallel with isolated `DATA_DIR` values and
write case-level movement reports.

## Anti-Demo Completion Criteria

Usable phase-14 ACK requires all of the following:

- real opt-in kernel path wired through `MemoryOSService.agent_kernel`;
- approved memory action writes durable memory and a tool result message;
- verification checks the real store/context state, not only a mocked result;
- verification trace is persisted and visible in `kernel_trace_events` when the
  kernel is enabled;
- unsupported tools and replay tampering are denied without side effects;
- focused RED/GREEN tests and full baseline verification are recorded;
- v1 fallback remains explicit, v3 remains default, kernel remains opt-in;
- no benchmark improvement claim is made unless a same-case public eval gate
  actually supports it.

## Default Constraints

- `MEMORYOS_MEMORY_ARCH=v3` remains the default.
- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- SQLite remains the authoritative store.
- Filesystem outputs and benchmark reports are diagnostics, not source of truth.
