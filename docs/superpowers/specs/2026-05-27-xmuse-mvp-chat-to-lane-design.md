# xmuse MVP: Chat to Lane Execution

> Date: 2026-05-27
> Status: spec
> Scope: first implementation phase
> Depends on: `2026-05-27-xmuse-architecture-blueprint-design.md`

## Purpose

This spec defines the first shippable xmuse slice for the new architecture.

The first release must prove the full core chain:

- human and multiple GODs discuss in chat
- discussion is approved into a structured resolution
- the resolution becomes a lane graph
- lanes execute through the current xmuse execution stack
- review produces a structured verdict
- dashboard independently audits the execution and review lifecycle

This release is intentionally narrower than the blueprint.

## Product Scope

### In Scope

1. A dedicated `Chat` surface for human and GOD discussion
2. A separate `Dashboard` surface for execution and audit state
3. Semi-peer GOD communication through a central platform router
4. Proposal and approval-to-structure workflow
5. `StructuredResolution -> LaneGraph` materialization
6. Execution through the current xmuse platform stack
7. Single review GOD with structured `ReviewVerdict`
8. Human approval switches at critical gates

### Out of Scope

1. Multi-GOD review council voting
2. Fully real-time streaming architecture everywhere
3. Full retirement of all legacy master-loop assets
4. Generic orchestration plugin marketplace
5. Fully direct GOD-to-GOD transport
6. Complex policy engine for human gating

## MVP Success Criteria

The MVP is successful if all five conditions hold:

1. A human can discuss a requirement with multiple GODs in chat.
2. The discussion can produce an approved `StructuredResolution`.
3. The system can generate a `LaneGraph` with dependency-aware parallel execution intent.
4. Existing xmuse execution infrastructure can execute those lanes and record auditable outputs.
5. Review can conclude with one of:
   `merge`, `rework`, `patch-forward`, `terminate`.

## User-Facing Shape

### Chat Surface

Primary purpose:

- discussion
- proposal
- approval
- delegation between GODs

Visible concepts:

- participants
- messages
- mentions
- formal proposals
- approval actions

Execution state does not dominate this surface.

### Dashboard Surface

Primary purpose:

- inspect lane graph
- track lane status
- inspect artifacts and gates
- inspect review verdicts
- inspect merge and termination outcomes

Visible concepts:

- lane graph
- dependency graph
- lane timeline
- gate report
- review verdict
- merge or stop outcome

## Core Flow

### Step 1: Discussion

- Human enters a requirement in chat.
- Multiple GODs discuss, clarify, and decompose.
- GODs can mention each other and continue the discussion through the platform router.

### Step 2: Formal proposal

- A GOD emits a formal `Proposal`.
- The proposal summarizes the recommended structure of work.
- Human gate may require approval before advancing.

### Step 3: Approval to structure

- Once approved, the platform creates an immutable `StructuredResolution`.
- The resolution becomes the execution entrypoint.

### Step 4: Lane graph generation

- The system converts the structured resolution into an immutable `LaneGraph`.
- The lane graph includes lane prompts, dependencies, and concurrency guidance.

### Step 5: Execution

- The execution plane projects the lane graph into the current xmuse lane runner.
- Existing `PlatformOrchestrator`, `LaneStateMachine`, `AgentSpawner`, and `GateRunner` remain the execution core.

### Step 6: Review

- A single review GOD reads execution artifacts and gate outputs.
- It emits a structured `ReviewVerdict`.

### Step 7: Final action

- If verdict is `merge`, merge can proceed subject to optional human approval.
- If verdict is `rework`, execution returns with explicit context.
- If verdict is `patch-forward`, a bounded follow-up execution step applies minimal corrections before merge.
- If verdict is `terminate`, the lane graph or lane is halted with audit context.

## MVP Objects

### Proposal

Required MVP behaviors:

- distinguish proposal from ordinary message
- support acceptance or rejection
- retain references to source messages

Required MVP states:

- `open`
- `accepted`
- `rejected`
- `superseded`
- `withdrawn`

### StructuredResolution

Required MVP behaviors:

- immutable after approval
- versioned
- references proposals and approving actors
- carries enough summary and context to generate a lane graph

Required MVP states:

- `draft`
- `approved`
- `superseded`
- `cancelled`

### LaneGraph

Required MVP behaviors:

- express multiple lanes
- express dependencies
- express concurrency intent
- map deterministically to execution-plane lanes

Required MVP states:

- `planned`
- `running`
- `completed`
- `halted`
- `superseded`

### ReviewVerdict

Required MVP behaviors:

- immutable after finalization
- references execution evidence
- emits one of the four allowed decision classes

Required MVP states:

- `proposed`
- `finalized`
- `overridden`
- `superseded`

Allowed MVP decisions:

- `merge`
- `rework`
- `patch-forward`
- `terminate`

## Module Boundaries for MVP

### New or expanded modules

1. `Gateway / Router`
   Owns GOD and human message ingress, mention routing, message persistence, and action triggering.

2. `Conversation State`
   Owns conversations, participants, messages, proposals, and resolution drafts.

3. `Lane Structuring`
   Owns `StructuredResolution -> LaneGraph` conversion.

4. `Dashboard Read Model`
   Owns dashboard projection over execution and review state.

5. `Review Verdict Model`
   Owns structured review outputs even if only one review GOD exists in this phase.

### Existing modules to reuse

1. `src/xmuse_core/platform/*`
   Reuse as the execution plane kernel.

2. `src/xmuse_core/gates/*`
   Reuse as gate infrastructure.

3. `xmuse/mcp_server.py`
   Reuse as the API facade for execution and platform tools, but do not turn it into the full chat-plane brain.

4. `xmuse/platform_runner.py`
   Reuse as execution worker loop with lane reconciliation.

### Legacy modules to avoid extending

- `xmuse/master_loop.py`
- `xmuse/master_state.json`
- `xmuse/work/features/*`
- `xmuse/jobs/*`
- `xmuse/history/*`

These should remain compatibility surfaces, not receive new primary workflow logic.

## Human Gates for MVP

The MVP must support two mandatory human gate switches:

1. `approve_structure`
   Approval before a structured resolution is finalized for execution.

2. `approve_final_action`
   Approval before `merge` or `terminate` is applied.

Optional later gates are explicitly deferred.

## Patch-Forward Semantics

`patch-forward` must not mean ad hoc reviewer edits.

For the MVP it means:

- review concludes the core business outcome is correct
- bounded defects exist
- the system creates a minimal corrective execution task
- the corrective task is auditable and linked to the original verdict

This preserves separation between review and execution.

## Frontend Direction

The MVP frontend should continue the current visual language in the Windows Open Design project.

Required UX direction:

- `Chat` and `Dashboard` are separate primary views
- chat remains the main interaction surface
- dashboard is default-openable as an independent audit surface
- execution details are navigable from chat context, but not rendered as the main chat substrate

This spec does not require final frontend implementation details.
It only fixes the product boundary.

## Storage Direction

The MVP may continue to use transitional file-backed state where practical, but must treat them as projections, not conceptual truth sources.

Acceptable transitional projections:

- `feature_lanes.json`
- `active_sessions.json`

The MVP should introduce explicit structured objects even if their first persistence layer is simple.

## Testing Strategy

The MVP should prove behavior through focused tests at four levels:

1. Conversation flow tests
   Proposal creation, approval, and structured handoff

2. Lane structuring tests
   Resolution-to-lane-graph determinism, dependency handling, and versioning

3. Execution integration tests
   Lane graph projection into existing xmuse platform execution flow

4. Review verdict tests
   Structured review outputs and final action handling

The release does not require full end-to-end browser automation at the first stage.

## Migration Strategy for MVP

### Phase 0

Keep execution-plane ownership in the current platform modules.

### Phase 1

Add the chat plane and route all new discussion through it.

### Phase 2

Introduce structured resolution and lane graph as the only supported path into new execution runs.

### Phase 3

Add structured review verdict handling and reduce reliance on legacy master-loop assets.

## Open Constraints Fixed by This Spec

The following decisions are fixed and should not be re-opened during MVP implementation unless a blocker appears:

- topology is `semi-peer`
- chat and dashboard are separate surfaces
- discussion truth and execution truth are separated by approval-to-structure
- structured objects are immutable snapshots
- execution continues to reuse the current xmuse platform stack
- review is single-GOD in the MVP but must emit future-compatible structured verdicts
