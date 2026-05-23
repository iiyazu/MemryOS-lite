# phase: phase-15

# Hybrid Selection Boundary And Diagnostic Planner Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` by default to implement this plan
> task-by-task with review between tasks. Use
> `superpowers:verification-before-completion` before claiming completion.

**Goal:** Implement and prove the minimal K2 hybrid selection boundary for the
real opt-in MemoryOS v3 kernel path, then admit only non-executing,
source-grounded diagnostic planner artifacts whose benchmark gold remains in
an eval-only sidecar.

**Architecture:** Route caller-supplied kernel tool requests through a new
small `ToolSelectionBoundary` before the existing audited policy/approval/
execution/verification path. Keep `archive_write` as the only K2 candidate,
carry stable selected-call provenance through approval replay, and condition
any planner/report artifact work on a green K2 gate.

**Tech Stack:** Python 3.11+, Pydantic models, existing SQLite-backed
`MemoryStore`, `pytest`, `ruff`, existing public benchmark harness.

**Basis:** `work/phase-15/context_bundle.md`, the active goal stated in that
bundle, `work/phase-15/god_dispatch.json`, and
`work/phase-15/brainstorm.md`.

**Constraint:** This plan must preserve v3 default, v1 fallback, and
`MEMORYOS_AGENT_KERNEL=v1` opt-in. It does not claim benchmark improvement and
does not set benchmark score targets.

---

## Execution Choice

Use subagent-driven execution by default. The mandatory tasks have strict
ordering: RED tests define the boundary, contracts/helper enable runner
integration, and the public replay update depends on the selected-call
contract. They should therefore be dispatched one at a time with review after
each task, not run concurrently. The conditional planner tasks are an
independent follow-on only after the K2 verification gate is green; they may
receive a fresh subagent after that gate.

## File Map

Mandatory production files:

- Modify: `src/memoryos_lite/v3_contracts.py` - K2 candidate, choice, origin,
  and selected-request provenance contracts.
- Create: `src/memoryos_lite/agent_tool_selection.py` - the small
  deterministic router/selector/validation boundary.
- Modify: `src/memoryos_lite/agent_kernel.py` - invoke K2 before policy,
  persist selection traces, and enforce replay binding.
- Modify: `src/memoryos_lite/evals.py` - resume the real opt-in public kernel
  probe with persisted `tool_call_id`.

Mandatory test files:

- Modify: `tests/test_agent_kernel.py` - K2 RED/GREEN, fail-closed, replay, and
  trace-order coverage.
- Modify: `tests/test_public_benchmarks.py` - public default-off preservation
  and opt-in trace/binding coverage.
- Verify unchanged: `tests/test_context_composer.py` - existing v3 default,
  v1 fallback, and kernel flag coverage.

Conditional planner files, only after the K2 gate passes:

- Create: `src/memoryos_lite/public_maintenance_planner.py` - separated
  model-visible input, eval-only sidecar, and proposal-only output.
- Modify: `src/memoryos_lite/public_benchmarks.py` - attach planner artifacts
  to case-level report output without replacing existing diagnostics.
- Modify: `tests/test_public_benchmarks.py` - leakage, deterministic proposal,
  and case-level grounding-risk report coverage.

Explicitly unchanged in this phase unless a RED failure proves the stated
narrow need:

- `src/memoryos_lite/config.py`;
- `src/memoryos_lite/store.py`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/public_case_diagnostics.py`;
- retrieval and answer-projection modules;
- all `docs/`, Hermes state, and benchmark report files.

## Task 1: RED - Freeze The K2 Boundary In Focused Kernel Tests

**Files:**

- Modify: `tests/test_agent_kernel.py`

- [ ] **Step 1: Add imports and selector fakes that describe the required K2 API.**

```python
from memoryos_lite.agent_tool_selection import ToolSelectionBoundary
from memoryos_lite.v3_contracts import ToolSelectionChoice


class _NonCandidateSelector:
    def select(self, request, candidates):
        return ToolSelectionChoice(
            tool_call_id="toolcall_not_declared",
            selection_origin="llm",
            reason="attempted invented tool selection",
        )


class _InvalidSelector:
    def select(self, request, candidates):
        raise TimeoutError("selector timeout")
```

- [ ] **Step 2: Add a failing test proving candidate trace ordering before policy.**

```python
def test_kernel_generates_candidate_trace_before_selection(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    result = _approval_runner(store).run_step(
        _request(),
        tool_requests=[_archive_request()],
    )

    event_types = [event.event_type for event in result.trace]
    assert event_types[:4] == [
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
    ]
    selected = next(event for event in result.trace if event.event_type == "tool_selected")
    assert selected.payload["selection_origin"] == "deterministic"
    assert selected.payload["candidate_reason"]
    assert selected.payload["tool_call_id"].startswith("toolcall_")
```

- [ ] **Step 3: Add failing tests proving non-candidate and selector failure resolve before policy or mutation.**

```python
def test_kernel_denies_selector_non_candidate_without_policy_or_execution(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(store)
    runner.tool_selection_boundary = ToolSelectionBoundary(selector=_NonCandidateSelector())

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    event_types = [event.event_type for event in result.trace]
    assert "tool_candidates_generated" in event_types
    assert "tool_selection_denied" in event_types
    assert "tool_policy_decision" not in event_types
    assert "tool_executed" not in event_types
    assert _archival_memory_count(store) == 0


def test_kernel_selector_invalid_output_falls_back_to_noop_without_mutation(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(store)
    runner.tool_selection_boundary = ToolSelectionBoundary(selector=_InvalidSelector())

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    denial = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert denial.payload["selection_origin"] == "fallback"
    assert "timeout" in denial.payload["reason"]
    assert "tool_policy_decision" not in [event.event_type for event in result.trace]
    assert _archival_memory_count(store) == 0
```

- [ ] **Step 4: Add a failing test proving selected provenance and approval replay binding survive the cold boundary.**

```python
def test_kernel_selected_request_carries_selection_origin_and_candidate_reason(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    pending = next(event for event in first.trace if event.event_type == "approval_pending")
    tool_call_id = pending.payload["metadata"]["tool_call_id"]
    assert tool_call_id.startswith("toolcall_")

    resumed = _approval_runner(create_store(settings)).run_step(
        _request(),
        tool_requests=[
            _archive_request(
                approval_id=pending.approval_id,
                tool_call_id=tool_call_id,
            )
        ],
    )
    selected = next(event for event in resumed.trace if event.event_type == "tool_selected")
    assert selected.payload["tool_call_id"] == tool_call_id
    assert selected.payload["selection_origin"] == "deterministic"
    assert selected.payload["candidate_reason"]
    assert "approval_granted" in [event.event_type for event in resumed.trace]
```

Update `_archive_request()` in the test file to accept
`tool_call_id: str | None = None` and pass it into `ToolExecutionRequest`.
Extend the existing replay-tampering test so a changed `tool_call_id` produces
`approval_replay_denied`, no `tool_executed`, and no archival write.

- [ ] **Step 5: Run only the focused RED command in the EXECUTE lane.**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Expected before production edits: FAIL during import or assertions because the
K2 helper/contracts and selection trace events do not yet exist.

- [ ] **Step 6: Commit the RED tests after confirming they fail.**

```bash
git add tests/test_agent_kernel.py
git commit -m "test: define phase 15 kernel selection boundary"
```

## Task 2: GREEN - Add Minimal K2 Contracts And The Selection Helper

**Files:**

- Modify: `src/memoryos_lite/v3_contracts.py`
- Create: `src/memoryos_lite/agent_tool_selection.py`

- [ ] **Step 1: Add the public K2 contracts without opening additional tools.**

In `src/memoryos_lite/v3_contracts.py`, add the following coherent contract
shape and export the new types:

```python
ToolSelectionOrigin = Literal["deterministic", "llm", "fallback"]


class ToolCandidate(BaseModel):
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    source_refs: list[SourceRef] = Field(default_factory=list)
    candidate_reason: str = Field(min_length=1)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ToolSelectionChoice(BaseModel):
    tool_call_id: str | None = None
    selection_origin: ToolSelectionOrigin
    reason: str = Field(min_length=1)
```

Extend the existing request contract:

```python
class ToolExecutionRequest(BaseModel):
    session_id: str
    tool_name: str
    arguments: dict[str, Any]
    source_refs: list[SourceRef] = Field(default_factory=list)
    approval_id: str | None = None
    tool_call_id: str | None = None
    selection_origin: ToolSelectionOrigin | None = None
    candidate_reason: str | None = None
```

- [ ] **Step 2: Create the small boundary helper with fail-closed behavior.**

Create `src/memoryos_lite/agent_tool_selection.py` implementing these exact
roles:

```python
@dataclass(frozen=True)
class ToolSelectionResolution:
    candidates: list[ToolCandidate]
    rejected_inputs: list[dict[str, Any]]
    selected_request: ToolExecutionRequest | None
    selection_payload: dict[str, Any]
    denied: bool


class ToolSelector(Protocol):
    def select(
        self,
        request: AgentStepRequest,
        candidates: list[ToolCandidate],
    ) -> ToolSelectionChoice: ...


class DeterministicToolSelector:
    def select(self, request, candidates):
        if len(candidates) != 1:
            return ToolSelectionChoice(
                tool_call_id=None,
                selection_origin="deterministic",
                reason="deterministic no-op: expected exactly one candidate",
            )
        return ToolSelectionChoice(
            tool_call_id=candidates[0].tool_call_id,
            selection_origin="deterministic",
            reason="deterministic sole candidate selection",
        )
```

`ToolSelectionBoundary.resolve()` must:

```python
ALLOWED_K2_TOOLS = {"archive_write"}

# For each allowed caller request:
# - retain a supplied tool_call_id only for approval-resume validation;
# - otherwise generate new_id("toolcall");
# - construct candidate_reason="existing archive_write bridge candidate";
# - record constraints requiring policy and source_refs-or-bound-approval.
#
# For unsupported requests:
# - record rejected_inputs; do not create a candidate.
#
# For selector errors, explicit no-op, ids outside candidates, duplicate ids,
# or a selected write that cannot meet source_refs-or-approval provenance:
# - return selected_request=None and denied=True;
# - report selection_origin="fallback" for invalid/error resolution;
# - never select archive_write as a fallback.
#
# For a valid choice:
# - return a copy of the candidate as ToolExecutionRequest with
#   tool_call_id, selection_origin, and candidate_reason populated.
```

The boundary does not call policy, approval, execution, the store, the LLM, or
public diagnostics.

- [ ] **Step 3: Run the focused contract/helper tests through the kernel test file.**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Expected at this intermediate point: K2 imports resolve, but selection-order
assertions still FAIL until the runner is wired through the helper.

- [ ] **Step 4: Commit the focused contract/helper implementation.**

```bash
git add src/memoryos_lite/v3_contracts.py src/memoryos_lite/agent_tool_selection.py
git commit -m "feat: add bounded kernel tool selection contracts"
```

## Task 3: GREEN - Wire Selection Into The Real Kernel And Approval Replay

**Files:**

- Modify: `src/memoryos_lite/agent_kernel.py`
- Modify: `tests/test_agent_kernel.py`

- [ ] **Step 1: Add the boundary dependency to the real runner.**

Change `SimpleAgentStepRunner` so the existing runner owns a default boundary:

```python
@dataclass
class SimpleAgentStepRunner:
    store: MemoryStore
    tool_policy_engine: SimpleToolPolicyEngine = field(default_factory=SimpleToolPolicyEngine)
    approval_gate: ApprovalGateV1 = field(default_factory=ApprovalGateV1)
    tool_execution_manager: SimpleToolExecutionManager | None = None
    tool_selection_boundary: ToolSelectionBoundary = field(default_factory=ToolSelectionBoundary)
```

- [ ] **Step 2: Resolve candidates once per step before the policy loop.**

Immediately after `kernel_step_started`, resolve `tool_requests or []` and
append durable trace entries before iterating any selected request:

```python
resolution = self.tool_selection_boundary.resolve(request, tool_requests or [])
trace.append(self._trace(
    step_id=step_id,
    session_id=request.session_id,
    sequence=sequence,
    event_type="tool_candidates_generated",
    payload={
        "candidates": [item.model_dump(mode="json") for item in resolution.candidates],
        "rejected_inputs": resolution.rejected_inputs,
    },
))
sequence += 1

if resolution.selected_request is None:
    if tool_requests:
        trace.append(self._trace(
            step_id=step_id,
            session_id=request.session_id,
            sequence=sequence,
            event_type="tool_selection_denied",
            payload=resolution.selection_payload,
        ))
        sequence += 1
    selected_requests = []
else:
    trace.append(self._trace(
        step_id=step_id,
        session_id=request.session_id,
        sequence=sequence,
        event_type="tool_selected",
        payload=resolution.selection_payload,
    ))
    sequence += 1
    selected_requests = [resolution.selected_request]
```

For backwards-compatible no-request behavior, do not emit candidate events
when `tool_requests` is empty; the existing no-tool trace test remains valid.
Replace the old policy iteration with `for tool_request in selected_requests`.

- [ ] **Step 3: Bind pending approval and replay checks to the selected call.**

When persisting `approval_pending`, include:

```python
"tool_call_id": tool_request.tool_call_id,
"selection_origin": tool_request.selection_origin,
"candidate_reason": tool_request.candidate_reason,
"request_fingerprint": self._request_fingerprint(tool_request),
```

Update `_request_fingerprint()` to include `tool_call_id`,
`selection_origin`, and `candidate_reason`. Replace the current unconditional
`tool_call_id mismatch` branch with an equality check:

```python
expected_tool_call_id = metadata.get("tool_call_id")
if expected_tool_call_id != request.tool_call_id:
    return None, self._replay_error(request, "tool_call_id mismatch")
```

Include the selected-call fields in `tool_selected`, approval, execution,
verification, denial, and tool-result metadata where a selected request
already exists. Do not weaken existing request/action/source replay checks.

- [ ] **Step 4: Adjust existing valid test expectations to include the two K2 events.**

For valid approval flows in `tests/test_agent_kernel.py`, the expected
selected path begins:

```python
[
    "kernel_step_started",
    "tool_candidates_generated",
    "tool_selected",
    "tool_policy_decision",
    "approval_pending",  # or approval_granted on resume
]
```

For an unsupported caller tool or a selector rejection, assert
`tool_policy_decision` is absent because it never becomes a K2 candidate.

- [ ] **Step 5: Run focused kernel GREEN verification.**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Expected: PASS, including fail-closed non-candidate/timeout/no-op tests,
selected provenance trace tests, replay tampering denial, and Phase 14
verification behavior.

- [ ] **Step 6: Commit the runner integration.**

```bash
git add src/memoryos_lite/agent_kernel.py tests/test_agent_kernel.py
git commit -m "feat: route kernel writes through constrained selection"
```

## Task 4: RED Then GREEN - Preserve The Real Public Kernel Boundary

**Files:**

- Modify: `tests/test_public_benchmarks.py`
- Modify: `src/memoryos_lite/evals.py`

- [ ] **Step 1: Update the opt-in public trace assertion before editing the real path.**

Leave `test_public_benchmark_kernel_trace_remains_default_off` unchanged.
Update `test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled` so both
approval steps assert:

```python
assert [event["event_type"] for event in kernel_trace_events] == [
    "kernel_step_started",
    "tool_candidates_generated",
    "tool_selected",
    "tool_policy_decision",
    "approval_pending",
    "kernel_step_completed",
    "kernel_step_started",
    "tool_candidates_generated",
    "tool_selected",
    "tool_policy_decision",
    "approval_granted",
    "tool_executed",
    "tool_verified",
    "kernel_step_completed",
]
pending_event = next(event for event in kernel_trace_events if event["event_type"] == "approval_pending")
selected_events = [event for event in kernel_trace_events if event["event_type"] == "tool_selected"]
assert pending_event["payload"]["metadata"]["tool_call_id"] == selected_events[0]["payload"]["tool_call_id"]
assert selected_events[1]["payload"]["tool_call_id"] == selected_events[0]["payload"]["tool_call_id"]
assert all(event["payload"]["candidate_reason"] for event in selected_events)
```

- [ ] **Step 2: Run public boundary tests to observe RED.**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected before editing `evals.py`: default-off remains PASS; opt-in FAILS
because approval resume does not yet carry the persisted `tool_call_id`.

- [ ] **Step 3: Carry the selection identity in the public probe resume.**

In `src/memoryos_lite/evals.py`, retrieve the selected call id from the
pending event and bind it into the resumed request:

```python
pending_event = next(
    (
        event for event in step.trace
        if event.event_type == "approval_pending" and event.approval_id
    ),
    None,
)
if step.continuation == "pause" and pending_event is not None:
    approval_id = pending_event.approval_id
    tool_call_id = pending_event.payload["metadata"]["tool_call_id"]
    resumed = service.agent_kernel.run_step(
        ...,
        tool_requests=[
            tool_request.model_copy(
                update={"approval_id": approval_id, "tool_call_id": tool_call_id}
            )
        ],
    )
```

Do not instantiate the kernel on default settings and do not change public
answer, judge, scoring, or case aggregation behavior.

- [ ] **Step 4: Run the public boundary GREEN verification.**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected: PASS; the default-off report still contains no kernel trace and the
opt-in real path now persists candidate/selected provenance across approval.

- [ ] **Step 5: Commit the real-path public probe binding.**

```bash
git add src/memoryos_lite/evals.py tests/test_public_benchmarks.py
git commit -m "feat: bind public kernel probe to selected tool call"
```

## Task 5: REFACTOR And K2 Admission Gate

**Files:**

- Review: `src/memoryos_lite/v3_contracts.py`
- Review: `src/memoryos_lite/agent_tool_selection.py`
- Review: `src/memoryos_lite/agent_kernel.py`
- Review: `src/memoryos_lite/evals.py`
- Review: `tests/test_agent_kernel.py`
- Review: `tests/test_public_benchmarks.py`
- Verify unchanged: `tests/test_context_composer.py`

- [ ] **Step 1: Refactor only duplicated trace payload construction or
  validation branching introduced by K2.**

Keep this refactor constrained:

```text
- one selection helper module;
- one selected-request path into existing policy;
- archive_write only;
- no planner types, tool registry, or new settings during K2 refactor.
```

- [ ] **Step 2: Run the mandatory K2 gate.**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q
```

Expected: all PASS. Required observed properties:

```text
- invalid/non-candidate selector output reaches neither policy nor execution;
- default public kernel trace remains empty;
- opt-in public trace includes candidate and selected provenance;
- v3 remains default and kernel remains off by default.
```

- [ ] **Step 3: Decide conditional planner admission from evidence.**

If any command above is not green, stop planner work and route failures to K2
repair/review. If all are green, admit Tasks 6-7. This is a scope gate, not a
benchmark-quality gate.

- [ ] **Step 4: Commit a K2-only refactor if it changed code.**

```bash
git add src/memoryos_lite/v3_contracts.py src/memoryos_lite/agent_tool_selection.py src/memoryos_lite/agent_kernel.py src/memoryos_lite/evals.py tests/test_agent_kernel.py tests/test_public_benchmarks.py
git commit -m "refactor: keep kernel selection boundary focused"
```

## Task 6: CONDITIONAL RED - Freeze The Planner Gold Boundary

**Gate:** Execute only after Task 5 K2 admission commands pass.

**Files:**

- Modify: `tests/test_public_benchmarks.py`

- [ ] **Step 1: Add RED tests for separated planner artifacts and zero tool execution.**

Write tests against the intended helper and public report API:

```python
from memoryos_lite.public_maintenance_planner import (
    EvalGoldSidecar,
    ModelVisiblePlannerInput,
    build_maintenance_artifact,
)


def test_planner_proposal_excludes_eval_gold_and_is_proposal_only():
    artifact = build_maintenance_artifact(
        model_visible=ModelVisiblePlannerInput(
            question="What is recorded?",
            rendered_answer="MemoryOS Lite [msg_selected]",
            selected_context_ids=["msg_selected"],
            final_context_trace_source_ids=["msg_selected"],
            rendered_evidence_ids=["msg_selected"],
            answer_evidence=[{"id": "msg_selected", "text": "MemoryOS Lite"}],
            cited_source_ids=["msg_selected"],
            unsupported_citation_ids=[],
            citation_contract_status="supported_cited_answer",
            archival_eligibility={},
            component_drop_counts={},
            kernel_trace_events=[],
        ),
        eval_sidecar=EvalGoldSidecar(
            case_id="case_gold",
            expected_answer="gold answer must not leak",
            expected_source_ids=["msg_gold"],
            verdict="fail",
            judge_status="judge_fail",
            failure_class="retrieval_miss",
            movement_status="unchanged_fail",
        ),
    )
    serialized_proposal = artifact.proposal.model_dump_json()
    assert artifact.proposal.execution_mode == "proposal_only"
    assert artifact.proposal.gold_fields_used is False
    assert "gold answer must not leak" not in serialized_proposal
    assert "msg_gold" not in serialized_proposal
    assert "msg_selected" in serialized_proposal
```

Add cases proving model-visible evidence absence yields
`diagnostic_only_denial`, and gold-derived judge-pass/source-miss
`grounding_risk` remains in the sidecar/report annotation rather than tool
arguments. Add a report test asserting planner artifact creation emits no
`tool_executed` trace.

- [ ] **Step 2: Run the planner RED subset.**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py -q
```

Expected before conditional production edits: FAIL because
`public_maintenance_planner.py` and planner artifact fields do not exist.

- [ ] **Step 3: Commit conditional RED tests after confirming failure.**

```bash
git add tests/test_public_benchmarks.py
git commit -m "test: define public planner gold sidecar boundary"
```

## Task 7: CONDITIONAL GREEN - Add Proposal-Only Planner Artifacts

**Gate:** Execute only after Task 6 tests are recorded RED and Task 5 remains
green.

**Files:**

- Create: `src/memoryos_lite/public_maintenance_planner.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] **Step 1: Implement separated planner data models and a model-visible-only builder.**

Create the exact public data boundary from `spec.md`:

```python
class ModelVisiblePlannerInput(BaseModel):
    question: str
    rendered_answer: str
    selected_context_ids: list[str] = Field(default_factory=list)
    final_context_trace_source_ids: list[str] = Field(default_factory=list)
    rendered_evidence_ids: list[str] = Field(default_factory=list)
    answer_evidence: list[dict[str, object]] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    unsupported_citation_ids: list[str] = Field(default_factory=list)
    citation_contract_status: str
    archival_eligibility: dict[str, object] = Field(default_factory=dict)
    component_drop_counts: dict[str, object] = Field(default_factory=dict)
    kernel_trace_events: list[dict[str, object]] = Field(default_factory=list)


class EvalGoldSidecar(BaseModel):
    case_id: str
    expected_answer: str
    expected_source_ids: list[str] = Field(default_factory=list)
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

`build_maintenance_artifact(model_visible, eval_sidecar)` must construct a
proposal from `model_visible` only. It may retain `eval_sidecar` as a separate
report property, but it must never use sidecar values in proposal arguments,
source refs, ids, or content. It returns `diagnostic_only_denial` when no real
selected/rendered evidence can support a proposal.

- [ ] **Step 2: Add planner artifacts to case reports without changing diagnostics semantics.**

In `src/memoryos_lite/public_benchmarks.py`:

```text
- add report fields for model_visible_planner_input, eval_gold_sidecar, and
  maintenance_proposal;
- build ModelVisiblePlannerInput from the already produced answer evidence,
  selected/rendered v3 context metadata, citations, eligibility, component
  drop counts, and kernel traces;
- build EvalGoldSidecar from report-only expected/outcome values;
- preserve existing case_diagnostics, source_hit, failure_class, judge_status,
  and movement_status fields unchanged;
- do not call SimpleAgentStepRunner or create ToolExecutionRequest from a
  proposal.
```

- [ ] **Step 3: Run conditional planner tests and mandatory K2 regression checks.**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py -q
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q
```

Expected: PASS; proposal payloads are sidecar-clean and proposal-only, while
K2/default-setting tests remain green.

- [ ] **Step 4: Commit conditional planner implementation.**

```bash
git add src/memoryos_lite/public_maintenance_planner.py src/memoryos_lite/public_benchmarks.py tests/test_public_benchmarks.py
git commit -m "feat: add diagnostic planner sidecar boundary"
```

## Task 8: Smoke, Review, And Eval Routing

**Files:**

- Review only: all files changed by the executed mandatory and admitted
  conditional tasks.
- Execution artifacts are owned by the later EXECUTE/REVIEW lane, not this
  PLAN_DRAFT lane.

- [ ] **Step 1: Run baseline verification after the implemented scope is stable.**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: PASS. Record actual counts and lint output; do not reuse prior phase
counts as Phase 15 evidence.

- [ ] **Step 2: Route evaluation according to the code actually changed.**

K2-only completion:

```text
Review scope: smoke.
Reason: only the explicitly enabled kernel selection/trace/replay path changed;
default public retrieval, context, answer, judge, and scoring did not change.
No public benchmark quality claim is allowed.
```

Conditional planner/report completion:

Run a diagnostic-only LoCoMo replay:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

Expected: report artifacts are emitted case-by-case, retain separate source
localization and judge/outcome fields, and contain no executable gold leakage.
This is structural smoke evidence only.

Escalated review routing:

```text
If execution changes default retrieval, context composition, answer
projection, judge behavior, or public scoring beyond this plan, stop and route
to review for parallel LongMemEval and LoCoMo milestone evaluation with LLM
answer/judge enabled under the blueprint. Do not silently broaden the phase.
```

- [ ] **Step 3: Perform code review against the anti-demo checklist below.**

Review must inspect event ordering, mutation absence on each denial path,
approval replay binding, public default-off behavior, gold-field serialization,
and case-level reporting. Review must cite `work/phase-15/context_bundle.md`
and the active goal.

## Anti-Demo Checklist

- [ ] K2 is invoked from `SimpleAgentStepRunner.run_step()`, not only a
  helper or demo CLI.
- [ ] The opt-in public benchmark probe reaches K2 through `evals.py`.
- [ ] `tool_candidates_generated` and `tool_selected` are durable traces, not
  transient return-only fields.
- [ ] An unknown or non-candidate selection never reaches policy, approval,
  execution, or verification.
- [ ] Invalid output, timeout, unavailable selector, missing provenance, and
  duplicate/replay mismatch do not produce memory writes.
- [ ] Failed selector resolution never silently picks `archive_write`.
- [ ] Approval resume is bound to both request fingerprint and stable
  `tool_call_id`.
- [ ] Only `archive_write` is exposed; no Phase 16 memory tool is opened.
- [ ] Default public kernel trace remains empty; v3 default, v1 fallback, and
  kernel opt-in are unchanged.
- [ ] Conditional planner artifacts, if admitted, are `proposal_only`,
  `gold_fields_used=false`, and never sent to execution by the planner.
- [ ] Expected answers, expected source ids, judge labels, gold-derived failure
  targets, and case-specific repair ids remain in eval-only sidecars.
- [ ] LoCoMo source localization and judged outcome remain separate per case;
  aggregate output does not hide pass-to-fail or source-miss risk.
- [ ] Result/review/ACK evidence makes no benchmark improvement or kernel
  default-on claim.

## Completion Evidence Expected From Execution

Mandatory evidence:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q
uv run pytest -q
uv run ruff check .
```

Conditional planner evidence, only when Tasks 6-7 are executed:

```bash
uv run pytest tests/test_public_benchmarks.py -q
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

Expected execution conclusion: structural K2 and, if admitted, planner
sidecar-boundary evidence only. No benchmark score target, benchmark
improvement claim, default kernel enablement, or promotion claim belongs in
Phase 15 completion.
