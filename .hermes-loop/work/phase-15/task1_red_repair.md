# phase: phase-15

Status: DONE

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Files changed:
- `tests/test_agent_kernel.py`
- `.hermes-loop/work/phase-15/task1_red_repair.md`

Review findings addressed:
- Added durable trace assertions through `store.list_traces()` / `_trace_payloads()` for accepted selection and the non-candidate denial path.
- Tightened candidate payload assertions so generated candidates declare only `archive_write`, include `tool_call_id`, `candidate_reason`, and `constraints`, and selected IDs must match declared candidate IDs.
- Made non-candidate rejection prove the returned selector ID is absent from generated candidate IDs.
- Replaced post-construction `runner.tool_selection_boundary = ...` mutation with constructor-style `tool_selection_boundary=` dependency injection in the test factory, assuming the planned runner constructor accepts that dependency.
- Renamed the timeout-only selector test and added RED tests for malformed selector output and missing provenance fail-closed behavior.
- Added an explicit missing-`tool_call_id` approval replay denial case and kept the existing tampered-`tool_call_id` denial case.
- Updated successful and already-executed approval replay tests to carry the original pending `tool_call_id`.
- Updated mismatch replay coverage to pass the valid original `tool_call_id` while isolating session, tool, content, unknown approval, or fingerprint mismatch behavior.

Exact command run:
```bash
uv run pytest tests/test_agent_kernel.py -q
```

Exit status: 2

Failure summary:
Collection failed while importing `tests/test_agent_kernel.py`:

```text
ModuleNotFoundError: No module named 'memoryos_lite.agent_tool_selection'
```

Why RED remains expected:
Task 1 is intentionally test-only. The repaired RED tests now reference the planned K2 `ToolSelectionBoundary`, constructor injection point, selector choice contract, durable candidate/selection/denial traces, and approval replay `tool_call_id` binding before any production implementation exists. Production has not yet added `memoryos_lite.agent_tool_selection`, so collection failure remains the correct pre-production RED signal.
