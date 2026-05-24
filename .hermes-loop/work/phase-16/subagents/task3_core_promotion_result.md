# phase: phase-16

# Task 5/6 Durable Core Promotion Request Result

Context bundle path used: `.hermes-loop/work/phase-16/context_bundle.md`

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope

Implemented only Phase 16 Task 5/6 durable `core_promotion_request`:

- RED tests for durable `MemoryLifecycleService.create_candidate()` persistence.
- RED kernel test proving approval-bound `core_promotion_request` persists a pending candidate, emits `tool_executed` and `tool_verified`, writes a generic tool message with `candidate_id` metadata, and does not mutate or render core memory.
- RED replay-tamper test covering content, label, source refs, `tool_call_id`, and requested action tampering before execution, candidate persistence, or core mutation.
- GREEN SQLite-backed `PromotionCandidate` persistence, Alembic migration `0008_add_promotion_candidates`, lifecycle persistence, named `PromotionMaintenanceService`, and kernel execution/verification routing.

No search tools were implemented. `core_memory_append` and `core_memory_replace` were not opened. Kernel default behavior was not changed.

## RED

Command:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_lifecycle_create_candidate_persists_pending_candidate tests/test_agent_kernel.py::test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation tests/test_agent_kernel.py::test_kernel_core_promotion_request_replay_tamper_denies_before_execution_or_candidate -q
```

Observed failure summary:

- `test_lifecycle_create_candidate_persists_pending_candidate` failed with `AttributeError: 'MemoryStore' object has no attribute 'get_promotion_candidate'`.
- `test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation` failed because `core_promotion_request` reached `tool_executed` but emitted no `tool_verified`.
- `test_kernel_core_promotion_request_replay_tamper_denies_before_execution_or_candidate` failed with `AttributeError: 'MemoryStore' object has no attribute 'list_promotion_candidates'` after replay denial checks.

The failures matched missing durable promotion persistence and routing, not syntax or fixture setup errors.

## GREEN

Focused command:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_lifecycle_create_candidate_persists_pending_candidate tests/test_agent_kernel.py::test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation tests/test_agent_kernel.py::test_kernel_core_promotion_request_replay_tamper_denies_before_execution_or_candidate -q
```

Observed summary: `3 passed`.

Affected suite command:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_memory_lifecycle.py -q
```

Observed summary: `53 passed`.

Requested lint command:

```bash
uv run ruff check src/memoryos_lite/store.py src/memoryos_lite/memory_lifecycle.py src/memoryos_lite/agent_kernel_tools.py src/memoryos_lite/agent_kernel.py tests/test_agent_kernel.py tests/test_memory_lifecycle.py alembic/versions/0008_add_promotion_candidates.py
```

Observed summary: `All checks passed!`.

Additional changed-file lint:

```bash
uv run ruff check src/memoryos_lite/v3_contracts.py
```

Observed summary: `All checks passed!`.

## Files Changed

- `src/memoryos_lite/store.py`
- `src/memoryos_lite/memory_lifecycle.py`
- `src/memoryos_lite/agent_kernel_tools.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/v3_contracts.py`
- `tests/test_memory_lifecycle.py`
- `tests/test_agent_kernel.py`
- `alembic/versions/0008_add_promotion_candidates.py`
- `.hermes-loop/work/phase-16/subagents/task3_core_promotion_result.md`

## Concerns Or Blockers

- No blockers for this scoped task.
- Existing dirty/untracked phase-local files and `.hermes-loop/state.json` were present before this subtask; this task did not intentionally modify `.hermes-loop/state.json`.
- Full repository tests, full lint, public smoke, and phase ACK artifacts remain outside this Task 5/6 subtask.

Benchmark scores were not used as targets.

Status: DONE
