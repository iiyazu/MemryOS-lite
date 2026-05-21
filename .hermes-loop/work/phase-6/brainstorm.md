# phase: phase-6

# Brainstorm: Context Composer + Agentic Kernel

## Inputs

- Blueprint phase: `phase-6` / `Context Composer + Agentic Kernel`
- Target state: `opt-in-v3`
- Required scope:
  - layered composer
  - durable agentic step runner
  - tool policy and approval gating
  - legacy v1/v2 compatibility

## Current Code Signals

- `v3_contracts.py` already defines `ContextComposerRequest`,
  `ContextPackageV3`, `ContextLayerItem`, `LayerBudgetDecision`,
  `AgentStepRequest`, `AgentStepResult`, `ToolPolicyRule`,
  `ToolPolicyDecision`, `ApprovalState`, and the protocol interfaces.
- `engine.py` still routes through the legacy `ContextBuilder` and the
  opt-in `RecallPipeline`; there is no real layered composer yet.
- `core_memory.py`, `store.py`, and `retrieval/archival_searcher.py` already
  expose the underlying sources needed for the composer layers.
- `Settings` has the recall pipeline flag, but no explicit v3 composer/kernel
  feature flags yet.

## Approach Options

### Option A: Dedicated v3 composer + kernel adapter

Add a new composer module that produces `ContextPackageV3` from task, core,
recall, archival, and recent-message layers. Add a separate kernel module that
turns an `AgentStepRequest` into a persisted step result and continuation
decision.

Tradeoff: a bit more code, but the boundaries stay clear and the legacy engine
path remains untouched except for flag-gated routing.

### Option B: Expand `engine.py` in place

Keep the logic inside `MemoryOSService` and teach `build_context` and agent
execution to branch on the new flags.

Tradeoff: fewer files, but `engine.py` is already doing too much. This risks a
hard-to-review tangle and makes the v3 boundary harder to test.

### Option C: Kernel first, composer later

Add the agentic step runner and approval plumbing before the layered composer.

Tradeoff: this is the wrong order for the current blueprint. The kernel needs
the layered context contract first or it will just rewrap the old path.

## Recommendation

Use Option A.

The composer should be a focused service that can be tested independently with
fake store data. The kernel should be a second service that consumes the
composer output and persists trace / approval state without changing the legacy
turn loop by default.

