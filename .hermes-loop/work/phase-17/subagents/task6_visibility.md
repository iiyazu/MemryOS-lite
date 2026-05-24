# phase: phase-17

# Task 6: V3 Visibility And Lifecycle Boundaries

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `work/phase-17/context_bundle.md`.

## RED

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_archive_artifacts_are_visible_only_when_session_attached -q
```

Result:

```text
FAILED tests/test_public_benchmarks.py::test_repair_smoke_archive_artifacts_are_visible_only_when_session_attached
KeyError: 'archive_artifacts'
1 failed in 3.67s
```

The failure showed that the public repair-smoke report did not expose sanitized archive artifact metadata, so the test could not prove that the v3 context saw the repair archive only through the session attachment created by the kernel write.

## GREEN

Command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_archive_artifacts_are_visible_only_when_session_attached -q
```

Result:

```text
1 passed in 3.24s
```

Required regression command:

```bash
uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q
```

Result:

```text
22 passed in 12.31s
```

## Files Changed

- `tests/test_public_benchmarks.py`
  - Added `test_repair_smoke_archive_artifacts_are_visible_only_when_session_attached`.
  - The test runs the explicit opt-in repair-smoke public v3 path, then a separate default run.
  - It asserts the repair artifact is visible to v3 through `eligible_archive_ids` and `selected_passage_ids` only in the attached repair session.
  - It asserts the separate default run has disabled repair smoke and does not see the repair archive or passage.
- `src/memoryos_lite/public_repair_smoke.py`
  - Added `archive_artifacts_from_kernel_trace()` to derive sanitized archive metadata from kernel `tool_verified` events.
  - The exported metadata is limited to `archive_id`, `passage_id`, verification status, and session eligibility booleans.
- `src/memoryos_lite/public_benchmarks.py`
  - Added `archive_artifacts` to repair-smoke reports and disabled repair-smoke defaults.

## Core Promotion Boundary

`core_promotion_request` rendering coverage was skipped for this Task 6 slice because the current public repair-smoke path exercised here only emits and verifies `archive_write`. No core rendering behavior was added.

## Self-Review

- `MEMORYOS_AGENT_KERNEL` remains default-off.
- `MEMORYOS_MEMORY_ARCH=v1` fallback and default v3 behavior were not changed.
- Repair artifact visibility is proven through the real public v3 path and kernel-created archive/session eligibility, not direct context injection.
- Repair-smoke metadata does not include raw benchmark source ids, expected answers, expected source ids, judge labels, failure classes, movement labels, or case ids.
- No benchmark fixtures, eval output reports, ACK files, blueprint, or state files were intentionally edited.
