# phase: phase-14

# Execute Self-Review

Status: PASS.

Context source: `.hermes-loop/work/phase-14/context_bundle.md`.

## What Real Chain Changed?

Phase 14 changed the opt-in kernel memory-action chain, not the default public benchmark answer path.

- `kernel_loop`: approved `archive_write` now produces `tool_executed` followed by durable `tool_verified`, and failed post-action verification is traced as `tool_verified(ok=False)` instead of being silently omitted (`src/memoryos_lite/agent_kernel.py:392`, `src/memoryos_lite/agent_kernel.py:409`, `src/memoryos_lite/agent_kernel.py:424`).
- `store`: successful `archive_write` still writes real archival memory and same-session archive attachment, then verification reads real history, passage, attachment, and same-session eligibility state (`src/memoryos_lite/agent_kernel.py:121`, `src/memoryos_lite/agent_kernel.py:156`, `src/memoryos_lite/agent_kernel.py:179`).
- `retrieval/context_composer`: verification checks `list_archival_passages_for_scope(ArchiveEligibilityScope(session_id=...))`, and tests prove the written archival memory becomes a v3 archival context item (`src/memoryos_lite/agent_kernel.py:199`, `tests/test_agent_kernel.py:525`).
- `approval replay`: pending approvals now carry a request fingerprint, and replay rejects fingerprint mismatches before execution (`src/memoryos_lite/agent_kernel.py:353`, `src/memoryos_lite/agent_kernel.py:495`, `src/memoryos_lite/agent_kernel.py:565`).
- `public_eval`: the opt-in kernel smoke trace now expects `tool_verified`; the default-off benchmark smoke still expects no kernel trace (`tests/test_public_benchmarks.py:3271`, `tests/test_public_benchmarks.py:3337`).

`ToolExecutionResult` gained a structured `verification` payload for this trace/message contract (`src/memoryos_lite/v3_contracts.py:641`).

## What Is Still Demo-Only Or Partial?

- Kernel execution remains opt-in and narrow: only `archive_write` is supported; `core_memory_append` and `core_memory_replace` are explicitly denied rather than implemented (`tests/test_agent_kernel.py:180`).
- The public benchmark kernel step is still a structural probe, not an answer-quality improvement mechanism. It writes "Benchmark question reviewed..." after context construction and should not be counted as LongMemEval/LoCoMo retrieval or answer movement.
- Verification proves real store visibility and same-session v3 archival eligibility, but it is not a full Letta-style maintenance planner, autonomous tool selector, or core-memory mutation surface.
- No full-chain LongMemEval or LoCoMo case matrix was rerun for this phase; the phase intentionally avoids a benchmark improvement claim.

## What Tests Proved The Behavior?

Self-review reran:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Result: `11 passed in 9.26s`.

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Result: `2 passed in 3.08s`.

```bash
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q
```

Result: `2 passed in 0.02s`.

The phase result artifact also records:

- `uv run pytest -q` -> `470 passed, 1 warning in 619.87s`;
- `uv run ruff check .` -> `All checks passed!`.

Behavior covered by tests:

- approved replay emits `kernel_step_started -> tool_policy_decision -> approval_granted -> tool_executed -> tool_verified -> kernel_step_completed` (`tests/test_agent_kernel.py:251`);
- successful verification records `status=verified`, same-session attachment, and session eligibility (`tests/test_agent_kernel.py:300`);
- replay tampering is denied with no execution, verification, tool message, or memory write (`tests/test_agent_kernel.py:376`);
- execution without store visibility emits negative verification and no successful tool-result message (`tests/test_agent_kernel.py:440`);
- unsupported memory tools are denied without execution, verification, or writes (`tests/test_agent_kernel.py:180`);
- default public benchmark kernel traces remain empty unless `memoryos_agent_kernel="v1"` is set (`tests/test_public_benchmarks.py:3271`, `tests/test_public_benchmarks.py:3290`).

## Which Benchmark Cases Moved Or Regressed?

No LongMemEval or LoCoMo case-level movement was measured or claimed in this phase.

- LongMemEval moved cases: none reported.
- LongMemEval regressions: none reported.
- LoCoMo moved cases: none reported.
- LoCoMo regressions: none reported.
- Pass-to-fail / fail-to-pass lists: not applicable for this structural kernel-loop phase.

The public benchmark tests only prove default-off kernel behavior and opt-in trace shape. They do not establish benchmark quality movement.

## Defaults And Fallbacks

v1 fallback, v3 default, and kernel opt-in remain intact.

- `Settings.memoryos_memory_arch` still defaults to `"v3"` and `Settings.memoryos_agent_kernel` still defaults to `"off"` (`src/memoryos_lite/config.py:29`).
- `Settings.resolved_memory_arch` still accepts only `"v1"` or `"v3"` (`src/memoryos_lite/config.py:67`).
- `MemoryOSService` only constructs `SimpleAgentStepRunner` when `settings.resolved_agent_kernel == "v1"` (`src/memoryos_lite/engine.py:1490`).
- v3 context routing remains tied to `resolved_memory_arch == "v3"`, so `MEMORYOS_MEMORY_ARCH=v1` remains the explicit fallback path (`src/memoryos_lite/engine.py:2124`).
- Settings tests confirm default v3 with kernel off and explicit kernel opt-in (`tests/test_context_composer.py:33`, `tests/test_context_composer.py:40`).

## Review Decision

PASS: REVIEW can proceed because the changed chain is real enough for the phase objective: approved opt-in `archive_write` now writes durable memory, verifies real store/session eligibility, persists positive and negative verification traces, denies replay tampering, and leaves defaults untouched.

No benchmark improvement claim is made.
