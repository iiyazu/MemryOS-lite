# phase: phase-15

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Files changed:
- `tests/test_public_benchmarks.py`
- `.hermes-loop/work/phase-15/task6_red_result.md`

Command:
`uv run pytest tests/test_public_benchmarks.py -q`

Command output summary:
- Pytest exited with code 2 during collection.
- Error: `ModuleNotFoundError: No module named 'memoryos_lite.public_maintenance_planner'`.
- Short summary: `ERROR tests/test_public_benchmarks.py`; `1 error in 0.49s`.

RED reason:
The Task 6 tests intentionally import `EvalGoldSidecar`, `ModelVisiblePlannerInput`, and `build_maintenance_artifact` from the planned `memoryos_lite.public_maintenance_planner` boundary. That production module does not exist yet, so the focused public benchmark test file fails during collection before any implementation changes.
