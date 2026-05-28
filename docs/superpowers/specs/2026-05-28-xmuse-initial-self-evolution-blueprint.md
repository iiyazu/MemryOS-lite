# xmuse Initial Self-Evolution Blueprint

> Date: 2026-05-28
> Status: initial blueprint
> Scope: first human-provided `EvolutionBlueprintSet` for xmuse self-evolution
> Depends on:
> - `2026-05-28-xmuse-god-session-first-architecture-design.md`
> - `2026-05-28-xmuse-blueprint-anchored-self-evolution-design.md`

## Purpose

This document is the initial human-provided blueprint for xmuse
self-evolution.

It is the first active planning input for Architect GOD and Review GOD after
the GOD-session-first architecture and blueprint-anchored self-evolution loop
exist.

This is not an implementation plan.
It defines what xmuse should improve toward during the first automatic
self-evolution chain.

## Provenance

This blueprint incorporates lessons from prior WSL Codex / Hermes long-running
agent records:

- active goal must be explicit
- blueprint source must be read before planning
- lane work needs fresh context bundles when sessions are not durable
- heartbeat and evidence-based monitoring matter more than process presence
- ACK gates must reference actual artifacts, not stale success state
- stale runtime artifacts must be quarantined before promotion

These are lessons, not a directive to reuse `.hermes-loop` as the xmuse main
control plane.

xmuse remains centered on:

`chat -> proposal -> approved resolution -> lane graph -> execution run -> review -> terminal outcome -> self-evolution`

## EvolutionBlueprintSet v0

Minimum object identity:

- `blueprint_set_id`: `xmuse-self-evolution-v0`
- `title`: `xmuse autonomous delivery capability`
- `goal_statement`: `improve xmuse autonomous delivery capability`
- `version`: `0`
- `status`: `active`
- `source_spec_refs`:
  - `2026-05-28-xmuse-god-session-first-architecture-design.md`
  - `2026-05-28-xmuse-blueprint-anchored-self-evolution-design.md`

Mission envelope:

- xmuse may improve its own autonomous delivery system
- xmuse may update this blueprint inside that envelope after review
- xmuse must not redefine itself into an external product planner
- xmuse must not bypass chat-to-resolution-to-graph as the mainline

## Priority Policy

First-chain priority is not balanced across all tracks.

The first automatic chain should optimize for one concrete milestone:

`one complete self-evolution dry-run can terminalize as merged or high-quality blocked_for_input`

Track priority order:

1. `graph_authority`
2. `review_plane`
3. `self_evolution_loop`
4. `clarification_recovery`
5. `dashboard_auditability`
6. `reliability_hardening`
7. `orchestrator_decoupling`
8. `a2a_messages`
9. `a2a_protocol`

High priority does not mean inline preemption.
Self-evolution work starts only after the source run terminalizes.

## Tracks

### graph_authority

Intent:

- make graph/run truth authoritative enough for self-evolution triggers

Milestones:

- authoritative `LaneGraph` store exists and is used by execution projection
- graph/run terminal aggregation is explicit
- mixed MVP lane states normalize through one compatibility layer
- patch-forward and requeue descendants participate in lane-lineage closure

Acceptance signals:

- a run terminal outcome is explainable from graph, lane lineage, verdicts,
  final-action holds, and clarification objects
- no self-evolution trigger reads terminal status from one loose lane status

### review_plane

Intent:

- make review GOD a persistent auditor that emits formal verdict objects

Milestones:

- review work is represented as review tasks or inbox items
- Review GOD emits structured verdicts
- verdict ingestion drives lane transitions through the runtime adapter
- `approve`, `requeue`, `patch_forward`, and `terminate` are auditable

Acceptance signals:

- a merged lane has a verdict lineage
- a requeued or patch-forward lane preserves the original verdict relation
- review is not implemented as an execution subprocess status side effect

### self_evolution_loop

Intent:

- create the minimum closed loop from terminal run to next system-authored run

Milestones:

- `StructuredEvidenceBundle` exists with versioned curation policy and primary
  refs
- Architect GOD drafts `EvolutionProposal` and candidate graph
- Review GOD ratifies with `approve | narrow | reject`
- `narrow` forces architect redraft through `NarrowingDecision`
- guardrail decision records continuation outcome
- landing creates visible system-authored conversation and approved resolution
- candidate graph enters through `StructuredResolution.content["lanes"]`

Acceptance signals:

- one full self-evolution cycle can be traced from source run to spawned run
- dashboard or files can show evidence bundle, proposal, review decision,
  guardrail decision, and lineage

### clarification_recovery

Intent:

- make information shortage a resumable object, not a swallowed failure

Milestones:

- `ClarificationRequest` or equivalent blocked object exists
- run terminal aggregation can produce `blocked_for_input`
- provided information can resume the blocked graph or spawn a follow-up
  resolution

Acceptance signals:

- high-quality `blocked_for_input` records exact missing input and recovery
  path
- the system does not silently terminate when it needs information

### dashboard_auditability

Intent:

- let a human inspect self-evolution without reading raw runtime files

Milestones:

- dashboard read models expose graph status, verdict lineage, final-action
  holds, blocked objects, and self-evolution lineage
- state names are normalized across MVP and target semantics
- automatic self-evolution conversations are visible

Acceptance signals:

- a 15-minute monitoring checkpoint can be written from dashboard/read-model
  evidence
- no critical self-evolution decision is only visible in transient logs

### reliability_hardening

Intent:

- make long-running autonomous work recoverable and auditable

Milestones:

- heartbeat records exist for long-running runs or workers
- stale success artifacts are quarantined before promotion
- ACK-style gates check artifact consistency
- incidents classify as `watch`, `recover`, or `stop`

Acceptance signals:

- monitor can distinguish running, stalled, completed, invalid, and blocked
  states by evidence
- repeated failure does not create infinite automatic follow-up

### orchestrator_decoupling

Intent:

- decompose PlatformOrchestrator (1457 lines) and SelfEvolutionController (100k bytes) into focused submodules with a thin facade

Milestones:

- orchestrator.py becomes a ~300-line facade (装配 + 路由 only)
- execution lifecycle extracted to `platform/execution/{executor,review,gate,merger}.py`
- god selection extracted to `platform/selection/god_picker.py`
- prompt construction extracted to `platform/prompts/builders.py`
- verdict ingestion extracted to `platform/verdicts/writer.py`
- projection/dependents extracted to `platform/projection/dependents.py`
- controller.py becomes a ~400-line facade
- controller submodules: `proposal/{drafter,reviewer}`, `budget/window`, `evidence/aggregator`, `clarification/lifecycle`, `adapters/{lanes_reader,chat_reader}`
- Transport abstraction (`platform/messages.py`) with ExecuteRequest/Response/ReviewRequest/ReviewVerdict dataclasses
- SubprocessTransport wraps AgentSpawner as the initial implementation

Acceptance signals:

- no file in platform/ or self_evolution/ exceeds 500 lines
- existing integration tests remain green throughout migration
- mandatory unit tests pass for: review fallback parsing, god_picker mixed mode, reproject_dependents
- A2A phase can add new Transport implementations without modifying executor or review modules

Spec reference: `docs/superpowers/specs/2026-05-29-orchestrator-controller-decoupling-design.md`

### a2a_messages

Intent:

- formalize god-to-god message contracts for the three core communication lines (architect→execute, execute→review, review→execute rework)

Milestones:

- ExecuteRequest/ExecuteResponse/ReviewRequest/ReviewVerdict are the sole interface between orchestrator and Transport
- SubprocessTransport is the only place that knows about `codex exec` / `claude -p` CLI details
- MCPTransport added for long-lived god sessions (SSE channel)
- GodPicker extended with health-aware swap policy
- prompts/builders extended with per-runtime prompt variants if needed

Acceptance signals:

- adding a new Transport implementation requires zero changes to executor.py or review.py
- all god communication goes through Transport.send_execute / Transport.send_review
- no subprocess.run call exists outside of SubprocessTransport

Spec reference: `docs/superpowers/specs/2026-05-29-orchestrator-controller-decoupling-design.md` Section 6 + 11

### a2a_protocol

Intent:

- upgrade god communication from implicit state-machine transitions to an explicit, discoverable, versioned protocol

Milestones (B1-B4 sequential):

- B1: GodManifest dataclass + capability registration; orchestrator routes by capabilities not hardcoded role names
- B2: schema version negotiation; additive-only field upgrades; field-stripping downgrade for older gods
- B3: dead letter queue (SQLite `dead_letters` table); MCP tools `get_dead_letters` / `replay_dead_letter`; retry logic moves from orchestrator to Transport layer
- B4: multi-god collaboration — vote mode (per-lane configurable: majority/unanimous/weighted) + peer mode (single-round: A proposes → B reviews → done)

Acceptance signals:

- new god type can join by registering a manifest file, without modifying orchestrator
- version mismatch between platform and god produces a clear error, not silent corruption
- failed messages are queryable and replayable from DLQ
- vote mode can produce a merged verdict from N independent reviewers

Spec reference: `docs/superpowers/specs/2026-05-29-session3-blueprint-discussion.md` Section B1-B4

## First-Chain Target

The first chain should not try to perfect every track.

Target:

- manually implement enough substrate for one complete self-evolution dry-run
- provide this blueprint as the active planning input
- start xmuse self-evolution only after dry-run passes
- allow the GOD loop to propose future blueprint mutations after review

Dry-run pass conditions:

- preferred: spawned self-evolution run reaches `merged`
- acceptable: spawned self-evolution run reaches high-quality
  `blocked_for_input`

High-quality `blocked_for_input` means:

- missing information is explicit
- owner/source of information is explicit
- resume path is explicit
- no executable lane remains incorrectly marked ready

## Non-Regression Rules

Automatic blueprint mutation must preserve:

- `goal_statement`
- chat-to-resolution-to-graph mainline
- architect authorship for evolution proposal content
- review ratification
- controller guardrails
- explicit terminal aggregation
- visible lineage for every automatic self-evolution run

Automatic mutation may refine tracks, priorities, milestones, or acceptance
signals only when it preserves or strengthens the evidence requirement for
claiming progress.

