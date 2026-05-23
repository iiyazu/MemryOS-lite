# phase: phase-14

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Situation

Phase 13 already proved the store/core-memory lifecycle and the v3 composer path.
Phase 12 already proved the archival/RAG bridge. The remaining kernel loop is
still narrow: `SimpleAgentStepRunner` can request approval, resume approval, run
`archive_write`, and persist traces, but it does not yet prove a full audited
memory-action cycle with an explicit verification step.

Current baseline for the opt-in kernel:

- only `archive_write` is supported by `SimpleToolExecutionManager`;
- approval replay is already guarded on session, tool name, and requested action;
- same-session archive attachment creation already exists;
- public benchmark kernel path stays opt-in and default-off.

## Options

### Option A: Verify `archive_write` only

Keep the kernel tool surface at `archive_write` and add an explicit
post-execution verification step that proves the write is visible in the real
store and v3 context path.

What this would do:

- emit a durable verification trace after a successful tool execution;
- check that the archival memory exists in the store;
- check that the same-session archive attachment or archival passage is visible
  to the v3 composer;
- keep unsupported tools denied, not silently remapped.

Tradeoffs:

- smallest change;
- lowest regression risk;
- still real, because the kernel step would now prove a memory-action effect
  instead of only logging execution.

Risk:

- if verification only checks the tool payload or a mock, it becomes demo-only.

### Option B: Expand the kernel to core-memory tools

Add kernel support for one or more core-memory actions such as
`core_memory_update` or `memory_deprecate`, reusing the phase-13 lifecycle
service and store audit hooks.

Tradeoffs:

- closer to Letta semantics;
- broader memory-action coverage;
- higher implementation and review cost.

Risk:

- this can turn into a half-wired tool surface unless each tool gets a real
  approval, store, and verification path;
- it is easy to overfit phase-14 into a tool inventory instead of an audited
  loop.

### Option C: Build a generic kernel action-verifier abstraction

Introduce a small verifier registry so each supported tool declares how it is
executed, approved, and verified.

Tradeoffs:

- cleaner long-term shape;
- easier to add future memory tools;
- conceptually closest to a Letta-style tool executor boundary.

Risk:

- likely too much architecture for phase 14;
- easy to spend the phase on abstraction instead of proving one real loop end
  to end.

## Recommendation

Choose Option A for this phase.

Reasoning:

- the current kernel surface already has a real supported tool;
- phase 13 already delivered the core-memory lifecycle, so phase 14 does not
  need to reopen that surface unless a test proves a missing capability;
- a durable verification trace after `archive_write` is the smallest credible
  way to make the kernel loop auditable without broadening the tool set;
- it keeps the opt-in boundary intact and avoids accidental benchmark claims.

If RED evidence later shows that `archive_write` is insufficient to satisfy the
agent-loop contract, then phase 14 can narrow-scope a follow-up to a specific
core-memory tool, not a generic tool surface.

## What Would Be Demo-Only Or Partial

- A trace that says a tool executed, but does not verify the real store/context
  effect.
- A verification hook that inspects only the request payload or a mocked
  response.
- A kernel path that accepts unsupported tools by falling back to another tool
  or to a no-op.
- A new tool surface that has no replay integrity checks or no store history.
- A change that only affects public benchmark reporting without changing the
  real kernel path.

## RED Tests To Add First

Add failing assertions before production changes:

1. `tests/test_agent_kernel.py`
   - a successful approved `archive_write` must emit a new verification trace
     after `tool_executed`;
   - the verification trace must prove the archival memory exists in the real
     store and is visible to the v3 composer.
2. `tests/test_agent_kernel.py`
   - approval replay tampering must still produce zero side effects and no
     verification trace.
3. `tests/test_agent_kernel.py`
   - unsupported tool names must be denied explicitly, not remapped.
4. `tests/test_public_benchmarks.py`
   - kernel trace remains empty by default;
   - when `MEMORYOS_AGENT_KERNEL=v1` is enabled, the trace shape includes the
     new verification event.

## Why Kernel Stays Opt-In

The kernel path is an experimental memory-action controller, not the default
memory architecture. Default v3 public behavior must stay unchanged until there
is larger-sample evidence. Any kernel improvement here should be judged on
traceability and correctness, not on benchmark score movement.

