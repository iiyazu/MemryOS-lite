# phase: phase-13

## Problem

Core memory is close to a real lifecycle, but the current shape still allows two weak points: direct store writes can bypass the service guardrails, and candidate promotion jumps straight from approval to block creation without a clear conflict/deprecation step. That is enough for silent overwrite or sourceless mutation to slip through even though `CoreMemoryService` already enforces provenance and read-only checks.

This phase should stay structural. No benchmark gain should be claimed unless the default v3 context path changes and later case-level evidence proves it.

## Options

### Option A: Service-owned promotion lifecycle

Flow:

```text
evidence -> candidate -> conflict check -> approval/provenance gate -> core update -> history -> render
```

Pros:

- matches the current split between `MemoryLifecycleService` and `CoreMemoryService`;
- keeps approval and provenance logic in one place;
- easiest route to add explicit deprecation and conflict recording;
- fits Letta-style audited memory actions without turning the composer into policy logic.

Cons:

- requires a few more contract fields and test cases;
- may need one or two store helpers for stable update semantics.

### Option B: Store-level versioned checkpoints

Flow:

```text
evidence -> versioned block row -> checkpoint/history row -> current pointer -> render
```

Pros:

- strongest protection against overwrite;
- history and current value become mechanically linked.

Cons:

- touches the store more deeply than the current phase seems to need;
- risks turning Phase 13 into a schema migration phase;
- larger blast radius for v1/v3 compatibility.

### Option C: Composer-visible candidate overlay

Flow:

```text
evidence -> pending candidate overlay -> composer may show it -> later commit
```

Pros:

- easy to inspect during debugging;
- minimal write-path change at first.

Cons:

- weakest boundary between tentative evidence and durable core memory;
- highest risk of context rendering leakage;
- easiest way to end up with a demo-only phase.

## Recommendation

Choose **Option A**.

Why this fits the current code:

- `CoreMemoryService` already owns the mutation guardrails and history emission for service-mediated writes.
- `MemoryStore.update_core_memory_block()` is still a raw field overwrite path, so the lifecycle should avoid treating it as the policy boundary.
- `V3ContextComposer._core_items()` simply renders whatever blocks exist, so it should continue to receive only approved, source-backed blocks.
- `MemoryLifecycleService.apply_candidate()` is already the right place to insert conflict/deprecation logic before a core write.

## Likely Files Later

- `src/memoryos_lite/memory_lifecycle.py`
- `src/memoryos_lite/core_memory.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/context_composer.py`
- `tests/test_memory_lifecycle.py`
- `tests/test_context_composer.py`
- `tests/test_core_memory_store.py`

## What Would Count As Partial

- candidate creation and approval exist, but the actual core write still bypasses conflict/deprecation logic;
- read-only enforcement and source-ref checks work in `CoreMemoryService`, but raw store updates can still mutate blocks directly;
- history is appended, but old and new state are not both preserved in a reviewable way;
- the composer renders core blocks correctly, but it cannot distinguish approved core memory from a tentative candidate path.

## What Would Count As Demo-Only

- candidate objects exist only for tests or logging, not for real promotion;
- the phase only proves a happy-path `apply_candidate()` call that creates a block once;
- history is recorded, but overwrite prevention, deprecation, and read-only bypass checks are not exercised through the real store/service chain;
- any rendered candidate text appears in v3 context before approval.

## Key Risks

- silent overwrite: a new promotion replaces an existing stable fact without an explicit conflict decision;
- sourceless mutation: a write path accepts content without source refs or approved provenance;
- history loss: the previous value disappears instead of being retained as a traceable event;
- read-only bypass: a lower-level helper mutates a block that should have been frozen;
- context rendering leakage: unapproved candidate content shows up in `V3ContextComposer` output.

## Guardrails

- keep `v1` fallback unchanged;
- keep `v3` default unchanged;
- keep `MEMORYOS_AGENT_KERNEL=v1` opt-in only;
- do not claim LongMemEval or LoCoMo improvement from lifecycle wiring alone;
- prefer source-backed evidence over direct manual edits every time.
