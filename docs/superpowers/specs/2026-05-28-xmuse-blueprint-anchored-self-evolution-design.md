# xmuse Blueprint-Anchored Self-Evolution

> Date: 2026-05-28
> Status: spec
> Scope: post-session-first cross-run self-evolution architecture
> Depends on:
> - `2026-05-27-xmuse-architecture-blueprint-design.md`
> - `2026-05-27-xmuse-mvp-chat-to-lane-design.md`
> - `2026-05-28-xmuse-god-session-first-architecture-design.md`

## Purpose

This document defines how xmuse should evolve itself after the
GOD-session-first architecture is in place.

The key correction is:

- self-evolution is not a purely mechanical controller workflow
- self-evolution is a non-standard, agent-led planning loop
- the loop must stay anchored to an explicit long-term blueprint

Therefore, xmuse self-evolution should be modeled as:

- blueprint-anchored
- architect-led
- review-ratified
- controller-guardrailed
- cross-run rather than in-run

This spec defines how xmuse can automatically open a new self-improvement run
after a prior run finishes, while keeping the existing MVP mainline intact:

- chat
- proposal
- approved resolution
- lane graph
- execution run
- review / verdict
- run terminal state

## Non-Goals

This slice does not require:

- replacing the current chat-to-resolution mainline
- bypassing `StructuredResolution -> planner -> LaneGraph`
- direct GOD writes into authoritative graph truth
- human approval for ordinary self-evolution proposals
- cost or token budgeting in the first version
- arbitrary platform-wide mission redefinition
- external product planning under the same loop

## Hard Rules

The architecture must preserve these rules:

1. self-evolution is triggered only after a run reaches a terminal state
2. self-evolution does not inject lanes into the current run
3. blueprint is an active planning input, not a passive archival document
4. architect GOD drafts evolution work; review GOD ratifies it
5. controller enforces guardrails but does not decide self-evolution content
6. candidate lane graphs must enter the system inside proposal/resolution content
7. authoritative lane graph truth still comes from the planner normalization path
8. blueprint mutation may auto-apply only inside the stable mission envelope:
   `improve xmuse autonomous delivery capability`

## Core Idea

xmuse self-evolution should be understood as a cross-run loop:

`run terminal -> evidence bundle -> architect draft -> review ratification -> controller guardrail check -> new visible conversation -> new proposal -> new approved resolution -> new lane graph -> next run`

This is not a side channel.
It is a specialized producer for the same mainline already used by human-driven
or GOD-assisted planning.

The difference from ordinary planning is the trigger source:

- ordinary planning is initiated from explicit human or system planning demand
- self-evolution is initiated from run outcome plus blueprint deviation or debt

## Run Definition

In this spec, a `run` means:

- one approved `StructuredResolution`
- one corresponding authoritative `LaneGraph`
- the full execution cycle of that graph
- including requeue, patch-forward, and clarification paths inside the graph
- until the graph reaches a terminal outcome

Run terminal outcomes are:

- `merged`
- `terminated`
- `blocked_for_input`

This is not a single lane lifecycle.
It is the lifecycle of one approved graph-level delivery attempt.

## Architectural Model

Self-evolution adds five layers on top of the existing MVP mainline.

### 1. Evolution Blueprint Layer

Responsibilities:

- define the long-term direction of xmuse self-improvement
- organize capability tracks and milestones
- give GODs a stable planning frame
- absorb bounded automatic blueprint updates

Primary objects:

- `EvolutionBlueprintSet`
- `BlueprintTrack`
- `BlueprintMutation`

Key rule:

- run evidence explains what happened
- blueprint explains what should happen next

### 2. Evolution Evidence Layer

Responsibilities:

- summarize the terminal run
- collect relevant verdicts, reports, lineage, and debt signals
- provide a structured handoff object to planning GODs

Primary object:

- `StructuredEvidenceBundle`

Key rule:

- cross-run planning should inherit structured evidence, not full noisy history

### 3. Agent-Led Evolution Planning Layer

Responsibilities:

- architect GOD reads blueprint plus evidence
- architect GOD drafts evolution proposal and candidate graph
- review GOD approves, narrows, or rejects the draft

Primary objects:

- `EvolutionProposal`
- `CandidateLaneGraph`
- `EvolutionReviewDecision`

Key rule:

- content decisions stay with GODs, not with the controller

### 4. Evolution Guardrail Layer

Responsibilities:

- verify run terminal state
- enforce xmuse-self-evolution boundary
- enforce 10-hour time budget
- enforce hybrid dedupe
- decide whether approved evolution work may be landed automatically

Primary objects:

- `EvolutionBudgetWindow`
- `EvolutionDedupRecord`
- `EvolutionGuardrailDecision`

Key rule:

- this layer governs safety and continuation, not planning content

### 5. Evolution Landing Layer

Responsibilities:

- create a system-authored visible conversation
- persist the evolution proposal and ratification result
- create a new proposal and approved resolution
- pass the candidate graph through planner normalization
- start the next high-priority run

Primary objects:

- `EvolutionConversation`
- `EvolutionLineageRecord`

Key rule:

- self-evolution lands through the same chat-to-resolution-to-graph mainline

## Role Model

### Architect GOD

Architect GOD is the primary self-evolution drafter.

Responsibilities:

- read the active blueprint set
- interpret the terminal run against that blueprint
- identify blueprint progress, deviation, debt, or missing tracks
- draft:
  - an `EvolutionProposal`
  - zero or more `BlueprintMutation` records
  - a `CandidateLaneGraph` inside proposal/resolution content

Architect GOD is not the final ratifier.

### Review GOD

Review GOD is the self-evolution ratifier.

Responsibilities:

- validate architect output against:
  - run evidence
  - review/verdict history
  - blueprint intent
  - risk and scope
- emit one of three decisions:
  - `approve`
  - `narrow`
  - `reject`

Semantics:

- `approve`: draft may proceed substantially as written
- `narrow`: direction is valid, but scope must be reduced before landing
- `reject`: no automatic self-evolution run should be opened from this draft

Review GOD does not become the primary author of the next run.

### Evolution Controller

The controller is not the planner.

Responsibilities:

- detect terminal runs
- assemble evidence bundles
- coordinate architect and review phases
- enforce guardrails
- land approved evolution work into the existing mainline

Non-responsibilities:

- no blueprint-level content planning
- no direct lane decomposition logic
- no semantic replacement for architect or review GODs

## Blueprint Model

### EvolutionBlueprintSet

`EvolutionBlueprintSet` is the active long-range planning base for xmuse
self-improvement.

Minimum fields:

- `blueprint_set_id`
- `title`
- `goal_statement`
- `version`
- `status`
- `active_track_ids`
- `priority_policy`
- `source_spec_refs`

Rules:

- initial version is human-provided
- later versions may be GOD-updated
- active blueprint set must stay inside the mission envelope:
  `improve xmuse autonomous delivery capability`

### BlueprintTrack

Tracks represent capability branches inside the blueprint.

Example track themes:

- execution autonomy
- review verdict formalization
- clarification recovery
- graph-native patch-forward
- dashboard auditability
- self-evolution planning quality

Minimum fields:

- `track_id`
- `name`
- `intent`
- `priority`
- `milestones`
- `dependencies`
- `acceptance_signals`

Every self-evolution proposal must target at least one track.

### BlueprintMutation

`BlueprintMutation` records proposed changes to the active blueprint set.

Minimum fields:

- `mutation_id`
- `blueprint_set_id`
- `proposed_by_session_id`
- `change_type`
- `summary`
- `affected_track_ids`
- `rationale`
- `created_at`

Allowed auto-applied change types in v1:

- `add_track`
- `split_track`
- `merge_track`
- `reorder_priority`
- `refine_milestone`
- `change_acceptance_signal`

Disallowed automatic changes:

- redefining the top-level mission
- elevating external product goals into the top-level blueprint mission
- removing the blueprint’s ability to track autonomous-delivery progress
- bypassing review, dedupe, or budget guardrails through blueprint edits

## Evidence Model

### StructuredEvidenceBundle

This is the cross-run handoff bundle used for self-evolution planning.

Minimum fields:

- `bundle_id`
- `source_run_id`
- `source_resolution_id`
- `summary`
- `run_terminal_status`
- `verdict_refs`
- `gate_report_refs`
- `lineage_refs`
- `artifact_refs`
- `signal_refs`
- `created_at`

Contents should include:

- run summary
- relevant verdicts
- gate reports
- patch-forward lineage
- requeue lineage
- key file references
- graph references
- negative signals
- debt signals

The bundle must be curated.
It should not be a full raw-history dump.

## Planning Model

### EvolutionProposal

This is the primary object describing the next self-evolution run.

Minimum fields:

- `proposal_id`
- `source_run_id`
- `blueprint_set_id`
- `target_track_ids`
- `scope_summary`
- `why_now`
- `evidence_bundle_id`
- `candidate_graph`
- `review_status`
- `spawned_conversation_id`
- `spawned_resolution_id`
- `created_at`

The proposal explains:

- what blueprint track should advance next
- why the current run proves that this next step matters now
- what concrete next run should be opened

### CandidateLaneGraph

This is not authoritative graph truth.
It is architect-authored graph intent embedded in proposal/resolution content.

Rules:

- architect GOD may draft it directly
- review GOD may narrow it
- it must still go through planner normalization
- planner remains the path to authoritative `LaneGraph`

Therefore the landing path stays:

`proposal/resolution content -> planner normalization -> authoritative lane graph`

## Guardrail Model

### EvolutionBudgetWindow

The first version uses only a time budget.

Budget definition:

- a self-evolution chain may continue automatically for up to 10 hours
- this is a chain-wide window, not a per-run timer
- the window starts when the first auto-accepted evolution run in the chain is opened
- in-flight work may finish after expiry, but no new automatic evolution run may start

Minimum fields:

- `window_id`
- `origin_run_id`
- `started_at`
- `expires_at`
- `status`
- `consumed_run_ids`

### EvolutionDedupRecord

The first version uses hybrid dedupe.

Minimum fields:

- `dedup_key`
- `signal_fingerprint`
- `source_lineage_key`
- `target_track_ids`
- `first_seen_at`
- `last_seen_at`
- `last_proposal_id`
- `status`

Hybrid dedupe should evaluate both:

- `signal fingerprint`
  based on signal type, affected paths/modules, and normalized reason
- `source lineage key`
  based on source run, verdict lineage, and target blueprint track

This prevents:

- repeated rephrasing of the same issue
- repeated auto-opening from the same run lineage

## Trigger Model

Self-evolution may be considered only after run terminalization.

Eligible trigger signal classes:

- `negative signals`
- `debt signals`

### Negative Signals

Examples:

- terminal `terminated`
- terminal `blocked_for_input`
- repeated `requeue` without convergence
- repeated `patch-forward` without convergence

### Debt Signals

Examples:

- merged with architecture debt
- merged with test debt
- merged with workflow debt
- merged via temporary workaround that exposes a platform gap
- merged but visibly misaligned with an active blueprint track

Trigger eligibility is not sufficient for continuation.
It only grants architect GOD the right to draft a self-evolution proposal.

## State Flow

The v1 state flow should be:

1. run reaches terminal state
2. controller checks that the run is eligible for self-evolution evaluation
3. controller assembles `StructuredEvidenceBundle`
4. architect GOD drafts:
   - `EvolutionProposal`
   - optional `BlueprintMutation`
   - `CandidateLaneGraph`
5. review GOD emits:
   - `approve`
   - `narrow`
   - `reject`
6. controller applies guardrail checks:
   - terminal-state validity
   - mission-envelope boundary
   - hybrid dedupe
   - 10-hour budget
7. if allowed, controller creates:
   - a system-authored visible conversation
   - a new proposal
   - a new approved resolution
8. planner normalizes the embedded candidate graph
9. authoritative lane graph is created
10. next high-priority evolution run starts

## Ratification Semantics

### Approve

- the proposed evolution scope is acceptable
- the candidate lane graph may proceed largely as drafted
- blueprint mutation may apply if included and mission-bounded

### Narrow

- the direction is valid
- the proposed scope is too wide, too risky, or too noisy
- architect output must be reduced before landing
- the narrowed result may still auto-land

### Reject

- this run should not automatically create a new evolution run
- reasons may include:
  - blueprint misalignment
  - duplicated proposal lineage
  - mission drift
  - insufficient evidence
  - too-fragmented scope

## Landing Semantics

Approved or narrowed self-evolution work should land as:

- a new `system-authored visible conversation`
- a new proposal object inside that conversation
- a new approved resolution
- a planner-normalized authoritative graph
- a new high-priority run

This preserves one unified mainline.

The system must not:

- directly append lanes into the previous run
- directly write the candidate graph into graph truth
- hide the next run inside a control-only channel

## Priority Rules

Self-evolution work must not inline-preempt an active external run.

Rules:

- current source run must first reach terminal state
- the next evolution run is then enqueued with high priority
- high priority means higher than ordinary backlog and maintenance work
- high priority does not bypass resource constraints

## Safety Modes

The system should produce one of three continuation outcomes:

- `continue`
- `hold`
- `stop`

### Continue

Automatic self-evolution may open the next run.

### Hold

Automatic continuation pauses, but the evidence and proposal remain visible.

Typical reasons:

- ambiguous scope after narrowing
- budget near exhaustion
- repeated blocked-for-input pattern

### Stop

The current self-evolution chain should not auto-continue.

Typical reasons:

- budget exhausted
- hybrid dedupe collision without meaningful delta
- blueprint drift outside mission envelope
- repeated non-progress loops

## Failure Modes

At minimum, the architecture must explicitly handle these cases.

### 1. Budget Exhaustion

- no new automatic evolution run may start after the 10-hour window expires
- in-flight work may finish

### 2. Dedupe Collision Without Meaningful Delta

- repeated signals alone are not enough to justify a new run
- if the new proposal does not materially advance a blueprint track, continuation should stop

### 3. Blueprint Drift Beyond Mission Envelope

- review GOD should reject
- controller should still enforce the boundary

### 4. Narrowing Below Viable Scope

- if repeated narrowing leaves no coherent run-sized task, auto-continuation should stop

### 5. Repeated Blocked-for-Input on the Same Gap

- repeated blocked runs on the same blueprint gap should shift the chain into `hold` or `stop`

### 6. Success Without Blueprint Progress

- merged work that does not move a blueprint track forward must not justify infinite self-generated follow-up runs

## Read Models

The dashboard must expose self-evolution objects directly.

Required read models in v1:

- `blueprint_sets`
- `blueprint_mutations`
- `evolution_proposals`
- `run_lineage`
- `evolution_budget`

### blueprint_sets

Should show:

- active blueprint set
- tracks
- milestones
- priorities
- current version

### blueprint_mutations

Should show:

- proposer
- affected tracks
- change type
- rationale
- ratification result

### evolution_proposals

Should show:

- source run
- target tracks
- evidence summary
- ratification result
- auto-accept result
- spawned conversation/resolution/run links

### run_lineage

Should show:

- source run
- evolution proposal
- spawned conversation
- spawned resolution
- next run

This is the key audit chain for automatic self-evolution.

### evolution_budget

Should show:

- budget window start
- budget window expiry
- current status
- continuation eligibility

## Testing Expectations

The first implementation slice should verify:

1. terminal run outcome can produce a structured evidence bundle
2. architect-authored self-evolution proposal can include a candidate graph
3. review ratification supports `approve`, `narrow`, and `reject`
4. narrowed proposals still land through the standard resolution path
5. hybrid dedupe blocks duplicate auto-evolution chains
6. 10-hour budget blocks new automatic chains after expiry
7. blueprint mutation auto-applies only within mission envelope
8. self-evolution landing creates a visible conversation rather than a hidden control artifact
9. planner remains the authoritative graph-normalization path

## Acceptance Criteria

This architecture is successful when:

1. xmuse self-evolution is anchored to a versioned blueprint set
2. architect GOD, not the controller, drafts the next self-evolution run
3. review GOD ratifies with `approve | narrow | reject`
4. candidate lane graphs are embedded inside proposal/resolution content rather
   than written directly as graph truth
5. every automatic self-evolution run is traceable back to:
   - a source run
   - an evidence bundle
   - a blueprint track
   - a ratification result
6. blueprint mutation can auto-apply without human approval while remaining
   mission-bounded
7. the 10-hour chain budget and hybrid dedupe prevent uncontrolled auto-growth
8. self-evolution runs re-enter the same chat-to-resolution-to-graph mainline
   rather than creating a parallel execution path
