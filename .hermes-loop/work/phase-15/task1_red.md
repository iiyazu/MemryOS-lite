# phase: phase-15

Status: DONE

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Files changed:
- `tests/test_agent_kernel.py`
- `.hermes-loop/work/phase-15/task1_red.md`

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

Why this is the expected RED signal:
The new focused tests define the Phase 15 K2 kernel selection boundary, including candidate trace ordering before policy, fail-closed denial for non-candidate selector output, selector failure fallback without mutation, selected request provenance through approval replay, and replay denial for a tampered `tool_call_id`. Production does not yet provide the planned `memoryos_lite.agent_tool_selection.ToolSelectionBoundary` helper or the related K2 contracts/traces, so the focused test command fails before production changes as intended.
