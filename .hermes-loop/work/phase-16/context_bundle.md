# phase: phase-16

# Phase 16 Context Bundle

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Every lane must read this file before any other phase-local artifact. Any lane output that ignores this bundle, contradicts it without evidence, or relies on remembered prior chat context is stale.

## Phase Binding

- Execute lane phase: `phase-16`
- State at bootstrap: `.hermes-loop/state.json` has `current_state = GOD_DISPATCH`, `current_phase_idx = 16`, `execute_lane.phase = phase-16`, `execute_lane.state = GOD_DISPATCH`.
- Phase status: `phase-16` is `in_progress`; `phase-17` and `phase-18` are `pending`.
- Ordering check: phases below 16 are completed or explicitly superseded. `phase-11` is superseded by a recorded adjustment. No higher phase is completed.
- Config check: `.hermes-loop/config.json` contains `Phase 16 - Kernel Maintenance Tool Surface`, `Phase 17 - LoCoMo Maintenance Repair Eval`, and `Phase 18 - Benchmark Governance And Promotion`; these headings exist in `.hermes-loop/blueprint.md`.
- Bootstrap safety: `work/phase-16/` was missing at startup, so this controller run may generate missing dispatch/planning artifacts only. Do not implement, test, eval, or modify product code until a later bootstrap observes `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` already present and promotes state to `EXECUTE`.

## Phase Objective

Implement K3 by planning the minimum Letta-style kernel maintenance tool surface needed before Phase 17 can run a LoCoMo maintenance repair smoke. The implementation phase may change only the opt-in v3 kernel/tool/public structural path and must preserve default-off kernel behavior.

Target chain components for the future implementation:

- `kernel_loop`: expand the existing K2 selection and approval path into a registry/policy/service-backed maintenance tool surface.
- `store`: use existing SQLite-backed store APIs through named services; no ad hoc direct write paths for new tools.
- `retrieval`: only for read-only search tools if the final plan opens them; preserve retrieval diagnostics and no gold leakage.
- `context_composer`: verify maintenance writes become visible to v3 only through archive attachment, passage eligibility, and core-memory scope/provenance rules.
- `public_eval`: structural opt-in kernel smoke only; default public reports must remain kernel-off unless `MEMORYOS_AGENT_KERNEL=v1`.
- `answer_projection`: not a Phase 16 target unless review evidence shows a tool surface artifact breaks report projection shape.
- `ingest`: not a Phase 16 target.

## Why Phase 16 Exists Now

Phase 14 completed K0/K1: the opt-in kernel can request approval, resume approval, execute `archive_write`, verify the write, emit durable trace events, and keep the kernel default off.

Phase 15 completed K2: tool requests now pass through `ToolSelectionBoundary` before policy/execution, `tool_call_id` is bound to approval replay, selector failures fail closed, and public benchmark reports include proposal-only maintenance planner artifacts generated from model-visible fields only.

Phase 17 needs kernel-created maintenance artifacts for a LoCoMo repair smoke. Phase 16 must therefore turn the proposal-only surface into a small, auditable, policy-gated, service-backed tool surface without opening unsafe core edits or using benchmark gold.

## Current Hypothesis

A bounded K3 tool surface can make Phase 17 repair smoke meaningful if each opened tool is:

- registered as an explicit candidate type before selection;
- gated by policy and approval where it can mutate memory;
- executed through a named domain service instead of direct ad hoc store writes;
- verified after execution with `tool_verified` evidence;
- visible to v3 only through existing scope/provenance rules;
- replay-safe through `approval_id`, `tool_call_id`, and request fingerprint checks.

Disconfirming evidence:

- any new tool can mutate memory without approval or source refs;
- replay tampering executes or verifies a write;
- `core_memory_append` or `core_memory_replace` becomes executable without a separate safety gate;
- new writes are visible to v3 despite missing archive/core scope eligibility;
- public benchmark reports emit kernel events without `MEMORYOS_AGENT_KERNEL=v1`;
- proposal or tool arguments use expected answers, expected source ids, judge labels, failure classes, or case ids as executable inputs.

## Exact Scope

Plan the implementation around the smallest usable K3 opening:

- preserve existing `archive_write` behavior and migrate it behind an explicit registry/executor/service contract if needed;
- add Level 1 mutating tools only if they are service-backed and approval-gated:
  - `archive_attach`;
  - `core_promotion_request`;
- add Level 2 read-only tools only if they are fail-closed, bounded, and do not create side effects:
  - `recall_search`;
  - `archive_search`;
- keep Level 3 core edit tools closed:
  - `core_memory_append`;
  - `core_memory_replace`;
- destructive delete/deprecate tools remain closed.

The final plan may narrow further if the codebase shape shows Level 1 alone is the only safe usable slice. It must record rejected alternatives in `brainstorm.md` and `plan_review.md`.

## Explicit Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change the default `v3` memory architecture or remove `MEMORYOS_MEMORY_ARCH=v1`.
- Do not claim benchmark-quality improvement from Phase 16.
- Do not run milestone promotion eval for Phase 16; this is a structural kernel/tool phase.
- Do not add Letta as a runtime dependency.
- Do not add a new daemon, scheduler, or external orchestrator.
- Do not add destructive tools.
- Do not let public benchmark gold fields influence tool arguments, source refs, archive ids, passage links, promotion candidates, repair notes, or memory writes.
- Do not make `core_memory_append` or `core_memory_replace` executable in Phase 16 unless a separate safety gate is documented and reviewed; the default safe plan should keep them denied.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` sections:

- `Hard Constraints`
- `Superpowers And Goal Discipline`
- `Completion Levels`
- `Required ACK Evidence`
- `Context Bundle Requirement`
- `Execute Goal Contract`
- `Full-Chain LLM Judge Gates`
- `Kernel And Eval Boundary`
- `Kernel Agent Graduation Blueprint`
- `Required Kernel Data Contracts`
- `Hybrid Tool Selection Boundary`
- `Phase Mapping For Active Loop`
- `Phase 16 - Kernel Maintenance Tool Surface`
- `Phase 17 - LoCoMo Maintenance Repair Eval`

Phase 16 blueprint summary:

- Target state: `kernel-maintenance-tools-usable`.
- Purpose: add the minimum Letta-style maintenance tools for the diagnostic planner while preserving approval, provenance, replay safety, and default-off kernel behavior.
- Allowed Level 1 tools: `archive_write`, `archive_attach`, `core_promotion_request`.
- Allowed Level 2 tools: `recall_search`, `archive_search`.
- Level 3 tools (`core_memory_append`, `core_memory_replace`) require a separate safety gate.
- Required tests include approval/source-ref requirements, unsupported/destructive fail-closed behavior, replay tamper denial, durable history plus `tool_verified`, v3 eligibility visibility, and explicit service mapping for every new tool.
- Eval gate is focused tool/kernel/store/context tests plus opt-in kernel 5-case structural smoke; default-kernel-off public reports remain unchanged.

## Required Read-First MemoryOS Files

Read these before planning implementation:

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/config.json`
- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/work/phase-15/ack.json`
- `.hermes-loop/work/phase-15/result.md`
- `.hermes-loop/work/phase-15/review_verdict.json`
- `.hermes-loop/work/phase-15/reflect_phase-15.md`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/agent_tool_selection.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/memory_lifecycle.py`
- `src/memoryos_lite/core_memory.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `src/memoryos_lite/public_maintenance_planner.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/engine.py`
- `tests/test_agent_kernel.py`
- `tests/test_memory_lifecycle.py`
- `tests/test_core_memory_service.py`
- `tests/test_archival_store.py`
- `tests/test_context_composer.py`
- `tests/test_public_benchmarks.py`

## Required Letta Reference Files

Use these as design references only. Do not import Letta.

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

Design comparison targets:

- Letta core memory blocks have labels, limits, read-only flags, metadata, and prompt rendering under `<memory_blocks>`.
- Letta tool execution routes tool names through a manager/factory into core/archive/passage managers.
- Letta archive and passage managers separate archive attachment, passage creation, search, and ownership/scope semantics.
- Letta agent v3 binds approvals to specific tool calls and resumes only approved calls.
- Letta context-window accounting separates core memory, recall, archival memory, tool returns, and system prompt components.

## Current MemoryOS Code Facts

- `SimpleToolExecutionManager.execute()` currently supports only `archive_write`; unsupported tools return `ok=false`.
- `archive_write` requires non-empty content and either `source_refs` or an approval id. It writes `ArchivalMemory`, creates a session if missing, attaches the archive to the session, verifies history/passage/attachment/eligibility, and returns `tool_verified` when verification passes.
- `SimpleAgentStepRunner.run_step()` emits `kernel_step_started`, `tool_candidates_generated`, `tool_selected` or `tool_selection_denied`, `tool_policy_decision`, `approval_pending` or `approval_granted`, `tool_executed`, `tool_verified`, optional `tool_replay_skipped`, and `kernel_step_completed`.
- Approval replay checks `session_id`, `tool_name`, requested action, `tool_call_id`, and request fingerprint before executing.
- `ToolSelectionBoundary` currently exposes only `archive_write` via `ALLOWED_K2_TOOLS = {"archive_write"}` and denies unsupported tools before policy/execution.
- `MemoryLifecycleService` already creates and applies `PromotionCandidate` objects. Core application requires an approved `ApprovalState` and `CoreMemoryService`; archival application writes `ArchivalMemory`.
- `CoreMemoryService` enforces source refs or approved approval state, actor/reason, token limits, and read-only protection for append/replace/update/delete.
- `MemoryStore` provides archival memory writes/history, archive attachments, passage eligibility by scope, and core memory history.
- `MemoryOSService` instantiates the kernel only when `settings.resolved_agent_kernel == "v1"`.

## Previous Evidence

Accepted Phase 8 milestone baseline:

- LongMemEval 50 full-chain LLM judge: `47/50`.
- LoCoMo 50 full-chain LLM judge: `30/50`.
- Invalid retry run ids: `phase8_lme50_hb_20260522T160637Z` and `phase8_locomo50_hb_20260522T160637Z` were killed/partial/projected and cannot support promotion.

Phase 10 milestone evidence:

- LongMemEval 30 full-chain LLM judge: `29 pass / 1 fail`; `pass_to_fail=0`; remaining evidence-hit-answer-fail `51a45a95`.
- LoCoMo 30 full-chain LLM judge: `20 pass / 10 fail`; `fail_to_pass=conv-26_qa_011, conv-26_qa_012`; `pass_to_fail=0`; remaining retrieval miss `6`; remaining evidence-hit-answer-fail `4`.

Phase 15 structural evidence:

- `uv run pytest -q` -> `499 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.
- LoCoMo 5 projected no-LLM structural smoke: `0/5`; cases:
  - evidence-hit-answer-fail: `conv-26_qa_001`, `conv-26_qa_002`;
  - retrieval-miss: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- All five Phase 15 smoke rows had proposal-only planner artifacts, `gold_fields_used=false`, and no planner-created `tool_executed` events.

## Known Pass-To-Fail Risks

- Broadening `ToolSelectionBoundary` could accidentally let unsupported or malformed tools reach policy/execution.
- Approval replay could be weakened if new tools omit `tool_call_id`, source refs, or request fingerprint material.
- New mutating tools could write directly to store and bypass `MemoryLifecycleService`, `CoreMemoryService`, or archive/passage service boundaries.
- `archive_attach` could make unrelated passages visible to v3 if scope checks are loose.
- `core_promotion_request` could become a hidden direct core write if it applies candidates instead of creating pending candidates.
- Read-only search tools could leak expected source ids, expected answers, judge labels, or failure classes if wired from public eval sidecars.
- Tool result messages could pollute answer context or source attribution if not clearly marked and scoped.
- Public reports could start emitting kernel events without opt-in if engine/settings wiring changes.

## RED Evidence To Start From

Use failing tests before implementation. Initial RED targets should include:

- `archive_attach` candidate is generated, requires policy/approval/source refs, executes through a named service, creates an `ArchiveAttachment`, verifies eligibility, and makes only eligible passages visible to v3.
- `archive_attach` replay with tampered archive id, scope id, `tool_call_id`, or requested action denies before execution and emits no `tool_verified`.
- `core_promotion_request` creates a pending `PromotionCandidate` through `MemoryLifecycleService` with source refs and approval provenance; it must not mutate core memory or make a core block visible in v3.
- `recall_search` and `archive_search`, if opened, are read-only, bounded, traced, and produce tool result messages without memory writes.
- `core_memory_append`, `core_memory_replace`, destructive delete/deprecate, and any unknown tool remain fail-closed before policy/execution unless a separate reviewed safety gate exists.
- Default public benchmark run has `kernel_trace_events == []` without `MEMORYOS_AGENT_KERNEL=v1`.
- Opt-in kernel structural public smoke shows registry/selection/approval/execution/verification events only for explicitly requested and allowed tools.

## Expected Verification Commands For Implementation Phase

Focused tests first:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_service.py tests/test_archival_store.py tests/test_context_composer.py -q
uv run pytest tests/test_public_benchmarks.py -q
```

Baseline checks before ACK:

```bash
uv run pytest -q
uv run ruff check .
```

Opt-in structural smoke only, if implementation changes public kernel probe or report shape:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase16_locomo5_kernel_tools_structural
```

Default-off guard:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase16_locomo5_kernel_default_off_guard
```

Phase 16 does not require a 30-case full-chain LLM judge milestone unless it changes default retrieval, answer projection, scoring, or non-kernel public benchmark behavior. Smoke evidence cannot support a benchmark-quality improvement claim.

## Anti-Demo Completion Criteria

Phase 16 can ACK only if the implementation reaches level 3 usable for its scoped tool surface:

- opened tools are wired into the real opt-in `SimpleAgentStepRunner.run_step()` path, not a demo helper;
- each opened tool has registry, candidate generation, policy decision, approval semantics if mutating, named executor/service method, post-action verification, trace coverage, and integration tests;
- every write tool requires source refs or approved approval provenance;
- replay tampering cannot execute or verify a write;
- unsupported and destructive tools fail closed before mutation;
- v3 composer sees new artifacts only through existing scope/provenance rules;
- default public benchmark reports remain kernel-off;
- case-level structural smoke, if run, reports LongMemEval and LoCoMo separately and makes no benchmark-improvement claim;
- `result.md`, `execute_review.md`, `review_verdict.json`, and `ack.json` all reference this active goal and `work/phase-16/context_bundle.md`.

## Hard Constraints

- Preserve v3 default.
- Preserve explicit v1 fallback.
- Preserve kernel opt-in.
- Do not use benchmark case-id hacks or expected-answer leaks.
- Do not hide case-level regressions.
- Do not modify `.hermes-loop` orchestration infrastructure except phase-local artifacts required by the controller.
- Do not consume stale ACK, result, or review artifacts.
