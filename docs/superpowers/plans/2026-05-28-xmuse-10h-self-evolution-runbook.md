# xmuse 10h Self-Evolution Runbook

> Date: 2026-05-28
> Status: runbook
> Scope: overnight operator protocol for bringing xmuse to self-iteration and
> monitoring the first automatic chain
> Depends on:
> - `2026-05-28-xmuse-god-session-first-architecture-design.md`
> - `2026-05-28-xmuse-blueprint-anchored-self-evolution-design.md`
> - `2026-05-28-xmuse-initial-self-evolution-blueprint.md`

## Purpose

This runbook constrains the 10-hour overnight work session.

It has two phases:

1. manually implement xmuse until one self-evolution dry-run is possible
2. start xmuse self-evolution and monitor it every 15 minutes

The runbook controls execution and monitoring.
The blueprint controls what self-evolution should optimize for.

## Active Goal

Active goal for this 10-hour session:

`Bring xmuse to the minimum state where it can run one blueprint-anchored self-evolution cycle through the standard chat-to-resolution-to-graph mainline, then monitor the first automatic self-evolution chain without human approval unless a stop condition is reached.`

Every checkpoint must be judged against this goal.

## Operating Boundaries

Hard rules:

- do not revert unrelated user or agent changes
- do not revive `.hermes-loop` as the xmuse execution mainline
- do not treat old master loop artifacts as authoritative runtime state
- do not start automatic self-evolution before dry-run entry criteria pass
- do not allow self-evolution to redefine the mission envelope
- do not make human review mandatory for ordinary GOD review verdicts
- do not keep retrying the same failing path without new evidence

Allowed implementation direction:

- use the current xmuse MVP mainline
- borrow reliability patterns from WSL Codex / Hermes records
- add minimal substrate required by the self-evolution specs
- prefer stores/read models over loose lane metadata for new self-evolution
  objects

## Phase 1: Manual Bootstrap

Objective:

- implement enough of the target architecture for one complete self-evolution
  dry-run

Required inputs:

- `xmuse/HANDOFF.md`
- `2026-05-28-xmuse-god-session-first-architecture-design.md`
- `2026-05-28-xmuse-blueprint-anchored-self-evolution-design.md`
- `2026-05-28-xmuse-initial-self-evolution-blueprint.md`
- current implementation under `xmuse/` and `src/xmuse_core/`

Minimum implementation checklist:

- GOD session identity is stable enough for architect/review/execute roles
- lane graph store and projection are authoritative enough for dry-run
- run terminal aggregation can produce `merged`, `terminated`, or
  `blocked_for_input`
- evidence bundle can be generated from a terminal run
- Architect GOD or equivalent agent path can draft an evolution proposal
- Review GOD or equivalent review role can ratify `approve | narrow | reject`
- `narrow` records constraints and returns to architect redraft
- guardrail decision can produce `continue | hold | stop`
- landing creates a visible system-authored conversation
- approved resolution serializes executable lanes into
  `StructuredResolution.content["lanes"]`
- planner projects those lanes into the execution surface
- read models expose enough lineage for monitoring

Phase 1 verification:

- run focused xmuse tests for touched modules
- run one manual dry-run from terminal source run to spawned evolution run
- inspect produced artifacts for source run, evidence bundle, proposal, review
  decision, guardrail decision, spawned conversation, spawned resolution, graph,
  and terminal outcome

Phase 1 exit criteria:

- dry-run reaches `merged`, or
- dry-run reaches high-quality `blocked_for_input`

High-quality `blocked_for_input` requires:

- explicit missing input
- explicit owner/source of the input
- explicit resume path
- no executable lane incorrectly left ready
- no hidden terminal failure disguised as blocked

If Phase 1 cannot meet exit criteria:

- write a short blocker note
- classify the failure as `recover` or `stop`
- do not enter Phase 2

## Phase 2: Automatic 10h Chain

Objective:

- start xmuse self-evolution after Phase 1 dry-run passes
- monitor every 15 minutes until the 10-hour budget expires or a stop condition
  triggers

Entry checklist:

- initial blueprint is present and readable
- current run has terminalized through explicit aggregation
- dry-run evidence is available
- dashboard/read models expose current run, graph, verdict, guardrail, and
  lineage evidence
- no stale dry-run success artifact is being reused as current proof
- git diff is understood well enough to avoid reverting unrelated changes

Start rule:

- open the first automatic self-evolution run as high priority
- do not inline-preempt active external execution
- allow GOD review verdicts to be default review authority
- no human audit gate is required unless a stop condition is reached

## 15-Minute Monitoring Checkpoint

Every checkpoint must record:

- timestamp
- elapsed time in the 10-hour window
- current run id, resolution id, and graph id if available
- lane counts by normalized state
- open lane lineages
- newest verdicts
- open final-action holds
- open clarification or blocked objects
- newest self-evolution proposal status
- guardrail decision status
- spawned conversation/resolution/run links
- latest test or smoke command result if any changed
- notable git diff or generated artifacts
- incident level: `watch`, `recover`, or `stop`
- next action before the next checkpoint

Evidence sources should prefer:

- authoritative stores
- read models
- graph files
- verdict records
- final-action records
- logs only when no structured artifact exists

Do not judge progress from process liveness alone.

## Incident Levels

### watch

Use `watch` when the system is slow or noisy but still producing usable
evidence.

Examples:

- lane worker still running within expected duration
- one retry occurred with new evidence
- dashboard read model lags behind store but store is coherent
- non-blocking test warning appears

Action:

- record evidence
- keep monitoring
- do not rewrite architecture

### recover

Use `recover` when the chain is blocked by a fixable implementation or runtime
problem.

Examples:

- runner stalled but state is intact
- verdict ingestion failed
- graph projection missed a ready lane
- final-action hold cannot resolve
- dashboard/read model disagrees with authoritative store
- focused tests fail after a local change

Action:

- stop automatic advancement for the affected run
- diagnose from structured state first
- make the smallest necessary fix
- run focused verification
- resume only when the evidence is coherent

### stop

Use `stop` when automatic continuation would be unsafe or unproductive.

Stop conditions:

- 10-hour budget expired
- same failure mode repeats three times without new evidence
- mission envelope drift
- proposal tries to bypass chat-to-resolution-to-graph
- controller or review tries to become hidden final content author
- state corruption prevents reliable lineage reconstruction
- a required human input is missing and no valid `blocked_for_input` recovery
  object exists
- continuing would risk reverting unrelated user or agent work

Action:

- stop opening new automatic self-evolution runs
- preserve current artifacts
- write a terminal status note
- leave existing in-flight work in an auditable state

## Stale Artifact Policy

Before treating any artifact as current evidence:

- confirm it references the current run or proposal id
- confirm it was produced after the current phase started
- confirm it is consistent with the active blueprint version
- quarantine stale success, ACK, or dry-run artifacts from earlier attempts

Stale artifacts may be retained for diagnosis.
They must not be used as current promotion evidence.

## Timeout Policy

Lane worker timeout:

- if a one-shot worker has no observable output for 3 hours, terminate it if
  safe
- retry once only if state remains coherent
- after the second timeout, classify as `recover` or `stop`

API or tool interruption:

- retry three times with short delay
- if still failing, wait and re-check structured state
- do not abandon the run solely because a transient API call failed

Monitoring gap:

- if a 15-minute checkpoint is missed, the next checkpoint must explain the gap
- if the gap hides state uncertainty, classify at least `recover`

## Completion Criteria

The 10-hour session is successful if:

- Phase 1 manually reaches dry-run pass criteria
- Phase 2 starts only after Phase 1 passes
- every automatic self-evolution run is traceable to the active blueprint
- every continuation has evidence bundle, proposal, review decision, guardrail
  decision, and lineage evidence
- monitoring checkpoints are evidence-based
- stop/recover decisions are recorded when needed

The session is not successful if:

- automatic self-evolution starts without a passing dry-run
- progress is claimed from raw logs without structured lineage
- stale artifacts are reused as current proof
- the system drifts outside the mission envelope
- repeated failures create infinite follow-up work

