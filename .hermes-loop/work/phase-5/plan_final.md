# phase: phase-5

# Plan: Memory Lifecycle + Promotion Policy

## TDD Order

1. Add tests for candidate creation and state transitions.
2. Add tests for source-backed enforcement and approval-gated core promotion.
3. Add tests for recall -> archival and archival -> core promotion routing.
4. Implement the lifecycle service and candidate contract.
5. Wire history writes through the existing memory history model.
6. Run focused tests, then full pytest.

## Proposed Files

- `src/memoryos_lite/memory_lifecycle.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/core_memory.py`
- `tests/test_memory_lifecycle.py`
- `tests/test_v3_contracts.py`
- `tests/test_core_memory_service.py`

## Implementation Steps

### 1. Candidate contract and policy surface

Define a small `PromotionCandidate` model and lifecycle status enum in the
shared contracts layer. Keep it provenance-heavy and storage-agnostic.

### 2. Lifecycle service

Implement a service that accepts explicit instructions, extraction results, and
sleep/consolidation outputs, then emits candidates or applies approved writes.

### 3. History wiring

Record all applied updates, replacements, deletions, approvals, and rejections
as `MemoryHistoryEvent` entries.

### 4. Adapters

Bridge recall and archival objects through narrow adapters so phase-5 does not
depend on phase-4 storage internals.

### 5. Verification

Run the smallest relevant test slice first, then `uv run pytest -q`.

## Verification Targets

- promotion candidates are persisted or at least serializable
- source-less writes are rejected
- approved manual provenance can unblock writes
- default legacy behavior remains unchanged

