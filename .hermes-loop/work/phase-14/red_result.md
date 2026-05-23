# phase: phase-14

# RED Result: Task 1

Scope: RED tests only. No production files under `src/` were edited.

Files changed:

- `tests/test_agent_kernel.py`
- `tests/test_public_benchmarks.py`
- `.hermes-loop/work/phase-14/red_result.md`

Commands run:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Result: expected RED failure.

- `test_kernel_replays_persisted_approval_after_cold_boundary_once` fails because the resumed approved `archive_write` trace has no `tool_verified` event after `tool_executed`.
- `test_kernel_rejects_replay_without_original_request_binding` fails because replay with the same `approval_id` and action is granted even when the stored pending approval carries unmatched future request-binding metadata.
- `test_kernel_emits_negative_verification_when_execution_is_not_store_visible` fails because an execution-only result emits `tool_executed` but no durable negative `tool_verified` event.
- Summary observed: `3 failed, 8 passed`.

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Result: expected RED failure.

- `test_public_benchmark_kernel_trace_remains_default_off` passes, preserving default-off behavior.
- `test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled` fails because the opt-in kernel trace shape still ends after `tool_executed` and lacks `tool_verified`.
- Summary observed: `1 failed, 1 passed`.

Expected GREEN target:

- approved `archive_write` emits durable `tool_verified(ok=True)` with store/context eligibility verification;
- replay approval is bound to original request identity or fingerprint, not only a globally searched `approval_id`;
- execution that cannot be verified through store/session eligibility emits durable `tool_verified(ok=False)`;
- unsupported memory tools still produce no `tool_executed`, no `tool_verified`, no tool message, and no memory write.
