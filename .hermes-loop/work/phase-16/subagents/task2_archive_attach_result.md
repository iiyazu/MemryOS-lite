# phase: phase-16

# Task 3/4 Archive Attach Result

Context bundle path used: `.hermes-loop/work/phase-16/context_bundle.md`

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope

Implemented only Phase 16 TDD Task 3 and Task 4:

- RED tests for `archive_attach` approval-bound execution, durable `ArchiveAttachment`, `tool_verified`, and v3 archival visibility.
- RED test for `archive_attach` replay tampering denied before `tool_executed`.
- GREEN named archive maintenance service and routing from `SimpleToolExecutionManager`.
- Preserved `archive_write` behavior through the same named archive service.

No core promotion persistence, Alembic migrations, policy changes in `engine.py`, public eval changes, result/ACK artifacts, or benchmark-target work were implemented.

## RED

Command:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3 tests/test_agent_kernel.py::test_kernel_archive_attach_replay_tamper_denies_before_execution -q
```

Observed failure summary:

- `test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3` failed because `archive_attach` reached `tool_executed` but emitted no `tool_verified`; execution still returned unsupported/no verification behavior.
- `test_kernel_archive_attach_replay_tamper_denies_before_execution` passed before implementation because the existing approval replay binding already denied tampered arguments before execution.
- Failure matched missing archive attach execution/service/verification behavior, not a syntax or test setup error.

## GREEN

Commands:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3 tests/test_agent_kernel.py::test_kernel_archive_attach_replay_tamper_denies_before_execution tests/test_agent_kernel.py::test_kernel_replays_persisted_approval_after_cold_boundary_once tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Observed summary: `4 passed`.

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Observed summary: `42 passed`.

```bash
uv run ruff check src/memoryos_lite/agent_kernel_tools.py src/memoryos_lite/agent_kernel.py tests/test_agent_kernel.py
```

Observed summary: `All checks passed!`.

## Files Changed

- `src/memoryos_lite/agent_kernel_tools.py`
- `src/memoryos_lite/agent_kernel.py`
- `tests/test_agent_kernel.py`
- `.hermes-loop/work/phase-16/subagents/task2_archive_attach_result.md`

## Concerns Or Blockers

- No blockers for this scoped task.
- `archive_attach` is intentionally limited to current session scope.
- `core_promotion_request` remains selection-only from Task 1/2 and was not implemented here.
- Existing dirty/untracked phase-local files and `.hermes-loop/state.json` were present in the worktree; this task did not modify `.hermes-loop/state.json`.

Benchmark scores were not used as targets.

Status: DONE
