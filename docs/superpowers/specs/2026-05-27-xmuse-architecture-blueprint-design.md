# xmuse Architecture Blueprint

> Date: 2026-05-27
> Status: blueprint
> Scope: long-term target architecture

## Purpose

This document fixes the long-term architectural direction for xmuse.
It is not the implementation scope for the first release.

The target product is a multi-GOD software development platform where:

- humans discuss requirements with multiple CLI-based GODs in a chat-first UI
- approved discussion outcomes become structured execution plans
- execute GODs run lanes concurrently on top of xmuse's execution stack
- review GODs or a review council decide merge, rework, patch-forward, or terminate
- human participation can be inserted at critical control gates
- chat and execution status are separated into independent frontend surfaces

## Product Shape

The product has two primary user-facing surfaces:

1. `Chat`
   The main interaction surface for humans and GODs.
   This is where exploration, proposal, deliberation, and approval happen.

2. `Dashboard`
   A separate execution and audit surface.
   This shows lane graphs, execution state, gate reports, review verdicts, and merge history.

Execution state is not rendered inline as the primary chat experience.
Chat may reference execution state, but dashboard remains the authoritative read view for execution.

## Architectural Model

The target architecture is split into three planes.

### Chat Plane

Responsible for:

- multi-GOD conversations
- routing and mentions
- proposals and deliberation
- approval to structure
- human interaction in discussion mode

Primary objects:

- `Conversation`
- `Message`
- `Proposal`
- `ResolutionDraft`

### Execution Plane

Responsible for:

- lane graph materialization
- concurrent lane execution
- code generation and patching
- gate execution
- review decisions
- merge or termination outcomes

Primary objects:

- `StructuredResolution`
- `LaneGraph`
- `Lane`
- `ExecutionRun`
- `ReviewVerdict`

### Control Plane

Responsible for:

- policy
- human gate switches
- audit events
- cross-plane transitions
- read-model publication

The control plane does not replace the chat or execution planes.
It governs transitions and policy between them.

## Communication Topology

The chosen topology is `semi-peer`.

User-visible behavior:

- GODs appear to speak to each other as peers
- humans can join the same discussion
- GODs can actively delegate or ask each other for help

Infrastructure behavior:

- all GOD communication flows through a platform `Gateway/Router`
- the platform is the only transport, persistence, and audit entrypoint
- GODs do not directly establish their own side channels

This preserves the product feel of peer collaboration without sacrificing auditability.

## Truth Model

xmuse uses a dual truth model with an explicit handoff point.

### Before approval to structure

The source of truth is the chat plane event stream:

- messages
- proposals
- approvals
- discussion context

### After approval to structure

The source of truth for execution becomes structured state:

- structured resolution snapshots
- lane graph snapshots
- execution state machine state
- review verdict snapshots

Chat remains visible and referential, but it is no longer the execution truth source.

## Immutability Rule

The following objects are append-only snapshots:

- `StructuredResolution`
- `LaneGraph`
- `ReviewVerdict`

They must never be modified in place.

Changes produce a new version which supersedes the old one.
Execution always references an explicit version.

This rule is required for reliable audit and replay.

## Core Objects

### Proposal

A formal suggestion created during discussion.
It is distinct from an ordinary chat message.

Minimum roles:

- define an actionable suggestion
- reference prior messages or artifacts
- be accepted, rejected, superseded, or withdrawn

### StructuredResolution

The approved, immutable output of discussion.
This is the handoff object from chat to execution.

It captures:

- what was approved
- who approved it
- which proposals it derived from
- what lane plan should exist
- what context bundle should be attached

### LaneGraph

The structured execution plan.

It captures:

- lane list
- dependency graph
- concurrency intent
- scheduling policy
- execution linkage back to a structured resolution

### ReviewVerdict

The formal structured outcome of post-execution review.

Allowed decision classes:

- `merge`
- `rework`
- `patch-forward`
- `terminate`

Review may be performed by a single GOD in early phases and a council later.
The object model must support both.

## Core Modules

### Gateway / Router

The single ingress for GOD and human communication.
Responsibilities:

- receive messages
- route mentions and broadcasts
- persist chat events
- trigger structured actions
- wake GOD processes

### Conversation State

Owns discussion state only.
It stores and serves:

- conversations
- participants
- messages
- proposals
- draft resolutions

It does not own lane execution state.

### Lane Structuring

The only sanctioned path from approved discussion to executable work.
It converts approved structured resolutions into lane graph snapshots.

### Execution Orchestrator

Owns:

- dispatch
- agent spawning
- execution status transitions
- gate invocation
- reconciliation

This is where the current `src/xmuse_core/platform/*` line belongs.

### Review Council

Owns post-execution deliberation and verdict formation.
It must not mutate code directly.

If small fixes are allowed, they should be expressed as `patch-forward` verdicts and executed by an execution unit.

### Human Gate

A policy-controlled intervention layer.
At minimum it should support:

- approval before structure
- approval before merge
- approval before terminate
- tie-break or override in disputed review outcomes

### Dashboard Read Model

Owns projection for the execution and audit UI.
It is not the system of record.
It is a stable, query-friendly read model for dashboard rendering.

## Codebase Mapping

### Promote to primary execution-plane foundations

- `src/xmuse_core/platform/*`
- `src/xmuse_core/gates/*`
- `xmuse/mcp_server.py`
- `xmuse/platform_runner.py`

These should evolve as execution-plane infrastructure, not as chat-plane orchestrators.

### Keep as compatibility or migration surfaces

- `xmuse/master_loop.py`
- `xmuse/master_state.json`
- `xmuse/slave_job_runner.py`
- `xmuse/work/features/*`
- `xmuse/jobs/*`
- `xmuse/history/*`

These represent the older file-driven master/slave control line.
They may be imported, read, or migrated, but should not remain the future source of truth.

### Replace over time as primary state carriers

- `xmuse/feature_lanes.json`
- `xmuse/active_sessions.json`

They may remain as transitional projections or runtime mirrors, but not as long-term primary business objects.

## Migration Direction

### Phase 0

Stabilize execution-plane ownership and downgrade the old master flow to compatibility status.

### Phase 1

Introduce chat plane and route all new discussion through conversation state.

### Phase 2

Introduce structured resolution and lane graph snapshots as the only execution entrypoint.

### Phase 3

Introduce structured review verdicts and retire old master control as a primary workflow engine.

## Non-Goals for the Blueprint

This blueprint does not prescribe:

- exact storage technology
- exact frontend framework internals
- exact event transport semantics
- exact council voting algorithm
- exact deployment topology

Those belong in phase-specific implementation specs.
