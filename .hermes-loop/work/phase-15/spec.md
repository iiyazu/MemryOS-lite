# phase: phase-15

# Phase 15 Spec: Hybrid Selection Boundary And Diagnostic Planner Readiness

## Basis And Active Goal

This specification is derived from `work/phase-15/context_bundle.md` (repository
path `.hermes-loop/work/phase-15/context_bundle.md`),
`work/phase-15/god_dispatch.json`, and `work/phase-15/brainstorm.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory
> system for LongMemEval and LoCoMo, without demo-only phase completion,
> without hiding case-level regressions, and without enabling the v3 kernel by
> default.

Observed real-path facts that constrain this specification:

- `SimpleAgentStepRunner.run_step()` currently sends caller-supplied
  `ToolExecutionRequest` objects directly to policy, approval, execution, and
  verification.
- `src/memoryos_lite/evals.py` creates the opt-in public benchmark
  `archive_write` probe and resumes its approval flow.
- `ToolExecutionRequest` does not yet carry the K2 selection identity or
  provenance needed to bind approval replay to selection.
- `build_case_diagnostics()` currently returns a report object containing
  gold-bearing and model-visible fields together.

## Chosen Design

Phase 15 uses a **K2-first small helper/router/selector boundary**, with
diagnostic planner proposals **conditional after focused K2 tests pass**.

The mandatory slice is a focused `agent_tool_selection.py` helper used by the
real opt-in `SimpleAgentStepRunner.run_step()` path. It converts incoming tool
requests into declared candidates, permits selection of exactly one declared
candidate or no-op, rejects invalid selector outcomes before policy or
execution, and passes a selected request through the already-audited Phase 14
policy, approval, execution, verification, tool-return, and durable trace
path.

The helper is intentionally not a general tool registry. The only Phase 15
write candidate is the already-existing `archive_write` bridge. Phase 16 owns
additional memory tools and domain service contracts.

Only after the K2 gate is green may this phase add a diagnostic-only planner
artifact boundary. The planner consumes an allow-listed, model-visible input,
emits reviewable proposal objects, and stores benchmark gold and outcome
labels only in a separate eval sidecar. Producing a proposal does not execute
a tool.

## Preserved Defaults And Invariants

- `MEMORYOS_MEMORY_ARCH=v3` remains the default context architecture.
- `MEMORYOS_MEMORY_ARCH=v1` remains an explicit supported fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in; Phase 15 must not enable it by
  default or change default public benchmark kernel behavior.
- SQLite remains the authoritative current store and trace persistence path.
- Letta remains a design reference only; no Letta runtime dependency is added.
- Existing `policy -> approval -> execution -> verification -> tool return`
  semantics remain authoritative after a valid selection.
- Default kernel-off public benchmark runs remain maintenance-write-free and
  kernel-trace-free.
- This phase makes no benchmark improvement claim.

## Scope

Mandatory K2 scope:

- Add K2 request/candidate/selection contracts.
- Add one focused selection helper with deterministic routing and an injectable
  selector protocol.
- Route real `SimpleAgentStepRunner.run_step()` tool requests through that
  boundary before policy.
- Persist candidate and selection provenance in kernel trace events.
- Bind approval pending/resume to the selected stable `tool_call_id` as well
  as the existing request fingerprint.
- Carry the bound call id through the opt-in public benchmark kernel probe.
- Add focused tests for valid selection, invalid/non-candidate selection,
  no-op failure behavior, replay binding, and public default-off behavior.

Conditional planner scope, admitted only after mandatory K2 tests pass:

- Create a small public maintenance planner helper that accepts explicitly
  separated model-visible input and eval-only sidecar values.
- Attach proposal/sidecar artifacts to public diagnostic output without
  changing answer, judge, retrieval, context selection, or score computation.
- Test that no gold-only field can enter proposal payloads, tool arguments, or
  source refs.

Verified but unchanged unless RED evidence demonstrates a narrow need:

- v3 context composition and archival eligibility.
- retrieval and answer projection.
- store trace persistence APIs.
- configuration defaults and v1 fallback.

## K2 Contracts

Contracts belong in `src/memoryos_lite/v3_contracts.py` unless noted
otherwise.

### Selection Origin

`ToolSelectionOrigin` is:

```python
Literal["deterministic", "llm", "fallback"]
```

`deterministic` is the default local selector, `llm` identifies a future or
test-injected constrained selector result, and `fallback` identifies fail-closed
resolution to no-op after selector failure or invalid output.

### Tool Candidate

`ToolCandidate` is an immutable candidate-plane representation, not an
execution grant:

```python
class ToolCandidate(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    source_refs: list[SourceRef] = Field(default_factory=list)
    candidate_reason: str
    constraints: dict[str, Any] = Field(default_factory=dict)
```

Required Phase 15 semantics:

- The deterministic router declares candidates only for `archive_write`.
- A candidate records `candidate_reason` and constraints including its
  provenance/approval requirement.
- Unsupported input tool names are recorded as rejected input and never
  become candidates.
- A fresh candidate receives a stable generated `tool_call_id`; an approval
  resume may carry only the previously persisted matching id.

### Selection Choice

`ToolSelectionChoice` is selector output:

```python
class ToolSelectionChoice(BaseModel):
    tool_call_id: str | None = None
    selection_origin: ToolSelectionOrigin
    reason: str
```

`tool_call_id=None` is an explicit no-op. A non-null id is valid only when it
exactly matches one generated candidate for the current step input.

### Selected Execution Request

`ToolExecutionRequest` remains the request consumed by policy and execution,
extended with optional K2 provenance:

```python
tool_call_id: str | None = None
selection_origin: ToolSelectionOrigin | None = None
candidate_reason: str | None = None
```

Caller input is not considered selected merely because these properties are
present. Only the K2 boundary may return the selected request processed by the
runner.

### Helper Boundary

Create `src/memoryos_lite/agent_tool_selection.py` with these responsibilities:

```python
class ToolSelector(Protocol):
    def select(
        self,
        request: AgentStepRequest,
        candidates: list[ToolCandidate],
    ) -> ToolSelectionChoice: ...


class DeterministicToolSelector:
    # Select the sole valid candidate; otherwise return explicit no-op.


class ToolSelectionBoundary:
    def resolve(
        self,
        request: AgentStepRequest,
        tool_requests: list[ToolExecutionRequest],
    ) -> ToolSelectionResolution: ...
```

`ToolSelectionResolution` is helper-local and returns:

- generated candidates;
- rejected-input diagnostics;
- the accepted selected `ToolExecutionRequest`, or `None`;
- a trace-ready selection payload and denial reason when selection fails.

The boundary catches selector exception/timeout/unavailable behavior, invalid
schema, non-candidate ids, duplicate supplied call ids, and missing selected
provenance. Such outcomes resolve to no selected request; they never fall
back to an executable `archive_write`.

## K2 Data Flow

For `MEMORYOS_AGENT_KERNEL=v1` only:

```text
SimpleAgentStepRunner.run_step(request, tool_requests)
-> kernel_step_started
-> ToolSelectionBoundary.resolve(...)
   -> deterministic candidate generation for supported archive_write input
   -> constrained selector chooses declared candidate or no-op
   -> selected request gains tool_call_id, selection_origin, candidate_reason
-> tool_candidates_generated persisted with candidate_reason/constraints
-> tool_selected persisted for a valid selected request
   OR tool_selection_denied persisted for fail-closed/no-op resolution
-> only a valid selected request enters existing policy/approval path
-> tool_policy_decision -> approval -> execution -> verification -> tool return
-> kernel_step_completed
```

Approval resume data flow:

```text
selected archive_write requires approval
-> approval_pending metadata persists tool_call_id and request_fingerprint
-> caller/public probe resumes with approval_id plus the persisted tool_call_id
-> K2 regenerates the matching selected request
-> replay check compares approval_id, tool_call_id, fingerprint, session,
   tool name, arguments, and source refs
-> mismatch emits approval_replay_denied and performs no mutation
```

The current public benchmark real-path integration therefore includes the
narrow update in `src/memoryos_lite/evals.py` needed to carry the pending
selection identity when it resumes the opt-in probe.

## Failure Handling

| Condition | Required behavior | Mutation permitted |
|---|---|---|
| No tool requests | Start/completed trace only, as today. | No |
| Supported request and deterministic selection | Trace candidates/selection, then use existing policy path. | Only after existing approval/execution/verification contract |
| Explicit selector no-op | Trace candidates and no-op selection/denial; do not call policy. | No |
| Selector chooses unknown or non-candidate id/tool | Emit `tool_selection_denied`; do not call policy or executor. | No |
| Selector malformed output, exception, timeout, or unavailable dependency | Record fallback origin and denial; do not choose a default write. | No |
| Duplicate/conflicting supplied `tool_call_id` | Deny before policy. | No |
| Selected candidate lacks required source provenance and has no bound approval path | Deny before execution; it must not become a write. | No |
| Policy denies selected candidate | Preserve existing `tool_policy_decision` and `tool_denied`. | No |
| Approval replay id/fingerprint/call binding differs | Preserve durable `approval_replay_denied`. | No |
| Execution verification fails | Preserve durable negative `tool_verified`; no successful tool-return evidence. | No successful mutation claim |

## Trace Contract

Mandatory new trace events are durable through the same `store.add_trace()`
path already used by the kernel:

- `tool_candidates_generated`: ordered candidate summaries, rejected input
  summaries, `tool_call_id`, `tool_name`, `candidate_reason`, and constraints.
- `tool_selected`: selected `tool_call_id`, `tool_name`,
  `selection_origin`, and `candidate_reason`.
- `tool_selection_denied`: failure reason, `selection_origin="fallback"` for
  invalid selector resolution, and no executable request.

For a valid selected tool, these events occur before
`tool_policy_decision`. Existing approval, execution, verification, replay,
and completion events remain durable and ordered after selection.

## Eval-Gold Sidecar Boundary

Conditional planner work is permitted only after focused K2 tests and public
kernel default-off tests are green.

Create `src/memoryos_lite/public_maintenance_planner.py` only in that
conditional slice. It must define separated inputs and outputs:

```python
class ModelVisiblePlannerInput(BaseModel):
    question: str
    rendered_answer: str
    selected_context_ids: list[str]
    final_context_trace_source_ids: list[str]
    rendered_evidence_ids: list[str]
    answer_evidence: list[dict[str, object]]
    cited_source_ids: list[str]
    unsupported_citation_ids: list[str]
    citation_contract_status: str
    archival_eligibility: dict[str, object]
    component_drop_counts: dict[str, object]
    kernel_trace_events: list[dict[str, object]]


class EvalGoldSidecar(BaseModel):
    case_id: str
    expected_answer: str
    expected_source_ids: list[str]
    verdict: str
    judge_status: str
    failure_class: str
    movement_status: str


class MaintenanceProposal(BaseModel):
    proposal_type: Literal["archive_write", "grounding_risk", "diagnostic_only_denial"]
    execution_mode: Literal["proposal_only"] = "proposal_only"
    tool_name: Literal["archive_write"] | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    gold_fields_used: Literal[False] = False
    denial_reason: str | None = None
```

Rules:

- The planner function receives `ModelVisiblePlannerInput` for proposal
  construction. It may attach `EvalGoldSidecar` for reporting, but may not
  read the sidecar to build executable payloads or source refs.
- `expected_answer`, `expected_source_ids`, overlap with expected sources,
  judge labels/reasoning, gold-derived `failure_class`, movement labels, and
  case-specific repair ids remain sidecar-only.
- A source-backed `archive_write` proposal may be emitted only from real
  rendered/context evidence and real source refs already visible in the model
  plane. It remains `proposal_only` and is not automatically sent to K2.
- A gold-detected `judge_pass` plus source miss may be represented as a
  sidecar/report `grounding_risk`; it cannot authorize a write proposal.
- When model-visible evidence is inadequate, output is a
  `diagnostic_only_denial`, with `gold_fields_used=false`.
- Public output may add planner artifacts, but it must not replace or aggregate
  away case-level source localization and judge outcome fields.

## Non-Goals

- No default-on kernel or default public maintenance writes.
- No `core_memory_append`, `core_memory_replace`, `archive_attach`,
  `core_promotion_request`, retrieval repair execution, or destructive tools.
- No Letta dependency or copied Letta runtime.
- No change to default retrieval, v3 composition, answer projection, judging,
  or scoring behavior.
- No benchmark-derived tool arguments, source refs, archive ids, passage
  links, promotion candidates, or memory contents.
- No same-slice repair write treated as quality or promotion evidence.
- No aggregate-only reporting that hides individual LoCoMo failures or
  source-miss/judge-pass grounding risk.

## Acceptance Criteria

Mandatory K2 acceptance:

- The K2 boundary is used from the real `SimpleAgentStepRunner.run_step()`
  path and therefore by the opt-in public benchmark kernel probe.
- The deterministic router exposes only `archive_write` candidates in this
  phase and records `candidate_reason`.
- A selector can choose only a declared candidate or no-op; invalid,
  unavailable, timed-out, missing-provenance, duplicate-id, and non-candidate
  outcomes fail closed without memory mutation.
- `tool_candidates_generated`, `tool_selected`, and denial traces are persisted
  with `selection_origin` and `candidate_reason` where applicable.
- Approval replay is bound to persisted `tool_call_id` and request
  fingerprint; the public probe carries that binding on resume.
- Existing policy, approval, execution, negative verification, and durable
  tool-return behavior remains in force after a valid selection.
- Tests prove default public reports remain kernel-off unless
  `MEMORYOS_AGENT_KERNEL=v1` is explicitly configured.
- Tests retain coverage that v3 is default and v1 remains an explicit
  fallback.

Conditional planner acceptance:

- Planner code is not added or counted complete unless mandatory K2 focused
  tests have passed first in execution evidence.
- Planner proposal construction accepts only explicit model-visible input;
  eval gold is attached only in a separate sidecar.
- Tests prove gold-bearing fields do not appear in proposal content,
  arguments, source refs, archive ids, or candidate ids.
- Every proposal has `gold_fields_used=false`, is `proposal_only`, and either
  has model-visible source grounding or an explicit denial reason.
- Case-level LoCoMo source localization and judge outcomes remain separately
  reportable.

Review acceptance:

- Review cites `work/phase-15/context_bundle.md` and this active goal.
- Focused kernel and public boundary tests are required evidence.
- A fixed diagnostic replay is allowed only if conditional planner/report
  artifacts are added, and is structural evidence rather than a quality claim.
- No benchmark improvement, promotion, or kernel-default claim is made by
  Phase 15.
