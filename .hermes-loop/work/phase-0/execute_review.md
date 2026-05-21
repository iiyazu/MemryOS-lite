# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Sources

- `.hermes-loop/work/phase-0/context_bundle.md`
- `.hermes-loop/work/phase-0/plan_final.md`
- `.hermes-loop/work/phase-0/spec.md`
- `.hermes-loop/work/phase-0/god_dispatch.json`
- `.hermes-loop/work/phase-0/baseline_case_matrix.md`
- `.hermes-loop/work/phase-0/result.md`

## Usable ACK Checklist

| check | review |
|---|---|
| Baseline matrix exists and cites active goal/context bundle | pass |
| LongMemEval and LoCoMo separated | pass |
| Stable case IDs recorded | pass |
| Every case has one `spec.md` taxonomy value | pass |
| Focused tests pass | pass, `61 passed in 368.61s` |
| Full pytest passes before ACK | pass, `355 passed, 1 warning in 482.85s` |
| Ruff passes before ACK | pass, `All checks passed!` |
| Report fields include `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events` | pass |
| v1 fallback, v3 default, and kernel opt-in constraints verified | pass |
| No behavior optimization claimed | pass |

## Review Findings

- LoCoMo failures are not hidden by LongMemEval results: LoCoMo has its own table with `conv-26_qa_001` through `conv-26_qa_005`, including four `retrieval_miss` rows and one `evidence_hit_answer_fail` row.
- `source_hit` is not conflated with evidence localization: the matrix records `episode_source_hit_at_10`, `planned_evidence_source_hit_at_5`, `source_overlap_ids`, and projected answer status separately.
- No benchmark leakage or expected-answer shortcut was introduced: no production, test, docs, benchmark data, prompt, or scoring code was changed.
- `.hermes-loop/state.json` and `.hermes-loop/blueprint.md` were already dirty before Phase 0 EXECUTE and were not modified by execution; this review does not claim a clean worktree for active state or active blueprint inputs.
- Kernel traces are absent by default: refreshed LongMemEval and LoCoMo v3 reports have empty `kernel_trace_events`.
- Kernel traces are present only under explicit `MEMORYOS_AGENT_KERNEL=v1`: the opt-in LoCoMo one-case report has the expected 9-event trace sequence.
- The refreshed reports expose v3 diagnostics for every row, so the missing-diagnostics stop condition did not trigger.
- Successful eval commands produced final `.json` reports; same-size `.partial.json` intermediates were removed so they are not mistaken for failed-run artifacts.

## Non-ACK Boundaries

- This review does not claim retrieval improvement, context composer improvement, answer prompt improvement, or kernel behavior improvement.
- This review does not claim full-chain LLM judge milestone completion; the optional 30-case LLM judge gate was not run.
- This review does not promote the v3 kernel default.

## Final Review Decision

`approve_ack`

ACK may be considered for Phase 0 usable baseline freeze only. The evidence supports advancing from no-code baseline freeze to the next phase, while preserving case-level failures and kernel opt-in boundaries.
