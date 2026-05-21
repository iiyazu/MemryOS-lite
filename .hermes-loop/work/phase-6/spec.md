# phase: phase-6

# Spec: Context Composer + Agentic Kernel

## Goal

Add an opt-in v3 composer that assembles layered memory context and a durable
agentic kernel that can run a single auditable step without breaking the legacy
v1/v2 paths.

## Compatibility State

`opt-in-v3`

## Scope

This phase introduces:

- a layered context composer
- a durable agentic step runner
- tool policy and approval gating
- v3 diagnostics for layer inclusion, budget decisions, and continuation
- feature-flagged routing so legacy context building remains available

This phase does not make v3 the default path.

## Dependencies

- Phase-5 lifecycle contracts and provenance types already exist.
- Core memory APIs and archival search/store APIs already exist.
- Existing `ContextPackage` and legacy `build_context` behavior must remain
  readable for current callers.

## Functional Requirements

1. Add explicit feature flags for:
   - `MEMORYOS_MEMORY_ARCH=v3`
   - `MEMORYOS_AGENT_KERNEL=v1`

2. Build a v3 composer that returns:
   - task item
   - core memory items
   - recall evidence
   - archival passages or archival documents
   - recent messages
   - fallback items when space remains

3. Record per-layer diagnostics:
   - layer name
   - reason
   - score or priority
   - token estimate
   - source refs
   - budget decision

4. Keep `ContextPackage` compatibility by routing the v3 package through an
   adapter payload and metadata field rather than replacing the legacy schema.

5. Add a durable agentic step runner contract that can:
   - sanitize input messages
   - resolve tool policy decisions
   - request or resume approval
   - execute a tool call
   - persist assistant, tool, and approval trace events
   - emit a continuation decision

6. Keep tool policy explicit:
   - no implicit allow without a matching rule
   - approval requirements must be durable
   - failed or pending approvals must be observable

## Non-Goals

- Do not make v3 default.
- Do not remove legacy `ContextBuilder` or `RecallPipeline`.
- Do not require real tool execution for every test.
- Do not let the new kernel bypass source-backed or approval-backed mutation
  rules.

## Proposed Design

### Composer

Introduce a dedicated composer service that reads from the store and retrieval
helpers, then emits `ContextPackageV3`. The service should build layers in a
fixed order:

1. task
2. core memory
3. recall evidence
4. archival passages or documents
5. recent messages
6. fallback items

The composer should stop once the budget is exhausted and record every drop in
diagnostics.

### Kernel

Introduce a small agentic step runner with explicit policy and approval
dependencies. The runner should accept a composed context, produce a durable
step id, persist trace events, and return a continuation decision.

### Adapter Surface

`MemoryOSService.build_context()` should keep the legacy return type by default
and only emit v3-compatible metadata when the v3 flag is set. This preserves
current CLI/API consumers while giving opt-in callers access to the richer
composer data.

## Acceptance Criteria

- The v3 composer can assemble a layered package from the store.
- Budget drops are explainable per layer.
- Tool policy decisions and approval state are explicit and durable.
- Legacy `build_context` behavior remains intact when the v3 flag is off.
- The new path is opt-in only.

