# phase: phase-14

# Phase 14 Result

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

## Summary

Phase 14 implemented the smallest audited opt-in kernel memory-action loop from
`plan_final.md`.

Real chain changes:

- `kernel_loop`: approved `archive_write` now emits a durable `tool_verified`
  trace after `tool_executed`; negative verification is also durable.
- `store`: verification checks real archival memory history, passage existence,
  same-session archive attachment, and archive eligibility.
- `retrieval` / `context_composer`: verification uses
  `list_archival_passages_for_scope(ArchiveEligibilityScope(session_id=...))`
  so a successful memory action must be eligible for the real same-session v3
  archival path.
- `public_eval`: opt-in kernel trace shape now includes `tool_verified`; default
  public benchmark behavior remains kernel-off with empty trace events.

No LongMemEval or LoCoMo benchmark quality claim is made from this phase. The
work is structural kernel-loop evidence only, scoped to `MEMORYOS_AGENT_KERNEL=v1`.

## RED Evidence

Recorded in `.hermes-loop/work/phase-14/red_result.md`.

RED failures were added before production changes:

- successful approved `archive_write` lacked `tool_verified`;
- replay with same `approval_id` could proceed without original request-binding
  verification;
- execution-only archive writes did not emit durable negative verification;
- opt-in public benchmark kernel trace lacked `tool_verified`.

## Implementation Evidence

Production files changed:

- `src/memoryos_lite/agent_kernel.py`;
- `src/memoryos_lite/v3_contracts.py`.

Tests changed:

- `tests/test_agent_kernel.py`;
- `tests/test_public_benchmarks.py`.

Behavior now covered:

- approved `archive_write` emits
  `kernel_step_started -> tool_policy_decision -> approval_granted ->
  tool_executed -> tool_verified -> kernel_step_completed`;
- `tool_verified(ok=True)` includes `verification.status=verified`,
  `session_attachment_found=True`, and `eligible_for_session=True`;
- replay tampering through request fingerprint mismatch is denied with no tool
  execution, no verification success, no tool message, and no memory write;
- unsupported memory tools such as `core_memory_append` and
  `core_memory_replace` are denied without execution or verification;
- unverifiable execution emits `tool_verified(ok=False)` and does not write a
  successful tool-result message.

## Verification Commands

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Result: `11 passed in 17.94s`.

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Result: `2 passed in 6.87s`.

```bash
uv run pytest -q
```

Result: `470 passed, 1 warning in 619.87s`.

```bash
uv run ruff check .
```

Result: `All checks passed!`.

## Benchmark / Case-Level Status

Milestone LongMemEval and LoCoMo full-chain LLM judge runs were not required for
this phase because the change is limited to the opt-in kernel path and does not
change default public v3 context selection, answer projection, judge behavior,
or scoring. The public benchmark smoke explicitly preserved default-off kernel
behavior and verified the opt-in trace shape.

Case-level movement for this phase:

- LongMemEval: not applicable; no benchmark-quality claim.
- LoCoMo: not applicable; no benchmark-quality claim.
- pass-to-fail: not applicable.
- fail-to-pass: not applicable.
- source-grounding movement: not applicable.

## Constraints

- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and was not enabled by default.
- No benchmark expected-answer, expected-source, or case-id fields were used for
  executable kernel tool arguments.
