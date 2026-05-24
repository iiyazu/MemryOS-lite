# phase: phase-17

Task 8 repair: rewrite source identifiers before final forbidden-value scan.

Triggering evidence:
- First full-chain repair-smoke eval `phase17_locomo10_kernel_repair_smoke` denied all 10 LoCoMo repair proposals.
- Inspection showed safe model-visible source ids inside proposal arguments were scanned before alias rewriting, so raw case/source ids caused `forbidden gold or benchmark value in executable payload` before they could become repair-store aliases.

RED:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_rewrites_argument_source_ids_before_forbidden_value_scan -q`
- Result: failed with `ExecutableRepairProposal(... denial_reason='forbidden gold or benchmark value in executable payload')`.

GREEN:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_rewrites_argument_source_ids_before_forbidden_value_scan tests/test_public_benchmarks.py::test_repair_smoke_denies_gold_fields_in_executable_tool_request -q`
- Result: `2 passed in 0.05s`.
- Command: focused repair-smoke test group covering sanitizer, opt-in, isolation, visibility, comparison summary, and gate labeling.
- Result: `10 passed in 15.79s`.

Post-fix LoCoMo evidence:
- Baseline run: `phase17_locomo10_baseline`, full-chain LLM answer/judge, `6 pass / 4 fail`.
- Repair-smoke run: `phase17_locomo10_kernel_repair_smoke_r2`, full-chain LLM answer/judge, `6 pass / 4 fail`.
- Kernel tool execution: 4 rows executed `archive_write`; 4 verified archive artifacts were session-attached and eligible.
- Movement: `fail_to_pass=[]`, `pass_to_fail=[]`, `unchanged_fail=["conv-26_qa_003","conv-26_qa_004","conv-26_qa_006","conv-26_qa_008"]`, `unchanged_pass=["conv-26_qa_001","conv-26_qa_002","conv-26_qa_005","conv-26_qa_007","conv-26_qa_009","conv-26_qa_010"]`.
- Source metric movement: no improvements and no regressions for `source_hit`, `planned_evidence_source_hit_at_5`, or `episode_source_hit_at_10`.
- Full-chain gate status remains `not_satisfied` because same-slice repair smoke is diagnostic only.
