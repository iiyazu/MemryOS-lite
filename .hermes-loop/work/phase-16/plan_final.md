# phase: phase-16

# Phase 16 Final Plan

Context bundle: `work/phase-16/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

PLAN_SELF_REVIEW result: `work/phase-16/plan_review.md` verdict `PASS`.

God decision: promote `work/phase-16/spec.md` and `work/phase-16/plan.md` to final execution guidance with the binding overrides below. These overrides narrow risk and supersede any conflicting wording in `plan.md`.

## Required Read Order For Execute Lane

1. `work/phase-16/context_bundle.md`
2. `work/phase-16/god_dispatch.json`
3. `work/phase-16/spec.md`
4. `work/phase-16/brainstorm.md`
5. `work/phase-16/plan_review.md`
6. `work/phase-16/plan.md`
7. This `work/phase-16/plan_final.md`

If any artifact has a different first-line phase binding, treat it as stale and enter `GOD_ADJUST` rather than implementing.

## Final Scope

Implement Level 1 tools only:

- `archive_write`
- `archive_attach`
- `core_promotion_request`

Keep closed:

- `core_memory_append`
- `core_memory_replace`
- destructive archive/core tools
- `recall_search`
- `archive_search`
- any unknown tool

Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default. Do not change v3 default or v1 fallback. Do not add Letta as a runtime dependency.

## Binding Review Overrides

1. Tool result message bodies must stay generic.

   Use `tool <tool_name> executed` as the message body. Put `memory_id`, `attachment_id`, `candidate_id`, result payloads, approval ids, tool call ids, and verification details in metadata only. This supersedes the `result_id` body sketch in `plan.md`.

2. Add explicit `core_promotion_request` replay-tamper coverage before production implementation.

   The execute lane must add a RED test that creates a pending approval for `core_promotion_request`, resumes with tampered content, label, source refs, `tool_call_id`, or requested action, and proves `approval_replay_denied` occurs before `tool_executed`, before candidate persistence, and before any core memory mutation.

3. Public benchmark evidence is structural only.

   `archive_attach` and `core_promotion_request` ACK evidence must come from focused kernel/store/context tests. The opt-in public smoke may remain `archive_write`-only and must not be described as LoCoMo or LongMemEval quality improvement.

## TDD Execution Tasks

Execute `work/phase-16/plan.md` tasks in order:

1. RED registry/fail-closed selection/policy tests.
2. GREEN registry and selection boundary.
3. RED archive maintenance service and v3 visibility tests.
4. GREEN archive maintenance service.
5. RED durable core promotion request tests, including the replay-tamper override above.
6. GREEN promotion candidate store, Alembic migration, lifecycle persistence, and tool execution.
7. Policy integration and public benchmark guards.
8. Focused suites, full verification, default-off guard, opt-in structural smoke, `result.md`, and `execute_review.md`.

Do not collapse RED/GREEN steps. Production code changes are not allowed until the corresponding focused RED test has been observed and recorded in phase-local execution artifacts.

## Required Verification Commands

Focused tests:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_service.py tests/test_archival_store.py tests/test_context_composer.py -q
uv run pytest tests/test_public_benchmarks.py -q
```

Baseline checks:

```bash
uv run pytest -q
uv run ruff check .
```

Default-off guard:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase16_locomo5_kernel_default_off_guard
```

Opt-in structural smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase16_locomo5_kernel_tools_structural
```

These smoke runs require heartbeat files if they become long-running. They are not milestone promotion evidence.

## Anti-Demo ACK Bar

Phase 16 may ACK only at `ack_level = "usable"` if every opened tool is wired through the real opt-in `SimpleAgentStepRunner.run_step()` path with registry, selection, policy, approval or source-provenance gating, service-backed execution, durable verification, trace evidence, focused tests, and case-level structural smoke evidence where applicable.

Reject ACK if:

- a tool exists only in constants/docs;
- `archive_attach` lacks a real `ArchiveAttachment` row or v3 eligibility evidence;
- `core_promotion_request` is in-memory only or applies core memory;
- replay tampering reaches execution or verification;
- public reports emit kernel events without `MEMORYOS_AGENT_KERNEL=v1`;
- result language claims benchmark-quality improvement from Phase 16.
