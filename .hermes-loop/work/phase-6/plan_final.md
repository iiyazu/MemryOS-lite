# phase: phase-6

# Plan: Context Composer + Agentic Kernel

## TDD Order

1. Add tests for v3 feature-flag resolution and composer output shape.
2. Add tests for layered context assembly and budget diagnostics.
3. Add tests for kernel policy / approval persistence and continuation.
4. Implement the v3 composer and legacy adapter.
5. Implement the minimal kernel runner and trace persistence.
6. Run focused tests, then `uv run pytest -q`.

## Proposed Files

- `src/memoryos_lite/config.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/engine.py`
- `tests/test_context_composer.py`
- `tests/test_agent_kernel.py`

## Implementation Steps

### 1. Feature flags and contracts

Add resolved settings for `MEMORYOS_MEMORY_ARCH` and
`MEMORYOS_AGENT_KERNEL`. Keep the defaults on legacy paths. Add tests that
prove invalid flag values fail early and valid opt-in values resolve cleanly.

### 2. Layered composer

Implement a composer service that reads:

- task text
- core memory blocks
- recall evidence from the recall pipeline
- archival passages from the archival store
- recent messages from the message log

It should emit `ContextPackageV3` with budget decisions and diagnostics.

### 3. Legacy adapter

Teach `MemoryOSService.build_context()` to route to the v3 composer only when
the v3 flag is enabled. Otherwise it must keep the current legacy path.

### 4. Kernel runner

Add a minimal agentic step runner that persists trace events and returns a
continuation decision. Keep tool execution pluggable and policy-driven.

### 5. Verification

Run the new unit tests first, then the smallest focused integration slice, then
the full pytest suite.

## Verification Targets

- invalid feature-flag values are rejected
- v3 composer output includes layer diagnostics and budget decisions
- legacy build_context stays unchanged when the flag is off
- kernel traces are persisted and continuation decisions are explicit

