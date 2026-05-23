# phase: phase-13

# Phase 13 Spec: Core Memory Lifecycle

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-13/context_bundle.md`.
Brainstorm: `.hermes-loop/work/phase-13/brainstorm.md`.
Dispatch: `.hermes-loop/work/phase-13/god_dispatch.json`.

## Problem

Core memory already exists as a durable block store and is already rendered into the v3 context path, but the lifecycle is too permissive. A core update can still look like a direct text write unless we force it through a promotion path that carries source refs, approval, conflict handling, and history.

## Goal

Make core memory promotion source-backed, conflict-aware, history-preserving, and renderable through the real v3 path without changing defaults.

## Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change benchmark scoring or judge semantics.
- Do not claim benchmark improvement from structural lifecycle tests alone.
- Do not let manual store writes bypass the promotion lifecycle.

## Design

The promotion path should stay simple and explicit:

```text
recall / archival evidence
-> promotion candidate
-> conflict check
-> approval / provenance gate
-> core update or create
-> history
-> rendered block
```

### Promotion Boundary

`MemoryLifecycleService` owns candidate application. It decides whether a candidate creates a new core block or updates an existing one. The decision should be label-scoped, not silent:

- one live block per label is the normal case;
- a candidate that targets an existing label updates that block in place;
- if the label resolves to multiple live blocks, the apply step fails rather than choosing one silently.

### Conflict Rules

Conflict is not a separate demo layer. It is the condition where a candidate wants to update an existing core block.

Expected behavior:

- the update is approved first;
- the old block value is preserved in history;
- the new value replaces the old one in place;
- the block keeps source refs and provenance metadata;
- no duplicate core block is created for the same label.

### Read-Only Enforcement

Read-only enforcement must exist in both places that can mutate core blocks:

- `CoreMemoryService` rejects update / replace / append / delete on read-only blocks;
- `MemoryStore` rejects direct update / delete attempts on read-only records too.

This prevents a lower-level bypass from weakening the lifecycle contract.

### History and Deprecation

Core block changes must be soft and auditable:

- create emits an `add` history event;
- update emits a `update` or `replace` history event with before / after payloads;
- delete marks the block deleted and preserves its history;
- deleted blocks disappear from the default live listing but remain inspectable through `include_deleted=True`.

### Rendering and Accounting

`V3ContextComposer` should continue to render only persisted core blocks. It does not need to render pending candidates because the candidate is not durable yet.

The rendered core item must keep:

- the block label and text;
- source refs;
- token accounting;
- provenance metadata when present.

## Acceptance Criteria

- A promoted core candidate with an existing label updates the existing block in place.
- The update preserves old and new values in history.
- Read-only core blocks reject updates and deletes on service and store paths.
- Soft-deleted core facts remain in history and are hidden from default live listings.
- A v3 context build renders the approved core block with source refs and budget accounting intact.
- v1 fallback, v3 default, and kernel opt-in remain unchanged.

## Evidence Boundaries

- No LongMemEval / LoCoMo improvement claim unless a real benchmark gate is run.
- No default-kernel change.
- No prompt-only success claim.
- Any public smoke is structural only and only if the v3 public context path changes.
