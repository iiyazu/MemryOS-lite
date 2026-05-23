# phase: phase-11

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

RED commands:

- `uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_splits_selected_and_render_handoff_drops -q`
  - Exit status: 1
  - Failure summary: expected RED. `KeyError: 'evidence_handoff'` when asserting selected-drop handoff boundary, proving public diagnostics do not yet expose the handoff ledger.
- `uv run pytest tests/test_public_benchmarks.py::test_public_result_reports_answer_evidence_handoff_metadata -q`
  - Exit status: 1
  - Failure summary: expected RED after fixing the fixture to match the current `EvalCase` contract. `_to_public_result() got an unexpected keyword argument 'answer_evidence'`, proving the public result path does not yet accept/report answer-evidence handoff metadata.
- `uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs -q`
  - Exit status: 1
  - Failure summary: expected RED after the milestone report exposed baseline `pass` plus current `error` being labeled `unchanged_fail`. The assertion `movement_status("pass", "error") == "pass_to_fail"` failed with `unchanged_fail`, proving the movement field could hide a pass-to-error regression.
