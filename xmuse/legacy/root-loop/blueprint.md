# MemoryOS Lite Letta-Style Benchmark Usability Blueprint

Status: active blueprint.
Target controller: `xmuse/god_loop_prompt.md`.
Last updated: 2026-05-23.

## Purpose

This is the active Hermes/God blueprint for moving MemoryOS Lite v3 from
the completed phase-8 promotion gate into the phase-9 to phase-15
targeted reliability loop. The immediate goal is to make LongMemEval and
LoCoMo behavior usable, diagnosable, and source-grounded.

The target is not a production MemoryOS and not a direct Letta fork. The target
is a MemoryOS Lite implementation that borrows Letta's memory semantics:

- explicit core memory blocks;
- archive and passage scopes;
- attached archive retrieval;
- passage-level evidence;
- tool-mediated memory mutation;
- durable approval/tool traces;
- component-level context accounting;
- answer projection that cites selected evidence.

Letta source lives at `/home/iiyatu/projects/python/letta` and is a design
reference only. Do not add it as a runtime dependency.

## Current Baseline And Phase 8 Evidence

Use the current repository, phase-8 ACK, and promoted phase-8 amendment as the
active baseline.

Architecture baseline:

- `memoryos_memory_arch` defaults to `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- public benchmark goes through the v3 context path.
- v3 plus kernel opt-in triggers `SimpleAgentStepRunner.run_step()`.
- `PublicBenchmarkResult` includes `kernel_trace_events`.
- kernel has the minimal trace loop:
  `approval_pending -> approval_granted -> tool_executed`.
- `SimpleToolExecutionManager` only minimally supports `archive_write`.

Phase 8 accepted evidence:

- LongMemEval 50 full-chain LLM judge: `47/50`.
- LoCoMo 50 full-chain LLM judge: `30/50`.
- No same-subset pass-to-fail cases were recorded.
- Kernel default remained off.
- Valid reports:
  `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json` and
  `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.
- Invalid for promotion evidence:
  `phase8_lme50_hb_20260522T160637Z` and
  `phase8_locomo50_hb_20260522T160637Z`, because they were killed/partial and
  projected/no-judge.

Current diagnosis:

- v3 context and opt-in kernel paths are wired.
- LongMemEval is comparatively strong but not sufficient for promotion alone.
- LoCoMo is the controlling bottleneck at `30/50`.
- LoCoMo failures split between retrieval/session localization misses and
  evidence-hit-answer-fail cases.
- The next loop starts with failure replay and recall/evidence reliability,
  then expands to handoff, archival/RAG, core lifecycle, and the opt-in agent
  memory loop.

## Hard Constraints

- Reuse existing `xmuse` infrastructure.
- Do not rewrite `hermes_reporter.py`, `god_launcher.sh` locking/heartbeat, or
  the lane/state directory model unless proven blocked.
- Do not overwrite active `xmuse/blueprint.md` without recording the
  triggering evidence and the amendment.
- `state.json` may be updated only when a reviewed ACK or promoted
  amendment requires an active-phase transition.
- Preserve v3 as default memory architecture.
- Preserve `MEMORYOS_MEMORY_ARCH=v1` fallback.
- Preserve v3 agent kernel as opt-in.
- Do not claim benchmark improvement from aggregate pass rate alone.
- Do not promote LongMemEval gains if LoCoMo remains unexplained.
- Do not use benchmark case-id rules, expected-answer leaks, or dataset hacks.
- Do not treat prompt-only tweaks as architecture improvements unless
  case-level evidence shows answer projection was the bottleneck.
- Every implementation phase needs failing tests or concrete failing benchmark
  cases before code changes.
- Every milestone phase must produce case-level diagnostics, not only score
  summaries.
- Public benchmark gold fields, including expected answers, expected evidence
  ids, and gold-derived failure labels, are eval-only sidecars. They must not be
  copied into agent-visible memory, tool requests, source refs, archive
  attachments, repair notes, promotion candidates, or context-composer inputs.
- A maintenance proposal can be promoted to a kernel tool request only if it can
  be regenerated from model-visible artifacts: retrieved candidates, selected
  context, rendered evidence, answer text, citations, tool traces, and store
  provenance. Gold labels may score or classify the proposal after the fact, but
  may not supply its content, target ids, or scope.

## Master/Slave Feature Governance

Hermes may run parallel feature development through a master/slave overlay while
preserving the existing lane permissions.

- `master_god` owns integration, cross-feature conflict resolution, integrated
  testing, and final merge decisions.
- Each `slave_god` owns one feature branch/worktree and may use the same
  research/plan/execute/review/subagent workflow inside that feature boundary.
- Root `state.json` remains the single active controller state; parallel feature
  state is recorded separately in optional `xmuse/feature_lanes.json`.
- Feature work must remain isolated by git worktree or GitHub PR until the slave
  reports usable ACK, passing review, required artifacts, clean worktree, and a
  documented merge target.
- Master God may merge only after integrated tests and after confirming that the
  feature does not violate v3 default, v1 fallback, kernel opt-in, source
  grounding, or benchmark-leakage constraints.
- Same-slice repair smoke or LongMemEval-only evidence is never sufficient for
  master merge if the feature makes memory-quality claims.

The reporter and hardening helpers summarize `feature_lanes.json` into
`master_slave_status.json` and `master_slave_status.md`. Missing registry means
no parallel feature lanes are active.

## Superpowers And Goal Discipline

God should use Superpowers methodology as workflow discipline:

- brainstorming for design alternatives;
- test-driven-development for code changes;
- systematic-debugging for unexpected eval/test failures;
- requesting-code-review / receiving-code-review for review loops;
- verification-before-completion before any completion claim.

Because Hermes/God runs autonomously, interactive "ask user" gates are replaced
by the active goal and written artifacts. God must still record the decision
that would normally be approved by a user.

Concrete autonomous replacements:

- Superpowers brainstorming approval gates become God-recorded design decisions
  in `brainstorm.md`, `spec.md`, and `plan_review.md`;
- Superpowers plan execution choices default to subagent-driven execution when
  tasks are independent, otherwise inline execution, with the choice recorded
  in `plan_final.md`;
- review FAIL feedback must route to bounded repair, repeat, `god_adjust`, or
  hold; it must not wait for human confirmation by default;
- `pause` is reserved for explicit human-only authorization, destructive risk,
  unavailable mandatory external service, or a hard-constraint conflict that
  cannot be narrowed safely;
- no lane prompt may use `request_user_input`, visual-companion consent, typed
  confirmation, or "should I continue" as part of the autonomous loop.

At startup God must write or confirm `xmuse/work/current_goal.md`:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Reference that active goal from dispatch, result, review, and ACK artifacts.

## Completion Levels

No phase may advance unless it reaches level 3.

```text
0. plan-only: only plan/docs, no real implementation.
1. demo-only: demo/stub/happy path exists but is not wired into the real path.
2. partial: some real path wiring exists but lacks tests, diagnostics, or eval evidence.
3. usable: wired into the real MemoryOS v3/public benchmark path, tested, diagnosed, smoked, and reviewed.
```

Research-only phases can be usable only if their output is consumed by the next
dispatch and contains concrete, testable decisions. An unconsumed analysis file
is plan-only.

## Required ACK Evidence

Every phase ACK must provide:

- `ack_level = usable`;
- active goal reference;
- context bundle path and confirmation that plan/execute/review outputs used it;
- affected chain components:
  ingest, store, retrieval, context composer, answer projection, kernel loop,
  public eval;
- whether the real public benchmark path is wired;
- explicit list of remaining demo-only or stub parts;
- failing tests added before fixes or benchmark cases used as RED evidence;
- verification commands and summarized outputs;
- LongMemEval and LoCoMo case-level results when the phase touches benchmark
  path behavior;
- fail-to-pass and pass-to-fail lists;
- retrieval miss and evidence-hit-answer-fail lists;
- review verdict on overfitting, source grounding, v1 fallback, v3 default, and
  kernel default.

If these cannot be filled with evidence, God must choose `repeat`,
`adjust_blueprint`, or `pause`, not `advance`.

## Context Bundle Requirement

Lane agents are not assumed to be persistent across phases. Every phase must
start with:

```text
work/{phase-id}/context_bundle.md
```

The bundle is the handoff packet that lets a fresh plan, execute, research, or
review agent work with sufficient context. It must contain:

- active goal;
- phase objective, scope, and non-goals;
- current hypothesis and disconfirming evidence;
- relevant `state.json` excerpt;
- active blueprint excerpts and any promoted amendments;
- required MemoryOS files;
- required Letta reference files;
- relevant prior work artifacts and benchmark reports;
- current baseline and case-level failure taxonomy;
- failing tests or benchmark cases to start from;
- smoke and milestone eval commands;
- anti-demo usable ACK criteria;
- v1 fallback, v3 default, and kernel opt-in constraints.

`god_dispatch.json` must point to this bundle. `brainstorm.md`, `plan.md`,
`plan_final.md`, `result.md`, `execute_review.md`, `review_verdict.json`, and
`ack.json` must either cite the bundle or explicitly explain why a section of
the bundle was superseded by newer evidence.

If a lane output ignores the bundle, contradicts it without evidence, or relies
on unstated prior chat memory, God must treat that output as stale and rerun the
lane or enter `GOD_ADJUST`.

## Execute Goal Contract

Before EXECUTE starts implementation, God must write
`work/{phase-id}/execute_goal.md`. The first line must be
`# phase: {phase-id}` and the body must include `/goal`.

This goal is phase-local. It may constrain scope, files, real-path wiring,
required tests, `result.md`, `execute_review.md`, and demo-only prohibitions.
It must cap repair loops with `Max repair cycles: 1`, `2`, or `3`.

It must not use benchmark scores as the target condition. LongMemEval and
LoCoMo may appear as diagnostic or gate evidence, but not as constraints such
as target pass rate, target accuracy, `50/50`, or "continue until score
improves". If eval evidence regresses, God classifies the failure and chooses
repair, repeat, adjust, or hold; it does not optimize in an unbounded score
loop.

## Full-Chain LLM Judge Gates

5-case runs are smoke only. 10-case runs are early stability. 30-50 case
full-chain LLM judge runs are milestone evidence and may change the blueprint.

Full-chain means:

- do not pass `--no-llm-answer`;
- do not pass `--no-llm-judge`;
- run through `MEMORYOS_MEMORY_ARCH=v3`;
- add `MEMORYOS_AGENT_KERNEL=v1` only when the phase explicitly tests kernel
  behavior.

Review eval autonomy:

- God may choose `not_applicable`, `smoke`, or `milestone` eval scope during
  review.
- `not_applicable` is limited to control-plane, docs, prompt, or
  non-behavioral hardening changes, and must be justified in
  `review_eval_decision.reason`.
- `smoke` may use deterministic/no-LLM or one-benchmark diagnostics, but cannot
  satisfy a milestone promotion gate.
- `milestone` requires both LongMemEval and LoCoMo. If the promotion gate is
  marked satisfied, LLM answer and LLM judge must be enabled unless the active
  phase explicitly states that full-chain judge is not applicable.
- Every `review_verdict.json` must include `review_eval_decision` with
  benchmark run/skip choices, LLM answer/judge choices, and
  `promotion_gate` as `satisfied`, `not_applicable`, or `not_satisfied`.
- God must not claim chain-level improvement from LongMemEval-only or
  LoCoMo-only evidence.

Default command shape:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge
```

If the available LoCoMo local file has fewer than the requested cases, run all
available cases and record the cap. If LLM provider access is unavailable,
record the blocker, run deterministic/no-LLM smoke only as fallback evidence,
and do not treat that as satisfying a full-chain milestone gate.

After every 30-50 case run, God must write a case-level report with:

- pass/fail by benchmark;
- fail-to-pass;
- pass-to-fail;
- unchanged fail;
- retrieval miss;
- evidence hit but context missing;
- evidence hit but answer fail;
- unsupported answer;
- judge questionable;
- source grounding movement;
- LoCoMo-specific failure mode.

## Letta Comparison Map

Before implementation, God and research_lane must compare MemoryOS against:

| Letta source | Semantics to borrow | MemoryOS risk if missing |
|---|---|---|
| `schemas/block.py` | block label/value/limit/description/read_only/tags | core memory becomes unbounded text |
| `schemas/memory.py` | structured memory rendering and block metadata | composer cannot budget or audit core |
| `schemas/archive.py` | archive identity, metadata, provider config | archival search has no scope |
| `schemas/passage.py` | passage text, archive/source/file/tags/metadata | evidence cannot be cited precisely |
| `services/block_manager.py` | block CRUD and prompt rebuild semantics | memory updates do not affect context |
| `services/archive_manager.py` | archive create/list/attach/detach/default | global top-k pollution |
| `services/passage_manager.py` | agent vs source passage invariants | source and agent memory blur |
| `tool_executor/core_tool_executor.py` | memory tools and edit invariants | unsafe or untraceable memory writes |
| `tool_execution_manager.py` | executor routing, truncation, metrics | tools remain ad hoc |
| `agents/letta_agent_v3.py` | approval, tool call, continuation, compaction | kernel remains demo-level |
| `context_window_calculator.py` | per-component token accounting | v3 budget remains opaque |

The goal is semantic compatibility, not line-by-line porting.

## Kernel And Eval Boundary

Letta-style kernel work in MemoryOS means a tool-mediated state transition, not
an eval-oracle repair loop.

Adopt these kernel invariants from Letta:

- approval is bound to the current pending tool call, including `step_id`,
  stable `tool_call_id` or equivalent request fingerprint, tool name, arguments,
  session/scope, and source refs;
- replay is idempotent only when a matching tool return or executed trace for
  the same pending call already exists;
- tool execution produces a structured result with success/error status, bounded
  return payload, durable tool-return message, and trace event;
- memory-writing tools route through a service contract
  `policy -> executor -> lifecycle/store service -> verification -> tool return`;
- direct store writes inside the kernel are allowed only for the narrow current
  `archive_write` bridge until a phase explicitly replaces them with a service
  executor contract.

Eval diagnostics must stay outside the agent-visible memory plane:

- `expected_source_ids`, expected answers, benchmark case ids used as labels,
  and gold-derived final failure classes may appear in reports, ACK evidence,
  and case matrices only;
- proposal payloads and tool arguments must include a `gold_fields_used=false`
  assertion or an explicit denial reason;
- if a proposed repair depends on gold-only fields, it must be emitted as
  diagnostic-only and cannot be executed through the kernel;
- same-slice repair runs are structural smokes, not promotion evidence.

## Kernel Agent Graduation Blueprint

Spec source:
`docs/superpowers/specs/2026-05-24-kernel-agent-graduation-blueprint-design.md`.

Graduation objective:
build a Letta-style, audited, source-grounded memory control plane on top of
MemoryOS Lite's existing v3 composer, recall, archival memory, core memory, and
lifecycle services. Architecture graduation comes first; public benchmark
graduation is the hard validation gate.

Default semantics:

- external kernel enablement remains opt-in and must not be enabled by this
  blueprint without separate approval;
- once the kernel is enabled, the graduated kernel defaults to hybrid tool
  selection inside the kernel;
- default public benchmark runs remain maintenance-write-free and comparable to
  the existing v3 baseline;
- opt-in repair evals must use isolated stores and cannot become promotion
  evidence without clean-store or held-out validation.

Target kernel loop:

```text
user turn / trigger
-> V3ContextComposer.build()
-> ToolSelectionRouter
-> ToolPolicyEngine
-> ApprovalLedger
-> ToolExecutionManager
-> domain executor / existing memory service
-> VerificationService
-> tool-return record + kernel trace
-> ContinuationController
-> next step | pause | stop | escalate
```

Borrowed Letta semantics:

- agent step loop with bounded continuation;
- approval pending state bound to the pending tool call;
- approval replay allowed only for an exact binding match;
- tool executor routing instead of ad hoc kernel mutations;
- compact, durable tool-return records;
- memory tools executed by domain services, not by unscoped direct store writes;
- component-level context and return-payload accounting.

Non-goals:

- do not import or clone Letta's full runtime;
- do not add destructive delete/deprecate tools in the first graduation loop;
- do not let benchmark gold fields guide executable maintenance writes;
- do not describe MemoryOS Lite as production-ready MemoryOS.

### Kernel Graduation Milestones

K0 - Kernel Contract Freeze:

- freeze tool call, approval, execution result, verification, and trace schemas;
- add deterministic serialization/replay contract fixtures;
- make unsupported tools fail closed before adding broader tool execution.

K1 - Audited Control Plane:

- carry one `archive_write` through policy, approval, execution, verification,
  tool return, and trace;
- verify real store state, history, attachment/scope eligibility, and later v3
  visibility;
- make verification failure durable and impossible to count as successful
  mutation evidence.

K2 - Hybrid Tool Selection:

- deterministic router generates candidate tools and constraints;
- constrained LLM selector may choose only inside the candidate set or no-op;
- schema, policy, provenance, and fallback checks run after selection;
- illegal tool names, invalid arguments, timeouts, and LLM failures deny or
  fallback without executing unknown tools.

K3 - Graduated Memory Tools:

- Level 1 write-safe tools: `archive_write`, `archive_attach`,
  `core_promotion_request`;
- Level 2 read/search tools: `recall_search`, `archive_search`;
- Level 3 controlled core edit tools: `core_memory_append`,
  `core_memory_replace`;
- every opened tool must have registry, policy, executor, verification, trace,
  and integration tests before it counts toward graduation.

K4 - Maintenance Planner And Repair Eval:

- produce maintenance proposals only from model-visible diagnostics;
- separate executable payloads from eval-only sidecars;
- require every executable proposal to assert `gold_fields_used=false`;
- treat same-slice repair as structural smoke, not quality promotion evidence.

K5 - Graduation Governance:

- run clean-store or held-out validation before promotion claims;
- report LoCoMo and LongMemEval separately;
- split judged pass movement from source-grounded movement;
- block graduation on unexplained pass-to-fail, source-grounding regressions, or
  benchmark leakage.

### Required Kernel Data Contracts

`ToolCallRecord` must include:

- `step_id`;
- `tool_call_id`;
- stable `request_fingerprint`;
- `tool_name`;
- `arguments`;
- `session_id`;
- `identity_scope`;
- `source_refs`;
- `selection_origin`: `deterministic | llm | fallback`;
- `candidate_reason`.

`ApprovalRecord` must include:

- complete binding to the tool call;
- `status`: `pending | approved | rejected | expired | executed | skipped`;
- actor, reason, requested/resolved timestamps;
- replay and idempotency metadata.

`ToolExecutionResult` must include:

- `status`: `success | error`;
- `tool_name`;
- bounded result payload;
- error payload if applicable;
- source refs;
- verification payload for tools that require write verification.

`VerificationResult` must include:

- `status`: `verified | failed | not_required`;
- boolean `ok`;
- executed checks;
- failure reason;
- bindings to the tool call, approval, and written resource.

`KernelTraceEvent` must cover at least:

- `kernel_step_started`;
- `tool_candidates_generated`;
- `tool_selected`;
- `tool_policy_decision`;
- `approval_pending`;
- `approval_granted`;
- `approval_replay_denied`;
- `tool_denied`;
- `tool_executed`;
- `tool_verified`;
- `tool_replay_skipped`;
- `continuation_decided`;
- `kernel_step_completed`.

### Hybrid Tool Selection Boundary

The kernel-internal selector may see:

- current user/task input;
- v3 selected context;
- allowed tool descriptions;
- policy summaries;
- model-visible retrieval and verification traces.

The selector must not see or use:

- expected answers;
- `expected_source_ids`;
- benchmark judge labels;
- gold-derived failure target classes;
- case-specific repair ids.

The deterministic router is authoritative for candidate scope. The LLM selector
cannot invent tools, expand permission scope, bypass source requirements, or
turn eval sidecar fields into tool arguments.

### Phase Mapping For Active Loop

- Phase 14 owns K0/K1 minimums: contract freeze plus one audited
  `archive_write` loop.
- Phase 15 owns K2 first, then the K4 planner only after constrained selection
  is testable.
- Phase 16 owns K3 graduated tool surface and must route each tool through a
  named domain service.
- Phase 17 owns K4 repair smoke and clean-store or held-out validation setup.
- Phase 18 owns K5 governance and the final promote/hold/continue decision.

## Historical Completed Phase Index

The following headings are retained only so `config.json`, `state.json`, and
older phase artifacts can resolve completed phase 0-8 references. They are not
the active execution loop. Active execution starts at Phase 9.

### Phase 0 - Baseline Freeze And Case Harness

Completed historical baseline freeze and case harness.

### Phase 1 - Letta Gap Matrix And Contract Decisions

Completed historical contract and gap-matrix phase.

### Phase 2 - Evidence Harness And Failure Taxonomy

Completed historical evidence harness phase.

### Phase 3 - Letta-Style Core Memory Blocks

Completed historical core-memory implementation phase.

### Phase 4 - Archive And Passage Scope

Completed historical archive/passage scope phase.

### Phase 5 - Context Composer And Accounting

Completed historical context composer/accounting phase.

### Phase 6 - Answer Projection And Citation Contract

Completed historical answer projection/citation phase.

### Phase 7 - Kernel, Tool, Approval, And Memory Mutation Loop

Completed historical opt-in kernel/tool loop phase.

### Phase 8 - Promotion Gate And Next Blueprint Decision

Completed historical promotion gate. The accepted phase-8 decision is
`adjust_blueprint` / `continue_targeted`, with Phase 9 as the next active
phase.

## Promoted Phase 9-18 Loop

## Core Thesis

The next loop should not only patch a single LoCoMo failure. It should turn the
existing v3 memory layers into a usable, source-attributed, lifecycle-governed,
agent-operable memory system.

Letta is a reference, not a template to copy. MemoryOS should keep Letta-style
core memory, archival memory, and agent memory tools, but add a stronger
benchmark-governed evidence layer:

- source-attributed evidence packets instead of opaque top-k snippets;
- failure replay before implementation;
- explicit lifecycle promotion from recall to archival to core;
- reversible provenance for every long-term memory mutation;
- eval gates that separate retrieval quality from judged answer quality.

## Current Evidence

Phase 8 accepted evidence:

- LongMemEval 50 full-chain LLM judge: `47/50`.
- LoCoMo 50 full-chain LLM judge: `30/50`.
- No same-subset pass-to-fail cases were recorded.
- Kernel default remained off.

LoCoMo is the controlling bottleneck:

- Retrieval/session localization misses:
  `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`,
  `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`,
  `conv-26_qa_025`, `conv-26_qa_035`, `conv-26_qa_036`,
  `conv-26_qa_039`, `conv-26_qa_044`, `conv-26_qa_050`.
- Evidence-hit-answer-fail cases:
  `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`,
  `conv-26_qa_024`, `conv-26_qa_027`, `conv-26_qa_033`,
  `conv-26_qa_041`, `conv-26_qa_048`.
- Judge/source-support questionable:
  `conv-26_qa_015`.

Therefore the next loop starts with recall/evidence reliability, then expands
to archival, core, and agent-loop lifecycle work.

Post phase-13 continuation evidence:

- Phase 13 completed with usable ACK for core-memory lifecycle hardening.
- The opt-in kernel remains default-off.
- Manual 5-case full-chain LLM judge after phase 13:
  - LongMemEval: `5/5`, `answer_mode=llm`, `judge_status=judge_pass`,
    `source_hit=5/5`;
  - LoCoMo: `4/5`, `answer_mode=llm`, `judge_status=judge_pass/judge_fail`,
    `source_hit=2/5`.
- The 5-case LLM judge smoke is a chain-health signal only. It is not
  promotion evidence and does not override the need for LoCoMo source-grounding
  repair and larger same-case gates.

## Global Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not remove explicit `MEMORYOS_MEMORY_ARCH=v1` fallback.
- Do not change benchmark scoring semantics.
- Do not use benchmark case-id hacks or expected-answer leaks.
- Do not claim production readiness.
- Do not accept aggregate-only improvements without same-case analysis.
- Do not rewrite the full architecture unless case evidence proves local fixes
  cannot solve the bottleneck.

## 30/50-Case Eval Gate Policy

30/50-case public benchmark runs are milestone gates, not routine regression
tests.

Mandatory rules:

- **LongMemEval and LoCoMo eval commands must run in parallel**
  (separate background processes). Do not run them sequentially — this
  doubles wall-clock time.
- Parallel public benchmark gates and smokes must use isolated `DATA_DIR`
  values per benchmark and run id. Reports from a shared default `.memoryos`
  store are invalid for promotion if either parallel process crashes,
  cross-contaminates sessions, or cannot prove store isolation. Record each
  `DATA_DIR` and report path in the phase result.

- no projected/no-LLM report can satisfy a quality gate;
- every quality gate command must explicitly include `--llm-answer` and
  `--llm-judge`;
- every gate must record run id, command, report path, comparison report, and
  whether kernel was off or opt-in;
- retrieval/source movement must be reported separately from judged answer
  movement;
- pass-to-fail and fail-to-pass lists must be explicit, even when empty;
- LoCoMo failure-class movement must be reported separately from aggregate
  pass/fail movement;
- 50-case runs are reserved for promotion, strong-signal confirmation, or a
  God-approved escalation after a useful 30-case signal.

Default milestone pattern:

1. focused tests;
2. fixed failure-slice full-chain smoke;
3. LoCoMo 30 full-chain gate;
4. LongMemEval 30 full-chain regression guard;
5. optional 50-case confirmation only if the 30-case signal is useful and
   same-case explainable.

## God Adjustment And Repeat Protocol

God may change the local plan, repeat a phase, or write an adjustment artifact
when evidence shows the blueprint is no longer the right next step. This is a
required control mechanism, not an exceptional failure path.

Required adjustment triggers:

- review finds demo-only implementation, partial wiring, or behavior that does
  not exercise the real public benchmark path;
- `state.json`, root `blueprint.md`, root `config.json`, and phase artifacts
  disagree about the active phase or accepted evidence;
- a 30-case full-chain gate has no same-case explainable improvement and does
  not convert failures into a more precise downstream class;
- source grounding, retrieval/source metrics, or pass-to-fail movement regresses
  in a way that is not explained by the phase goal;
- a phase tries to advance from projected/no-LLM evidence for a quality claim;
- stale, killed, partial, or heartbeat artifacts are being treated as promotion
  evidence.

Allowed decisions:

- `repeat_phase`: keep the same phase and require a narrower implementation;
- `god_adjust`: amend the local blueprint or phase scope before continuing;
- `hold`: stop promotion or expansion because evidence is unsafe;
- `continue_targeted`: move to the next targeted phase only when the ACK gate is
  met and same-case evidence is explicit;
- `expand_eval`: run larger 30/50-case evidence only after the smaller gate has
  useful, explainable signal.

Every adjustment must write the reason, affected cases, stale artifacts to
ignore, and the next allowed gate into the phase-local `adjustment.md` or
`ack.json`.

## Phase 9 - Evidence Closure And Failure Replay

Target state: `failure-replay-ready`.

Purpose:
make every benchmark failure replayable from query to retrieval, context
selection, rendered evidence, answer, citation, and judge result.

Inputs:

- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`
- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/diagnostic_report.py`

Allowed changes:

- diagnostic helpers;
- replay artifact writers;
- tests for failure class completeness;
- phase-local reports.

Not allowed:

- answer/retrieval behavior changes unless a failing diagnostic test proves the
  current report cannot classify real cases.

Required artifacts:

- `work/phase-9/failure_taxonomy.md`
- `work/phase-9/case_matrix.md`
- `work/phase-9/replay_schema.md`
- `work/phase-9/replay_cases/<case_id>.json` or one equivalent structured
  per-case replay artifact for each of the 20 LoCoMo phase8 failures;
- `work/phase-9/result.md`
- `work/phase-9/review_verdict.json`
- `work/phase-9/ack.json` or `work/phase-9/adjustment.md`

Required failure classes:

- retrieval miss;
- session localization miss;
- temporal/date miss;
- speaker/entity confusion;
- evidence retrieved but not selected;
- evidence selected but not rendered;
- evidence rendered but answer fails;
- unsupported citation;
- refusal despite evidence;
- judge questionable;
- diagnostic gap.

ACK gate:

- all 20 LoCoMo phase8 failures are classified;
- every one of the 20 LoCoMo phase8 failures has a replay row or artifact with
  case id, expected source ids, indexed source status, retrieved ids, selected
  ids, rendered ids, answer output, citation/source support, judge result, and
  final failure class;
- replay artifacts distinguish path-level patterns from case-level evidence;
- source metrics remain separate from judged answer metrics;
- `diagnostic_gap` cases are explicit and not hidden.

## Phase 10 - Recall Memory Reliability

Target state: `recall-evidence-reliable`.

Purpose:
make recall memory robust enough for LoCoMo dialogue, temporal, speaker, and
multi-hop questions without regressing LongMemEval.

Current implementation anchor:

- `RecallPipeline`
- `RecallMemorySearcher`
- episode backfill;
- BM25 direct hits;
- neighbor expansion;
- benchmark session guard.

Design direction:

Recall should return an evidence packet, not just a flat top-k list:

```text
anchor_turn
+ neighbor_turns
+ benchmark_session_id
+ benchmark_date
+ speaker/entity hints
+ rank features
+ selected because...
```

Potential targeted fixes:

- LoCoMo-aware same-session expansion when the expected source is near a weak
  lexical hit;
- speaker-aware expansion for questions naming Caroline/Melanie or equivalent
  participants;
- temporal/date-aware boost that distinguishes session date from message text;
- multi-anchor retrieval for questions requiring two dialogue turns;
- evidence packet diagnostics that show which anchor caused each neighbor.

Required tests:

- failing test for one real repeated LoCoMo failure class;
- fixed-slice test or diagnostic assertion covering the selected repeated
  LoCoMo failure cases that the phase claims to improve;
- regression test that unrelated session neighbors are not pulled in;
- LongMemEval guard where high LME retrieval remains stable.

Eval gate:

- focused pytest;
- LoCoMo fixed failure slice full-chain LLM judge;
- LoCoMo 30-case full-chain LLM judge as the recall milestone gate;
- LongMemEval 30-case full-chain LLM judge as the regression guard;
- same-case movement table for the fixed failure slice and the 30-case gate,
  with pass-to-fail, fail-to-pass, unchanged-fail, retrieval/source movement,
  and failure-class movement split out;
- optional LoCoMo 50-case confirmation only after LoCoMo 30 improves on
  same-case evidence or converts a repeated retrieval miss into a more precise
  downstream failure class.

ACK gate:

- at least one repeated LoCoMo retrieval/session failure class improves or is
  converted into a more precise downstream failure class;
- the LoCoMo 30-case gate has same-case explainable signal; if it has no
  explainable gain, God must choose `repeat_phase` or `god_adjust` instead of
  advancing;
- any pass-to-fail case is listed with a cause and either fixed, accepted with a
  documented tradeoff, or used to trigger `hold`;
- no material LongMemEval collapse;
- all new behavior is explained in `case_matrix.md`.

## Phase 11 - Evidence Handoff And Context Selection

Target state: `evidence-handoff-reliable`.

Purpose:
ensure retrieved evidence is not silently lost between recall, v3 composer,
legacy context package projection, answer evidence rendering, and public report
diagnostics.

Current implementation anchor:

- `V3ContextComposer`
- `ContextPackageV3`
- `_context_package_from_v3`
- `v3_final_context_trace`
- `case_diagnostics.selected_context_ids`
- `case_diagnostics.rendered_evidence_ids`

Design direction:

Every expected source should have a traceable status:

```text
indexed -> retrieved -> selected -> rendered -> cited -> judged
```

Required tests:

- retrieved expected source but dropped by budget;
- selected source missing from final context trace;
- rendered source not available to answerer;
- archival/recall source id projection mismatch.

Eval gate:

- focused pytest for context projection and diagnostics;
- LoCoMo 30-case full-chain LLM judge;
- LongMemEval 30-case full-chain LLM judge as regression guard;
- report failure-class movement for `retrieval_miss`,
  `context_missing_evidence`, and `evidence_hit_answer_fail` separately;
- optional LoCoMo 50 only if the 30-case run proves handoff improvement rather
  than only aggregate judge noise.

ACK gate:

- no selected expected evidence disappears without a diagnostic reason;
- `context_missing_evidence` is split into selected-drop vs render-drop;
- public reports expose enough fields for same-case diagnosis.

## Phase 12 - Archival/RAG Memory Unification

Target state: `archival-rag-usable`.

Purpose:
unify archival memory writes and archival passage retrieval into a complete
long-term RAG loop.

Current split:

- `archive_write` writes `ArchivalMemory`;
- v3 composer retrieves `ArchivalPassage`;
- documents/chunks/passages exist and are scope-gated;
- vector/hybrid modes currently fall back to lexical when vector is unavailable.

Design direction:

Archival memory should become retrievable evidence after write:

```text
agent/tool/user source
-> archival memory
-> passage/index representation
-> scoped retrieval
-> context item
-> cited answer
-> history/provenance
```

Required tests:

- `archive_write` creates memory with source refs;
- generated/bridged passage is eligible by session/archive scope;
- subsequent `build_context` can retrieve the written archival fact;
- delete/update history prevents stale archival evidence from being selected.

Eval gate:

- focused archival tests;
- no-LLM structural smoke for archive write -> retrieval;
- optional LLM judge only after structural path is green;
- run LoCoMo 30 and LongMemEval 30 only if archival changes affect the default
  v3 public benchmark context path.

ACK gate:

- archival write and archival retrieval are connected in one audited path;
- every archival context item has source refs;
- no sourceless archival mutation is accepted.

## Phase 13 - Core Memory Lifecycle

Target state: `core-memory-lifecycle-usable`.

Purpose:
turn core memory from manually managed blocks into source-backed, conflict-aware
stable memory.

Current capability:

- core blocks can be stored, rendered, updated, deleted, and history-tracked;
- v3 composer reads core blocks into the core layer;
- writes require source refs or approval.

Design direction:

Core memory should be promoted, not casually written:

```text
recall/archival evidence
-> promotion candidate
-> conflict check
-> approval/source-density gate
-> core update
-> history
-> rendered block
```

Required tests:

- repeated recall evidence can propose a core candidate;
- conflicting candidate does not overwrite silently;
- approved replacement records old value and source refs;
- read-only core blocks reject mutation;
- stale core facts can be deprecated without deletion from history.

Eval gate:

- focused core-memory lifecycle tests;
- no-LLM structural smoke proving core candidates render into v3 context only
  through approved/source-backed paths;
- run LoCoMo 30 and LongMemEval 30 only if core lifecycle changes alter default
  benchmark context composition.

ACK gate:

- core candidate lifecycle is source-backed and reviewable;
- rendered core memory stays within token budget;
- core updates do not bypass approval/provenance.

## Phase 14 - Opt-In Kernel Memory Action Verification

Target state: `agent-loop-memory-usable`.

Purpose:
make the opt-in kernel able to prove one complete, audited memory action loop
without broadening the tool surface.

Kernel graduation mapping:
Phase 14 implements the minimum K0/K1 slice. It freezes the records needed for
approval, execution, verification, trace, and replay, then proves them with the
existing `archive_write` bridge only.

Current capability:

- `SimpleAgentStepRunner`;
- tool policy;
- approval pending/granted;
- `archive_write`;
- trace events.

Design direction:

Phase 14 is deliberately narrow. It should keep `archive_write` as the only
supported kernel tool and add a post-action verification event proving that the
approved write produced durable store state and later v3 context eligibility:

```text
observe context
-> request archive_write
-> policy decision
-> approval if required
-> execute
-> verify store/history/archive attachment/context eligibility
-> trace result
```

Do not add `recall_search`, `archive_search`, `core_memory_update`, or
destructive memory tools in this phase unless RED evidence proves the narrow
verification loop is demo-only.

Required tests:

- opt-in kernel remains off by default;
- policy denies unsupported tools;
- approval replay cannot be tampered with;
- approval replay is bound to the original pending `step_id` and stable
  tool-call identity or request fingerprint;
- approved `archive_write` emits `tool_executed` followed by `tool_verified`;
- `tool_verified` inspects real store state, archival history, same-session
  archive attachment, and v3 archival eligibility;
- verification failure emits a durable negative verification event and cannot be
  counted as a successful memory action;
- tool-return messages include enough verification summary for replay
  idempotency checks without reusing gold benchmark fields;
- unsupported tools and tampered approval replays emit neither `tool_executed`
  nor `tool_verified`.

Eval gate:

- focused kernel tests;
- default-kernel-off LoCoMo 30 and LongMemEval 30 if the agent-loop changes
  touch default context, retrieval, or public benchmark paths;
- opt-in kernel 5-case smoke for trace/control-plane verification;
- no 50-case kernel run unless default-kernel-off 30-case gates are stable and
  God explicitly records why larger kernel evidence is needed.

ACK gate:

- kernel default remains off;
- every mutation has policy, approval/source refs, and trace;
- K0 records are sufficiently stable for replay and later tool routing;
- one approved `archive_write` can be verified through the real store and later
  v3 context eligibility;
- no benchmark improvement claim is made from this structural kernel phase.

## Phase 15 - Hybrid Tool Selection And Diagnostic Maintenance Planner

Target state: `hybrid-selection-and-diagnostic-planner-ready`.

Purpose:
implement K2 hybrid tool selection before allowing K4 planner proposals: the
kernel must first prove that a deterministic candidate router, constrained LLM
selector, schema/policy validation, and deterministic fallback cannot execute
out-of-scope tools. Only after that gate may public benchmark failure
diagnostics produce safe, reviewable kernel memory action proposals without
executing broad autonomous memory edits.

K2-first requirements:

- kernel enabled implies hybrid tool selection is on by default internally;
- deterministic routing declares allowed candidates and constraints;
- the LLM may select only from declared candidates or select no tool;
- invalid output, unavailable LLM, timeout, missing provenance, or policy denial
  falls back deterministically or stops without mutation;
- selection traces record `selection_origin` and `candidate_reason`;
- no maintenance planner proposal may be executable until these requirements
  have focused tests.

Current bottleneck:

- LoCoMo can pass under LLM judge even when source localization is weak.
- `source_hit=false` with `judge_pass` must be treated as a grounding risk, not
  a retrieval success.
- `retrieval_miss` and `evidence_hit_answer_fail` need different maintenance
  responses.

Design direction:

The planner observes case-level diagnostics and emits candidate tool requests:

```text
public case diagnostics, split into eval-only and model-visible fields
-> failure-class router for workflow selection only
-> candidate maintenance action
-> policy/approval gate
-> no execution unless explicitly run through kernel
```

Initial action types:

- `retrieval_repair_note` for retrieval/session localization misses;
- `archive_write` evidence summary for evidence-hit-answer-fail cases;
- `grounding_risk` trace for judge-pass/source-miss cases;
- `core_promotion_request` only as a pending candidate, never as direct core
  mutation.

Gold-boundary rule:

- `expected_source_ids`, expected answers, and gold-derived target ids must not
  appear in proposal content, tool arguments, source refs, archive ids, passage
  links, or promotion candidates;
- if the planner cannot create a proposal from model-visible traces alone, it
  must emit a diagnostic-only denial with the missing model-visible evidence.

Required tests:

- deterministic candidate generation and fallback are reproducible;
- a constrained LLM selector cannot choose an unregistered/non-candidate tool;
- tool-selection inputs do not contain expected answers, expected source ids,
  judge labels, or gold-derived repair targets;
- `retrieval_miss` produces a repair proposal with expected/retrieved source
  ids only in the eval sidecar; the executable proposal itself contains no
  expected-source or expected-answer leakage;
- `evidence_hit_answer_fail` produces a source-backed evidence-summary
  proposal;
- `judge_pass` plus `source_hit=false` produces a grounding-risk trace/proposal
  and is not counted as retrieval success;
- planner output is deterministic and does not execute tools by itself.
- every executable proposal records `gold_fields_used=false`, while every
  gold-dependent proposal is denied as diagnostic-only.

Eval gate:

- focused planner tests;
- fixed 5/10-case LoCoMo diagnostic replay proving proposed actions match
  failure classes;
- no pass-rate improvement claim unless a later eval consumes the maintenance
  artifacts through the real context path.

ACK gate:

- K2 selection is bounded, traceable, and fail-closed;
- every proposal has source refs or an explicit denial reason;
- no proposal uses expected-answer leakage;
- source localization and judge outcome remain separately reported;
- kernel default remains off.

## Phase 16 - Kernel Maintenance Tool Surface

Target state: `kernel-maintenance-tools-usable`.

Purpose:
implement K3 by adding the minimum Letta-style memory tools needed for the
diagnostic planner while preserving approval, provenance, replay safety, and
default-off kernel behavior.

Allowed tools by graduation level:

- Level 1: `archive_write`, `archive_attach`, `core_promotion_request`;
- Level 2: `recall_search`, `archive_search`;
- Level 3, only after separate safety gate: `core_memory_append`,
  `core_memory_replace`.

Maintenance artifacts may include a diagnostic-only `retrieval_repair_note`,
but it is not user-facing memory and cannot bypass the registered Level 1-3
tool/service contracts to alter retrieval visibility.

Not allowed:

- unapproved direct core edits or direct `core_memory_update` from the kernel;
- destructive delete/deprecate tools;
- direct `passage_link` mutations that bypass a named lifecycle/archival
  service and scope verification;
- benchmark case-id hacks;
- expected-answer-derived memory writes.

Required tests:

- every write tool requires approval or strong source refs;
- unsupported/destructive tools fail closed;
- replay tampering cannot execute or verify a write;
- each successful tool has durable history and a `tool_verified` event;
- v3 composer can see only the artifacts that are eligible by scope.
- each tool maps to an explicit service method before implementation; no new
  tool may bypass `MemoryLifecycleService`, `CoreMemoryService`, or a named
  archival/retrieval maintenance service with direct ad hoc store writes.

Eval gate:

- focused tool/kernel/store/context tests;
- opt-in kernel 5-case structural smoke only;
- default-kernel-off public reports remain unchanged.

ACK gate:

- each opened tool level has registry, policy, named executor/service,
  verification, trace, and integration coverage;
- tool execution is auditable and replay-safe;
- maintenance writes are visible to v3 only through scope/provenance rules;
- kernel remains opt-in.

## Phase 17 - LoCoMo Maintenance Repair Eval

Target state: `locomo-maintenance-repair-measured`.

Purpose:
execute the K4 evaluation slice: prove whether kernel-created maintenance
artifacts improve LoCoMo source localization and answer quality when consumed
through the real v3 context path, without converting repair smoke into
promotion evidence.

Required evaluation pattern:

```text
baseline fixed LoCoMo slice
-> diagnostic planner proposals from model-visible fields only
-> approved maintenance writes in an isolated repair-smoke store
-> rerun same fixed LoCoMo slice as structural smoke only
-> freeze generic rules and maintenance artifacts
-> run clean held-out LoCoMo validation before any quality claim
```

Primary metrics:

- `source_hit`;
- `planned_evidence_source_hit_at_5`;
- `episode_source_hit_at_10`;
- source-miss judge-pass count;
- `retrieval_miss` to downstream-failure conversion;
- pass-to-fail and fail-to-pass lists.

Eval gate:

- fixed LoCoMo 10-case same-subset full-chain LLM judge;
- same-slice movement can satisfy only the repair-smoke gate, not promotion;
- LoCoMo 30-case full-chain LLM judge only from a clean store or held-out
  validation setup after the fixed-slice source movement is useful and
  explainable;
- LongMemEval 30-case regression guard if maintenance artifacts affect default
  v3 context selection.

ACK gate:

- source localization improves or failure classes become more precise;
- no hidden source-grounding regression;
- LoCoMo is reported separately from LongMemEval;
- kernel default remains off unless explicitly approved by the user after
  larger evidence.

## Phase 18 - Benchmark Governance And Promotion

Target state: `governed-promotion-ready`.

Purpose:
execute K5 governance and prevent accidental promotion from noisy aggregate
improvements.

Required gates:

- no-LLM structural smoke for wiring;
- full-chain LLM answer/judge for quality;
- LongMemEval 50 full-chain LLM judge;
- LoCoMo 50 full-chain LLM judge;
- same-case comparison;
- pass-to-fail list;
- fail-to-pass list;
- retrieval/source metrics separate from judged answer quality;
- invalid artifact quarantine;
- phase ACK only after review verdict passes.

Minimum promotion thresholds relative to accepted phase-8/phase-10 baselines:

- no same-case LoCoMo pass-to-fail remains unexplained;
- LoCoMo source localization does not regress, including source-miss
  judge-pass cases;
- LoCoMo judged pass rate and source-grounded pass rate are reported separately;
- LongMemEval 50 does not materially regress from the accepted phase-8 baseline
  without an explicit hold decision;
- any improvement claim must be supported by held-out or clean-store evidence,
  not only same-slice maintenance repair.

Promotion decisions:

- `continue_targeted`: a layer-specific bottleneck remains.
- `expand_eval`: 30/50-case evidence is stable enough for larger samples.
- `hold`: aggregate improved but source grounding or regressions are unsafe.
- `promote_blueprint`: root blueprint/config should be updated after review.

ACK gate:

- LongMemEval and LoCoMo are both reported;
- LoCoMo is not hidden by LongMemEval;
- kernel default remains unchanged;
- v1 fallback remains explicit;
- next blueprint decision is backed by case-level evidence.

## Current Continuation Step

Phase 13 is completed and ACKed. Continue with Phase 14 as already planned:
opt-in kernel memory-action verification. Do not broaden Phase 14 into a full
agent loop. Phase 14 should now be read as the K0/K1 minimum slice from the
kernel graduation blueprint.

After Phase 14 is usable, continue to the kernel graduation sequence:

1. Phase 15: K2 hybrid tool selection, then diagnostic maintenance planner.
2. Phase 16: K3 graduated kernel maintenance tool surface.
3. Phase 17: K4 LoCoMo maintenance repair smoke and validation setup.
4. Phase 18: K5 benchmark governance and promotion decision.

The old governance phase is intentionally delayed until kernel maintenance has
either improved LoCoMo source localization or shown, with evidence, that this
path is not useful.

Recommended first fixed LoCoMo slice:

- retrieval/session misses:
  `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`,
  `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`,
  `conv-26_qa_025`, `conv-26_qa_050`.
- evidence-hit-answer-fail:
  `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_033`,
  `conv-26_qa_041`, `conv-26_qa_048`.

The first implementation should target the largest repeated failure class found
by replay, not the easiest code path.

## Minimum Next Dispatch

When this promoted blueprint starts, the first `god_dispatch.json` should target
Phase 9 and must include these read-first files:

- `xmuse/state.json`
- `xmuse/blueprint.md`
- `xmuse/config.json`
- `xmuse/work/phase-8/ack.json`
- `xmuse/work/phase-8/promotion_decision.md`
- `xmuse/work/phase-8/blueprint_amendment.md`
- `xmuse/work/phase-8/god_context.md`
- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/diagnostic_report.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_context_composer.py`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`

Before executing Phase 14, God must promote the execute lane from Phase 13 ACK
to Phase 14 EXECUTE and read:

- `work/phase-14/context_bundle.md`;
- `work/phase-14/god_dispatch.json`;
- `work/phase-14/plan_final.md`;
- `work/phase-13/ack.json`;
- this updated root blueprint.

Phase 14 must not change answer or retrieval behavior. It should only verify
the opt-in kernel memory-action loop and leave default public benchmark runs
kernel-off.


## Stop Conditions

God must pause or adjust instead of advancing when:

- a phase is only plan-only, demo-only, or partial;
- a lane output ignored or contradicted `context_bundle.md` without evidence;
- tests pass but the real benchmark path is not wired;
- pass rate improves while evidence/source grounding regresses;
- LoCoMo regresses or remains unexplained;
- LLM judge is unavailable for a mandatory milestone and no equivalent evidence
  exists;
- review identifies benchmark leakage or case-id overfitting;
- v1 fallback or kernel opt-in is broken.

## Expected Outcome

The expected result is not a guaranteed benchmark score. The expected result is
a MemoryOS Lite v3 chain where each LongMemEval/LoCoMo failure can be explained
as retrieval, evidence planning, context packaging, answer projection, kernel
control, or judge instability, and where subsequent score improvements are
supported by case-level source-grounded evidence.
