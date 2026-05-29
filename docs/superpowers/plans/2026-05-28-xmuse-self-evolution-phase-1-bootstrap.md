# xmuse Self-Evolution Phase 1 Bootstrap Plan

> Date: 2026-05-28
> Status: active implementation plan
> Scope: minimum substrate for one blueprint-anchored self-evolution dry-run

## Goal

Implement the smallest xmuse slice that can prove:

`terminal run -> evidence bundle -> architect-authored proposal -> review decision -> guardrail decision -> visible conversation -> approved resolution -> planner graph -> projected ready lane`

The implementation stays on the MVP mainline and does not revive the legacy
master loop.

## Implementation Slices

1. Add self-evolution object models and append-only JSON store.
2. Add explicit graph-level terminal aggregation over lane lineage.
3. Generate structured evidence bundles with selection policy and primary refs.
4. Draft a bootstrap evolution proposal through an architect-equivalent path.
5. Ratify through a review-equivalent decision, including explicit
   `NarrowingDecision` for `narrow`.
6. Enforce controller guardrails before landing.
7. Land through `ChatStore.approve_proposal()` so executable lanes enter
   `StructuredResolution.content["lanes"]`.
8. Run planner normalization and ready-lane projection into `feature_lanes.json`.
9. Expose self-evolution stores through dashboard read-model API.
10. Verify with focused tests and one real dry-run artifact chain.

## Phase 1 Exit Evidence

Required artifacts:

- source run graph and lane state
- run terminal aggregation
- evidence bundle
- evolution proposal
- review decision
- guardrail decision
- spawned conversation
- spawned approved resolution
- spawned lane graph
- projected self-evolution lane
- dashboard `/api/self-evolution` read model

## Review Note

External subagent review was attempted three times during bootstrap. The service
returned 503 or timed out, so the run continues under the runbook API/tool
interruption policy with local review, expanded tests, and explicit residual
risk tracking.
