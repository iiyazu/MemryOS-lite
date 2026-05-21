# phase: phase-5

# Brainstorm: Memory Lifecycle + Promotion Policy

## Inputs

- Blueprint phase: `phase-5` / `Memory Lifecycle + Promotion Policy`
- Target state: `shadow-read`
- Required write sources:
  - explicit user/system instruction
  - Mem0-style message extraction
  - Letta-style sleep/consolidation job
- Required promotion paths:
  - recall -> core
  - recall -> archival
  - archival -> core
  - document -> passage -> archival memory

## Current Code Signals

- `v3_contracts.py` already defines shared provenance and lifecycle primitives:
  `SourceRef`, `IdentityScope`, `MemoryHistoryEvent`, `CoreMemoryUpdate`,
  `ArchivalDocument`, `ArchivalPassage`, and `ArchivalMemory`.
- `core_memory.py` already enforces source refs or approved manual provenance
  for core writes, and writes history through `MemoryHistoryEvent`.
- `store.py` persists core memory blocks and core history, but has no archival
  store tables yet; phase-5 must depend on phase-4 archival APIs rather than
  reusing `MemoryPage` / `MemoryItem` as the new lifecycle target.
- Legacy Page/Item tools still exist and must remain adapter/reference paths,
  not promotion destinations.

## Approach Options

### Option A: Candidate-first lifecycle service

Add a lifecycle layer that produces `PromotionCandidate` records first. Direct
writes are allowed only for explicit user/system instructions with source refs
or approved manual provenance. Extraction and sleep jobs create candidates with
reason, confidence, source refs, and intended destination.

Tradeoff: adds an intermediate object and more tests, but matches the blueprint:
automatic promotion only produces candidates first, and core promotion remains
approval-gated.

### Option B: Direct writers with policy checks

Implement writers for core and archival layers immediately. The policy engine
decides whether a write is accepted, rejected, or deferred.

Tradeoff: simpler surface, but it risks hidden automatic writes before the
agentic approval gate exists. This is too aggressive for `shadow-read`.

### Option C: Policy-only planning layer

Only define promotion policies and diagnostics without persisting candidates.

Tradeoff: low risk and fast, but does not satisfy lifecycle acceptance because
promotion candidates and add/update/delete history cannot be exercised.

## Recommendation

Use Option A.

Phase-5 should introduce a small lifecycle service and candidate contract that
can read recall/core/archival objects, emit promotion candidates, and apply only
explicitly approved or explicit-instruction writes. This keeps phase-5 in
`shadow-read`, preserves legacy defaults, and gives phase-6 composer/kernel a
clear object to approve or reject later.

## Candidate Shape

Minimum fields:

- `id`
- `source_layer`
- `target_layer`
- `operation`
- `content`
- `source_refs`
- `identity_scope`
- `reason`
- `confidence`
- `status`
- `created_at`
- `approved_at` / `rejected_at`
- `metadata`

Allowed statuses:

- `candidate`
- `approved`
- `rejected`
- `applied`
- `superseded`

## Writer Boundaries

- Explicit user/system instruction:
  - may write through lifecycle service if source refs or approved manual refs
    are present.
- Mem0-style extraction:
  - creates candidates only.
- Sleep/consolidation job:
  - creates candidates and archival documents/passages/memories only through
    phase-4 archival APIs.
- Core promotion:
  - requires approval or a high-confidence policy explicitly encoded in the
    lifecycle service.

## Risks

- Phase-4 archival APIs may still be in flux. Phase-5 plan should define a
  narrow dependency interface instead of assuming final storage details.
- Candidate confidence can become a fake quality signal. Tests should assert
  provenance and state transitions, not answer-quality gains.
- Core promotion can pollute always-in-context memory. Default behavior must
  stay unchanged and core writes must remain source-backed.

## Acceptance Mapping

- Promotion candidates carry reason, source refs, and confidence:
  candidate contract and store tests.
- Automatic promotion only produces candidates at first:
  extraction and sleep/consolidation tests assert no direct core/archival write.
- Core promotion requires explicit approval or high-confidence policy:
  policy tests cover reject/defer/apply paths.
- Add/update/delete events are tracked in memory history:
  lifecycle application writes `MemoryHistoryEvent` for core and archival
  mutations.
