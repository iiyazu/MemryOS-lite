# phase: phase-5

# Spec: Memory Lifecycle + Promotion Policy

## Goal

Add a lifecycle layer that decides what memory should be written, promoted,
rejected, or deferred across recall, archival, and core memory.

## Compatibility State

`shadow-read`

## Scope

This phase introduces:

- explicit memory write sources
- promotion candidates
- promotion policy
- add / update / delete / history semantics for lifecycle actions
- a narrow bridge from recall and archival memories into core memory

This phase does not change the default legacy context or make automatic
promotion live by default.

## Dependencies

- Phase-4 archival memory APIs must exist or be represented by narrow adapter
  interfaces.
- Core memory block storage and history already exist.
- Shared provenance types from `v3_contracts.py` already exist:
  `SourceRef`, `IdentityScope`, `MemoryHistoryEvent`, `ApprovalState`, and
  `CoreMemoryUpdate`.

## Functional Requirements

1. The system can represent promotion candidates with:
   - source layer
   - target layer
   - operation
   - content
   - source refs
   - identity scope
   - reason
   - confidence
   - lifecycle status
   - timestamps
   - metadata

2. The system recognizes three write sources:
   - explicit user/system instruction
   - Mem0-style message extraction
   - Letta-style sleep/consolidation jobs

3. Automatic promotion initially produces candidates only.

4. Core promotion requires one of:
   - explicit approval
   - a documented high-confidence policy
   - explicit source-backed provenance

5. Every applied lifecycle mutation must record history.

6. Promotion paths must be explicit for:
   - recall -> core
   - recall -> archival
   - archival -> core
   - document -> passage -> archival memory

## Non-Goals

- Do not make lifecycle writes part of the default legacy path.
- Do not add source-less automatic writes.
- Do not encode benchmark case IDs or answer strings into promotion logic.
- Do not make phase-6 composer/kernel depend on hidden side effects.

## Proposed Design

### Candidate model

Introduce a `PromotionCandidate` contract with the minimal fields needed for
traceable decisions. The candidate is a first-class record separate from the
final applied memory object.

### Lifecycle service

Introduce a small lifecycle service that:

- creates candidates from explicit instructions, extraction, or consolidation
- evaluates policy for candidate promotion
- applies approved writes to core or archival adapters
- appends memory history events for applied changes
- leaves rejected or deferred candidates auditable

### Policy behavior

- explicit instructions may apply immediately when source-backed
- extraction and sleep jobs only emit candidates first
- core promotion must be gated by approval or explicit high-confidence policy
- archival promotion may be allowed earlier than core, but still remains
  source-backed and history-traced

### Persistence boundary

The lifecycle layer should persist candidates and history, but should not own
archival schema details. It must call narrow archival interfaces from phase-4
instead of binding to internal tables.

## Acceptance Criteria

- Promotion candidates carry reason, source refs, and confidence.
- Automatic promotion only produces candidates at first.
- Core promotion requires explicit approval or a high-confidence policy.
- Add/update/delete events are tracked in memory history.
- Default v1/v2 behavior remains unchanged.

