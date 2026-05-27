# xmuse GOD Session-First Architecture

> Date: 2026-05-28
> Status: spec
> Scope: architecture correction for post-MVP migration
> Depends on:
> - `2026-05-27-xmuse-architecture-blueprint-design.md`
> - `2026-05-27-xmuse-mvp-chat-to-lane-design.md`

## Purpose

This document corrects the architectural semantics of xmuse after the first
MVP chat-to-lane migration.

The current MVP path is valid as a transitional implementation:

- chat
- structured resolution
- lane graph
- ready lane projection
- platform runner / orchestrator
- gate / review / final action
- dashboard

But the current runtime still encodes the wrong identity model in three
critical places:

1. a GOD is still treated like a one-shot subprocess
2. execute GOD is still conflated with lane execution lifecycle
3. review GOD is still modeled like a short-lived callback process instead of a
   persistent auditor that emits verdict objects

This spec defines the corrected target semantics and the migration order to get
there without discarding the current MVP mainline.

## Non-Goals

This spec does not require the following in the same implementation slice:

- rewriting the full graph scheduler in one pass
- replacing every existing MVP execution module immediately
- introducing review council voting
- introducing a generic orchestration plugin system
- replacing the current dashboard frontend design language

## Hard Rules

The corrected architecture must preserve these rules:

1. `GodSession != WorkerProcess`
2. `ExecuteGodSession != LaneLifecycle`
3. `ReviewGodSession produces ReviewVerdict objects, not status side effects`

Any transitional implementation that violates these rules is considered a
temporary compatibility layer, not the target architecture.

## Architectural Model

xmuse is split into six layers.

### 1. Chat Plane

Responsibilities:

- human and GOD group chat
- routing and mentions
- proposal and approval flow
- clarification and discussion
- discussion handoff into `StructuredResolution`

Primary objects:

- `Conversation`
- `Message`
- `Proposal`
- `StructuredResolution`

Key rule:

- GODs are first-class chat participants before they are execution actors

### 2. GOD Session Layer

Responsibilities:

- host persistent CLI sessions
- maintain role prompts, session context, and tool bindings
- represent architect, execute, and review identities
- communicate through platform routing instead of direct side channels

Primary sessions:

- `ArchitectGodSession`
- `ExecuteGodSession`
- `ReviewGodSession`

Key rule:

- a GOD persists across many tasks and does not terminate when one lane finishes

### 3. Execution Plane

Responsibilities:

- convert `StructuredResolution` into `LaneGraph`
- materialize `ExecutionRun`
- compute ready lanes
- enforce dependency-aware scheduling
- launch one-shot lane workers
- ingest worker results and gate outputs

Primary objects:

- `LaneGraph`
- `ExecutionRun`
- `LaneRun`
- `WorkerArtifactBundle`

Key rule:

- execution truth is graph/run-centric, not subprocess-centric

### 4. Review Plane

Responsibilities:

- receive gated lanes as review tasks
- expose queued audit work to persistent review GOD sessions
- ingest formal `ReviewVerdict` objects
- support future expansion from single reviewer to review council

Primary objects:

- `ReviewTask`
- `ReviewInbox`
- `ReviewVerdict`

Key rule:

- review is an auditable task flow and object flow, not a branch inside lane
  status callbacks

### 5. Control Plane

Responsibilities:

- policy and human participation switches
- final action holds
- clarification / blocked-for-input handling
- audit event publication
- cross-plane state transitions

Primary objects:

- `FinalActionHold`
- `ClarificationRequest`
- `AuditEvent`
- `PolicyDecision`

Key rule:

- control plane governs transitions; it does not replace the chat or execution
  planes

### 6. Dashboard Read Models

Responsibilities:

- expose audit-safe read views for execution and review
- separate execution visibility from the main chat surface
- publish stable read models rather than ad hoc runtime state

Suggested read models:

- `conversations`
- `resolutions`
- `lane_graphs`
- `execution_runs`
- `lane_runs`
- `review_tasks`
- `verdicts`
- `final_actions`
- `audit_timeline`

Key rule:

- dashboard should read projected audit objects, not infer truth from scattered
  lane metadata

## GOD Session Semantics

### Architect GOD

`ArchitectGodSession` is a persistent chat participant.

Responsibilities:

- discuss requirements with human and peer GODs
- synthesize formal proposals
- help produce `StructuredResolution`
- participate in clarification loops

It is not responsible for executing lanes or owning execution state.

### Execute GOD

`ExecuteGodSession` is a persistent execution-facing session, but it is not the
lane worker.

Responsibilities:

- own execution strategy for a graph/run
- interact with human or other GODs about execution issues
- supervise execution progress
- trigger worker dispatch through controller interfaces

It does not itself become `executed` when a lane finishes.

### Review GOD

`ReviewGodSession` is a persistent audit-facing session.

Responsibilities:

- consume queued review tasks
- read gate reports, diffs, and worker artifacts
- submit formal `ReviewVerdict` objects
- remain distinct from implementation workers in prompt and tool access

It is not a short-lived review subprocess.

## Execution Model

The execution stack is split into three layers.

### ExecuteGodSession

Persistent CLI identity for execution discussion and supervision.

### ExecutionRunController

In-process controller responsible for:

1. creating and tracking `ExecutionRun`
2. finding dependency-ready lanes
3. enforcing concurrency budgets
4. dispatching lane workers
5. ingesting worker completion, gate results, and review routing events

### LaneWorkerLauncher

Launcher for one-shot lane workers such as `codex exec`.

Responsibilities:

- build worker prompt bundles
- launch lane-specific worker subprocesses
- collect artifacts, exit status, and telemetry

Non-responsibilities:

- no graph scheduling
- no review decisions
- no persistent GOD identity

## Lane Lifecycle Semantics

The target lane lifecycle should be interpreted as:

- `planned`
- `ready`
- `dispatched`
- `running`
- `executed`
- `gate_failed`
- `gated`
- `under_review`
- `reviewed`
- `awaiting_final_action`
- `merged`
- `requeued`
- `terminated`

Definitions:

- `planned`: lane exists in graph but is not dependency-ready
- `ready`: dependencies are satisfied and lane can be scheduled
- `dispatched`: a worker slot has been assigned
- `running`: lane worker is actively executing
- `executed`: worker completed and emitted an execution result bundle
- `gated`: post-execution gate passed
- `under_review`: a review task has been created and queued or claimed
- `reviewed`: a formal verdict has been accepted into the runtime
- `requeued`: execution should run again with explicit context
- `terminated`: lane or graph is stopped with audit context

The status `executed` refers to lane worker completion, not execute GOD
lifetime.

## Mixed-Run State Compatibility

During migration, the current MVP runtime and dashboard will continue to see
legacy lane states from `src/xmuse_core/platform/state_machine.py` and
`feature_lanes.json`.

This section defines the required compatibility contract so runtime modules and
dashboard read models do not guess independently.

### Authoritative rule during mixed-run

- `LaneGraph` remains the authoritative source for `planned` lanes
- projected lane queue entries remain the source for currently runnable or
  currently running work
- dashboard and controller must normalize legacy states through the same mapping
  layer until run-native states are fully deployed

### Legacy-to-target mapping

| Current MVP state | Mixed-run semantic meaning | Target semantic status | Notes |
|---|---|---|---|
| graph-only, not projected | lane exists but is not dependency-ready | `planned` | not represented in `feature_lanes.json`; must be read from `LaneGraph` |
| `pending` | dependency-ready and waiting for dispatch | `ready` | projected queue entry; dashboard must render as ready, not as generic pending |
| `dispatched` | worker slot assigned | `dispatched` | same meaning |
| `executed` | worker completed, pre-gate result exists | `executed` | same meaning |
| `gated` | gate passed and review task should exist or be created | `under_review` during bridge, then `gated` + review task | once `ReviewInbox` exists, runtime must emit `ReviewTask` before rendering review progress |
| `reviewed` | legacy bridge verdict accepted | `reviewed` | this state may exist only through verdict bridge; it must not mean "metadata implies review" |
| `awaiting_final_action` | final-action hold pending | `awaiting_final_action` | same meaning |
| `merged` | merged | `merged` | same meaning |
| `rejected` | legacy rework requested | `requeued` | preserved only as bridge state |
| `reworking` | legacy retry loop active | `requeued` | preserved only as bridge state |
| `exec_failed` | worker execution failed | `exec_failed` transitional failure bucket | may later fold into run-level failure model, but must remain distinguishable during migration |
| `gate_failed` | gate failed | `gate_failed` transitional failure bucket | must remain distinguishable from execute failure during migration |
| `failed` | terminal failure under old runtime | `terminated` unless bridge can recover a more specific failure cause | migration code should prefer cause-specific mapping when `failure_reason` is available |

### Dashboard contract during mixed-run

- dashboard metrics must aggregate normalized states, not raw legacy values
- dashboard approval logic must operate on normalized completion states
- any view that shows `planned` lanes must merge `LaneGraph` data with projected
  lane queue data rather than reading only `feature_lanes.json`

### Retirement rule

The statement `reviewed status == verdict exists` is retired as a target
semantic rule, but it remains valid only through the explicit bridge defined in
this spec until the legacy status machine is removed.

## Review Model

The review stack is split into three parts.

### ReviewInbox

When a lane reaches `gated`, runtime creates a `ReviewTask` and places it in
`ReviewInbox`.

The inbox is visible, auditable, retryable, and can later support multiple
reviewers.

### ReviewTask

Minimum fields:

- `task_id`
- `lane_id`
- `graph_id`
- `resolution_id`
- `artifact_refs`
- `gate_report_refs`
- `requested_by`
- `status`

Supported statuses:

- `pending`
- `claimed`
- `completed`
- `failed`
- `superseded`

### ReviewVerdict

`ReviewVerdict` is the authoritative output of review.

Minimum fields:

- `verdict_id`
- `lane_id`
- `graph_id`
- `resolution_id`
- `reviewer_session_id`
- `decision`
- `summary`
- `evidence_refs`
- `patch_instructions`
- `terminate_reason`
- `created_at`

Allowed decisions:

- `merge`
- `rework`
- `patch-forward`
- `terminate`

Runtime must consume verdict objects directly.
It must not infer review outcome by reverse-engineering lane metadata.

## Verdict Bridge for Incremental Migration

The current codebase already defines a minimal shared verdict object in
`src/xmuse_core/structuring/models.py` and uses
`src/xmuse_core/platform/verdict_adapter.py` as a bridge into lane metadata and
final-action logic.

Migration must not rely on that metadata bridge as the long-term source of
truth, but it also must not require a flag day replacement.

### Bridge rule

- introduce a new authoritative review-plane verdict model and store
- keep the current structuring-layer `ReviewVerdict` temporarily as a legacy
  transport DTO
- every legacy verdict must be up-converted into the authoritative verdict
  store before any lane transition, final-action hold creation, or dashboard
  publication occurs

### Required enrichment at up-conversion time

If a legacy DTO does not carry the full target schema, bridge code must enrich
it from review task context and lane/graph context before persistence.

Required enriched fields:

- `graph_id`
- `resolution_id`
- `reviewer_session_id`
- `created_at`
- lineage references required by patch-forward or terminate flows

### Bridge constraints

- no runtime path may treat scattered lane metadata as a substitute for a
  persisted verdict object
- `verdict_adapter.py` may remain as transition logic, but it must consume
  authoritative verdict records rather than becoming the permanent truth source
- dashboard verdict views must read the verdict store, not reverse-engineer lane
  metadata

### Model evolution decision

During migration, the review-plane authoritative model should be introduced in
a dedicated review-plane module rather than replacing the existing structuring
model in place on day one.

Reason:

- reduces cross-module churn
- allows old call sites to keep emitting the minimal DTO briefly
- makes the up-conversion bridge explicit and removable
- prevents silent fallback to metadata-based semantics

## Verdict Consumption Semantics

`ExecutionRunController` consumes a finalized verdict and maps it into control
flow.

### merge

- transition to `awaiting_final_action` when human approval is required
- otherwise proceed to `merged`

### rework

- transition to `requeued`
- attach explicit retry/rework context

### patch-forward

- create a child lane with lineage
- record `parent_lane_id`
- record `source_verdict_id`
- preserve graph linkage

Patch-forward child lanes must not be appended as orphan lanes detached from
graph lineage.

### terminate

- transition to `terminated`
- preserve terminate reason and evidence

## Current Runtime Mapping

The current transitional modules should be interpreted as follows.

### Modules to Keep as Transitional Base

- `xmuse/chat_api.py`
- `src/xmuse_core/chat/store.py`
- `src/xmuse_core/structuring/planner.py`
- `src/xmuse_core/structuring/graph_store.py`
- `src/xmuse_core/structuring/projection.py`
- `xmuse/dashboard_api.py`

### Modules to Reinterpret

- `src/xmuse_core/platform/agent_spawner.py`
  should become `LaneWorkerLauncher`
- `src/xmuse_core/platform/orchestrator.py`
  should become `ExecutionRunController`
- `xmuse/platform_runner.py`
  should become run-level execution entrypoint rather than a flat pending-lane
  scanner

### Semantics to Retire

- `execution-god subprocess == lane execution`
- `review-god subprocess == review`
- `reviewed status == verdict exists`

## Migration Strategy

Migration should proceed in five phases.

### Phase 1: Establish GOD Session Layer

Goal:

- make GOD identity persistent before changing deeper execution semantics

Work:

- build `GodSessionLayer`
- host `ArchitectGodSession`
- host `ExecuteGodSession`
- host `ReviewGodSession`
- route communication through the platform router
- introduce stable GOD addressing independent of `feature_id`, `lane_id`, or
  task identity
- add a persistent session registry keyed by `god_session_id`
- add stable `session_address` and `session_inbox_id` concepts for routing and
  work delivery

Compatibility:

- keep current orchestrator temporarily
- reinterpret current spawner as worker launcher
- reuse the `agents/*` substrate where practical, but phase 1 is incomplete if
  active sessions are still keyed by `feature_id`
- `feature_id` may remain on work assignments, but must not remain the primary
  session identity key

### Phase 2: Split Execute Session from Worker Execution

Goal:

- remove the assumption that lane lifecycle equals execution GOD lifecycle

Work:

- introduce `ExecutionRun`
- introduce `LaneRun`
- refactor orchestrator toward `ExecutionRunController`
- make run/controller consume graph truth instead of only flat pending lanes

Compatibility:

- keep existing graph store and ready projection as adapter layers
- keep `feature_lanes.json` as a transitional queue/read model, not
  authoritative truth

### Phase 3: Introduce Review Inbox and Verdict Ingestion

Goal:

- make review a first-class task and object flow

Work:

- add `ReviewTask`
- add `ReviewInbox`
- add `VerdictStore`
- route gated lanes to inbox
- consume only formal `ReviewVerdict` objects

Compatibility:

- keep current review adapter logic only as bridge code until full verdict
  ingestion exists
- require the bridge to persist an authoritative verdict record before any lane
  status transition derived from review

### Phase 4: Formalize Control Plane Objects

Goal:

- remove control logic from scattered lane metadata

Work:

- add `ClarificationRequest`
- harden `FinalActionHold`
- add `AuditEvent`
- add explicit policy decision records

Compatibility:

- retain existing final-action hold path while migrating storage and read models

### Phase 5: Unify Dashboard Read Models

Goal:

- make dashboard consume projected audit truth instead of reconstructing runtime
  truth from lane files

Work:

- publish read models for graph, run, review task, verdict, final action, and
  audit timeline
- reduce `feature_lanes.json` to a narrow transitional role

## Implementation Priority

Recommended order:

1. `GodSessionLayer`
2. `ExecuteGodSession + ExecutionRunController`
3. `ReviewInbox + ReviewVerdict ingestion`
4. `ControlPlane` objects
5. dashboard read-model unification

Reason:

- first correct identity semantics
- then correct execution semantics
- then correct audit semantics
- only then consolidate policy and read models

This minimizes rework and prevents further investment in one-shot GOD
assumptions.

## Acceptance Criteria

This architecture correction is successful when:

1. chat-visible GODs are persistent sessions rather than one-shot task
   subprocesses
2. execute GOD supervises an execution run instead of being equated with a lane
   worker
3. review GOD consumes review tasks and publishes `ReviewVerdict`
4. patch-forward creates lineage-aware child lanes instead of orphan lanes
5. dashboard can display graph/run/review/final-action audit data without
   inferring truth from lane metadata alone
