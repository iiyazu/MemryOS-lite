# phase: phase-14

# Kernel Agent Graduation Blueprint Amendment Candidate

Spec source: `docs/superpowers/specs/2026-05-24-kernel-agent-graduation-blueprint-design.md`.

Status: promoted into `.hermes-loop/blueprint.md` as an active blueprint
section; not a completed phase artifact and not an ACK.

## Trigger

The current Phase 14+ path was reviewed against Letta's agent/tool execution
model and MemoryOS Lite's existing core, recall, archival, lifecycle, and v3
composer infrastructure. The review found that the current narrow kernel path
can become a credible graduation route only if it gains a bounded control-plane
contract and keeps benchmark gold fields outside executable memory actions.

## Decision Candidate

Adopt a staged kernel graduation sequence:

```text
K0 Kernel Contract Freeze
-> K1 Audited Control Plane
-> K2 Hybrid Tool Selection
-> K3 Graduated Memory Tools
-> K4 Maintenance Planner And Repair Eval
-> K5 Graduation Governance
```

## Immediate Impact On Phase 14

Phase 14 remains narrow and opt-in. It should absorb only K0/K1 requirements:

- contract records for tool call, approval, execution result, verification, and
  trace;
- approval replay binding to pending step/tool-call identity or request
  fingerprint;
- positive and negative verification trace semantics;
- durable tool-return verification summary;
- real store/history/scope/v3 context visibility checks for `archive_write`;
- unchanged default-off kernel behavior.

## Proposed Mapping For Later Phases

The existing later-phase intent should be reviewed against this mapping:

- existing Phase 15 should become or contain K2, followed by K4 planner work
  only after hybrid selection contracts are proven;
- existing Phase 16 should map to K3 tool-surface work through service-backed
  executors;
- existing Phase 17 should map to K4 opt-in repair smoke plus clean-store or
  held-out validation;
- existing Phase 18 should map to K5 governance and promotion decision.

God should not reorder active phase state solely from this candidate. It should
promote a documented amendment during an explicit adjustment or reviewed ACK
transition.

Promotion note:

- promoted into active blueprint under `Kernel Agent Graduation Blueprint`;
- Phase 14 is mapped to K0/K1;
- Phase 15 is mapped to K2 first, then K4 planner work;
- Phase 16 is mapped to K3 graduated memory tools;
- Phase 17 is mapped to K4 repair smoke and validation setup;
- Phase 18 is mapped to K5 governance;
- `.hermes-loop/state.json` is intentionally unchanged.

## Non-Negotiable Boundaries

- External kernel enablement remains opt-in unless separately approved.
- Once enabled, the graduated kernel is designed to default to hybrid tool
  selection: deterministic candidate routing, constrained LLM selection, and
  deterministic fallback.
- Tool selection cannot invent unregistered tools.
- Memory writes route through named domain services and verification contracts.
- `expected_source_ids`, expected answers, gold failure classes, and
  benchmark-targeted repair ids remain eval-only sidecars.
- Same-slice repair evidence is structural smoke only; no promotion claim may
  rely on it without clean-store or held-out validation.

## Required God Review Questions

- Should the active Phase 15 order be adjusted so hybrid selection precedes
  maintenance planning?
- Which current phase artifacts become stale if K0-K5 is promoted?
- What exact clean-store or held-out gate will qualify K5 graduation evidence?
- Should K0 be introduced as a new explicit phase or embedded as the first
  deliverable of Phase 14 adjustment/repeat?
