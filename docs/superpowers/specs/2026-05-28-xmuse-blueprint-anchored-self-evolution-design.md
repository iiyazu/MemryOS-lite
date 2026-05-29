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
9. `narrow` must force architect redraft; neither review GOD nor controller may
   silently become the final content author
10. run-level terminalization must be computed through an explicit aggregation
    contract rather than guessed from individual lane states

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
- `NarrowingDecision`

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
It is, however, always the final content author for any landed evolution draft.

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
When review emits `narrow`, it must produce structured narrowing constraints
rather than a final rewritten proposal.

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
- no hidden mutation of proposal text or candidate graph content
- no substantive steering of self-evolution content by selectively hiding cited
  primary evidence from architect or review GODs

## Blueprint Model

### EvolutionBlueprintSet

`EvolutionBlueprintSet` is the active long-range planning base for xmuse
self-improvement.

Minimum fields:

- `blueprint_set_id`
- `title`
- `goal_statement`
- `version`
- `supersedes_blueprint_set_id`
- `status`
- `active_track_ids`
- `priority_policy`
- `source_spec_refs`
- `created_at`

Rules:

- initial version is human-provided
- later versions may be GOD-updated
- blueprint sets are append-only snapshots; auto-mutation creates a new version
  rather than mutating the current snapshot in place
- only one blueprint set version may be `active` at a time
- `goal_statement` is immutable across automatic blueprint mutations
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
- `proposed_successor_blueprint_set_id`
- `proposed_by_session_id`
- `change_type`
- `summary`
- `affected_track_ids`
- `rationale`
- `non_regression_note`
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

Additional mutation rules:

- every accepted mutation must land as a new blueprint snapshot with explicit
  supersession lineage
- automatic mutation must not weaken `goal_statement`
- `change_acceptance_signal` may refine, clarify, or strengthen evidence
  requirements, but it must not silently reduce the evidence bar for declaring
  blueprint progress

## Evidence Model

### StructuredEvidenceBundle

This is the cross-run handoff bundle used for self-evolution planning.

Minimum fields:

- `bundle_id`
- `source_run_id`
- `source_resolution_id`
- `selection_policy_id`
- `selection_policy_version`
- `summary`
- `run_terminal_status`
- `verdict_refs`
- `gate_report_refs`
- `lineage_refs`
- `artifact_refs`
- `signal_refs`
- `primary_refs`
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

Evidence curation contract:

- the controller may summarize, cluster, and rank evidence for planner
  efficiency
- every cited or summarized item must retain a full primary reference in
  `primary_refs`
- `selection_policy_id` and `selection_policy_version` must identify the
  evidence selection policy used to build the bundle
- architect and review GODs must receive both the curated summary view and the
  primary references view
- selection policy changes must be auditable so later reviewers can explain why
  an item was included or omitted

## Planning Model

### EvolutionProposal

This is the primary object describing the next self-evolution run.

Minimum fields:

- `proposal_id`
- `source_run_id`
- `blueprint_set_id`
- `target_track_ids`
- `status`
- `draft_version`
- `author_session_id`
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

Lifecycle statuses:

- `drafting`
- `awaiting_review`
- `narrowed_for_redraft`
- `approved`
- `rejected`
- `guardrail_blocked`
- `landed`

### CandidateLaneGraph

This is not authoritative graph truth.
It is architect-authored graph intent embedded in proposal/resolution content.

Rules:

- architect GOD may draft it directly
- review GOD may constrain it only through `NarrowingDecision`
- it must still go through planner normalization
- planner remains the path to authoritative `LaneGraph`
- the executable graph payload must be serialized as
  `StructuredResolution.content["lanes"]`
- self-evolution metadata that is not executable graph content must live beside
  `lanes` in resolution/proposal content, not in a parallel graph-truth channel

Therefore the landing path stays:

`proposal/resolution content -> planner normalization -> authoritative lane graph`

This matches the current planner behavior, which reads executable lane intent
from `StructuredResolution.content["lanes"]`.

### NarrowingDecision

`NarrowingDecision` is the structured output of a review `narrow` verdict.

Minimum fields:

- `decision_id`
- `proposal_id`
- `source_review_session_id`
- `source_draft_version`
- `target_draft_version`
- `scope_constraints`
- `required_graph_changes`
- `required_evidence_focus`
- `rationale`
- `created_at`

Rules:

- `narrow` never lands directly
- `narrow` always returns authorship to architect GOD for redraft
- review GOD may constrain scope and graph shape, but it may not silently become
  the final author of the landed proposal text
- each redraft must increment `draft_version` while keeping the same
  `proposal_id` lineage

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

### EvolutionGuardrailDecision

This object records whether an approved proposal may continue into automatic
landing.

Minimum fields:

- `decision_id`
- `proposal_id`
- `source_run_id`
- `decision`
- `reason_codes`
- `budget_window_id`
- `dedup_key`
- `mission_boundary_result`
- `terminal_aggregation_ref`
- `created_at`

`decision` values:

- `continue`
- `hold`
- `stop`

Rules:

- guardrail decisions operate only on review-approved proposal drafts
- guardrail decisions may stop or hold continuation, but they may not rewrite
  proposal content
- guardrail decisions must persist the exact basis used for the decision so the
  dashboard can audit why continuation happened or did not happen

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

## Run Terminal Aggregation

Run terminalization must be computed from explicit run-level truth, not guessed
from a single lane state.

Authoritative inputs:

- authoritative `LaneGraph`
- normalized lane execution states, including mixed-run compatibility mapping
- verdict lineage
- patch-forward lineage
- final-action holds
- clarification / blocked-for-input objects

### Lane-Lineage Closure

A lane lineage is the originating lane plus every descendant created through
requeue, rework, or patch-forward continuation.

A run is not terminal while any lane lineage remains open.
A lineage is closed only when no descendant path remains executable, reviewable,
or waiting on final action.

### Terminal Outcomes

`merged`:

- every lane lineage is closed
- every required final action hold is resolved positively
- no clarification object remains open
- the resulting graph-level delivery attempt is accepted as completed

`terminated`:

- every lane lineage is closed
- no clarification object remains open
- at least one lineage closed via fail/stop semantics, or guardrails/controller
  explicitly terminated the run

`blocked_for_input`:

- progress cannot continue without external information or clarification
- at least one authoritative clarification or blocked object remains open
- no executable lane can advance until that input is resolved

### Mixed-Run Compatibility Bridge

Until native run-level truth exists everywhere, terminal aggregation must first
normalize legacy lane states through the mixed-run compatibility rules defined
by the session-first architecture migration.

That normalization layer is the only allowed bridge from current MVP runtime
states into these terminal outcomes.

## State Flow

The v1 state flow should be:

1. run reaches terminal state
2. controller checks that the run is eligible for self-evolution evaluation
3. controller assembles `StructuredEvidenceBundle`
4. architect GOD drafts proposal `draft_version = 1`:
   - `EvolutionProposal`
   - optional `BlueprintMutation`
   - `CandidateLaneGraph`
5. review GOD emits:
   - `approve`
   - `narrow`
   - `reject`
6. if review emits `narrow`, it must persist `NarrowingDecision` and return the
   same proposal lineage to architect GOD for redraft
7. architect GOD may redraft the same `proposal_id` with incremented
   `draft_version`, after which review GOD must ratify again
8. v1 allows at most one automatic narrow-redraft loop; a second unresolved
   narrowing degrades to `hold` rather than hidden controller authorship
9. if review emits `reject`, the self-evolution attempt stops for this source
   run
10. only after review emits `approve` may controller apply guardrail checks:
   - terminal-state validity
   - mission-envelope boundary
   - hybrid dedupe
   - 10-hour budget
11. if allowed, controller creates:
   - a system-authored visible conversation
   - a new proposal
   - a new approved resolution
12. planner normalizes the embedded candidate graph from
    `StructuredResolution.content["lanes"]`
13. authoritative lane graph is created
14. next high-priority evolution run starts

## Ratification Semantics

### Approve

- the proposed evolution scope is acceptable
- the candidate lane graph may proceed largely as drafted
- blueprint mutation may apply if included and mission-bounded

### Narrow

- the direction is valid
- the proposed scope is too wide, too risky, or too noisy
- review GOD must emit a `NarrowingDecision`
- architect output must be reduced before landing
- only an architect-authored redraft may later auto-land

### Reject

- this run should not automatically create a new evolution run
- reasons may include:
  - blueprint misalignment
  - duplicated proposal lineage
  - mission drift
  - insufficient evidence
  - too-fragmented scope

## Landing Semantics

Review-approved self-evolution work should land as:

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

### EvolutionConversation

This is the visible chat entry point for an accepted self-evolution run.

Minimum fields:

- `conversation_id`
- `source_run_id`
- `origin_proposal_id`
- `visibility`
- `opened_by`
- `opened_at`

Rules:

- it must be visible on the normal chat surface
- it must preserve lineage back to the source run and evolution proposal
- it is the public handoff point from cross-run planning back into the standard
  mainline

### EvolutionLineageRecord

This is the authoritative bridge between the source run and the spawned
self-evolution run.

Minimum fields:

- `lineage_id`
- `source_run_id`
- `source_resolution_id`
- `proposal_id`
- `spawned_conversation_id`
- `spawned_resolution_id`
- `spawned_run_id`
- `blueprint_set_id`
- `target_track_ids`
- `terminal_aggregation_ref`
- `guardrail_decision_id`
- `created_at`

Rules:

- one record must exist for every landed automatic self-evolution run
- lineage records are append-only
- lineage records are the audit root for cross-run continuation

## Authoritative Stores

The first implementation must make store ownership explicit.

- blueprint store is authoritative for `EvolutionBlueprintSet` and accepted
  `BlueprintMutation` snapshots
- evidence store is authoritative for `StructuredEvidenceBundle`
- proposal store is authoritative for `EvolutionProposal` and
  `NarrowingDecision`
- guardrail store is authoritative for `EvolutionGuardrailDecision`
- lineage store is authoritative for `EvolutionConversation` and
  `EvolutionLineageRecord`

No dashboard or controller component may infer these objects solely from loose
lane metadata once the dedicated stores exist.

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
- `evolution_guardrail_decisions`
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
- draft version history
- ratification result
- auto-accept result
- spawned conversation/resolution/run links

### evolution_guardrail_decisions

Should show:

- proposal
- continuation decision
- reason codes
- budget status
- dedupe result
- terminal aggregation basis

### run_lineage

Should show:

- source run
- evolution proposal
- spawned conversation
- spawned resolution
- next run
- terminal aggregation reference
- guardrail decision reference

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
2. evidence bundles expose curated summaries plus full primary refs under a
   versioned selection policy
3. architect-authored self-evolution proposal can include a candidate graph
   serialized into `StructuredResolution.content["lanes"]`
4. review ratification supports `approve`, `narrow`, and `reject`
5. `narrow` persists `NarrowingDecision` and forces architect redraft rather
   than direct landing
6. run terminal outcomes are computed from explicit aggregation inputs rather
   than guessed from a single lane state
7. hybrid dedupe blocks duplicate auto-evolution chains
8. 10-hour budget blocks new automatic chains after expiry
9. blueprint mutation auto-applies only within mission envelope and without
   weakening `goal_statement` or acceptance evidence bar
10. self-evolution landing creates a visible conversation rather than a hidden
    control artifact
11. planner remains the authoritative graph-normalization path
12. dashboard read models expose proposal lineage, guardrail decisions, and run
    lineage for audit

## Acceptance Criteria

This architecture is successful when:

1. xmuse self-evolution is anchored to a versioned blueprint set
2. architect GOD, not the controller, drafts the next self-evolution run
3. review GOD ratifies with `approve | narrow | reject`
4. `narrow` always returns to architect redraft and never lands through hidden
   controller or reviewer authorship
5. candidate lane graphs are embedded inside `StructuredResolution.content["lanes"]`
   rather than written directly as graph truth
6. every automatic self-evolution run is traceable back to:
   - a source run
   - an evidence bundle
   - a blueprint track
   - a ratification result
7. blueprint mutation can auto-apply without human approval while remaining
   mission-bounded
8. run terminalization is computed through an explicit aggregation contract
9. the 10-hour chain budget and hybrid dedupe prevent uncontrolled auto-growth
10. self-evolution runs re-enter the same chat-to-resolution-to-graph mainline
   rather than creating a parallel execution path
