# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Sources

- `.hermes-loop/work/phase-0/context_bundle.md`
- `.hermes-loop/work/phase-0/plan_final.md`
- `.hermes-loop/work/phase-0/spec.md`
- `.hermes-loop/work/phase-0/god_dispatch.json`
- `benchmarks/longmemeval/longmemeval.json`
- `benchmarks/locomo/locomo10.json`
- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`
- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json`

## Run Summary

| command | status | report path | cases | notes |
|---|---:|---|---:|---|
| `uv run pytest tests/test_agent_kernel.py tests/test_public_benchmarks.py tests/test_context_composer.py tests/test_evals.py -q` | pass | n/a | n/a | `61 passed in 368.61s` |
| `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 5 --run-id phase0_v3_lme_5case --no-llm-answer --no-llm-judge` | pass | `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json` | 5 | projected no-LLM report |
| `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --run-id phase0_v3_locomo_5case --no-llm-answer --no-llm-judge` | pass | `.memoryos/evals/phase0_v3_locomo_5case_locomo.json` | 5 | projected no-LLM report |
| `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 1 --run-id phase0_v3_kernel_locomo_1case --no-llm-answer --no-llm-judge` | pass | `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json` | 1 | explicit opt-in kernel trace report |
| `uv run pytest -q` | pass | n/a | n/a | `355 passed, 1 warning in 482.85s` |
| `uv run ruff check .` | pass | n/a | n/a | `All checks passed!` |

## Default And Opt-In Checks

| check | evidence | status |
|---|---|---|
| v3 default | `Settings()` prints `memory_arch= v3`; docs and tests expect v3 default. | pass |
| v1 fallback | `Settings(memoryos_memory_arch="v1")` prints `memory_arch= v1`; focused tests covering v1 fallback passed. | pass |
| kernel default off | `Settings()` prints `agent_kernel= off`; default public reports have `kernel_trace_events=[]`. | pass |
| kernel opt-in | `Settings(memoryos_agent_kernel="v1")` prints `agent_kernel= v1`; opt-in report has the expected 9 trace events. | pass |
| v3 diagnostics | all refreshed report rows have `memory_arch`, `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events`. | pass |

## Prior RED Evidence

This remains visible as prior evidence from `.hermes-loop/work/phase-0/context_bundle.md` and `.hermes-loop/work/phase-0/god_dispatch.json`, not as a replacement for refreshed rows:

- LongMemEval evidence-hit answer fails: `e47becba`, `118b2229`, `51a45a95`.
- LongMemEval retrieval miss: `58bf7951`.
- LongMemEval pass: `1e043500`.
- LoCoMo evidence-hit answer fail: `conv-26_qa_001`.
- LoCoMo retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

## LongMemEval Cases

| benchmark | run_id | report_path | case_id | result | taxonomy | retrieval_evidence | context_evidence | answer_status | v3_diagnostics | kernel_trace | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| longmemeval | `phase0_v3_lme_5case` | `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json` | `e47becba` | fail/projected | `evidence_hit_answer_fail` | `episode_source_hit_at_10=true`, `planned_evidence_source_hit_at_5=true`; missing source ids remain in final projection | v3 context present; source evidence reached planned path | `expected_missing=["Business Administration"]` | present | `absent_by_default` | Evidence was found before projection, but projected answer failed. |
| longmemeval | `phase0_v3_lme_5case` | `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json` | `118b2229` | fail/projected | `evidence_hit_answer_fail` | `episode_source_hit_at_10=true`, `planned_evidence_source_hit_at_5=true`; final `source_hit=false` | v3 context present; source evidence reached planned path | `expected_missing=["45 minutes each way"]` | present | `absent_by_default` | Evidence was found, but answer projection missed the expected fact. |
| longmemeval | `phase0_v3_lme_5case` | `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json` | `51a45a95` | fail/projected | `evidence_hit_answer_fail` | `episode_source_hit_at_10=true`, `planned_evidence_source_hit_at_5=true`, `source_hit=true` | v3 context present; `source_overlap_ids` non-empty | `expected_missing=["Target"]` | present | `absent_by_default` | Source overlap exists, so final failure is not treated as retrieval localization. |
| longmemeval | `phase0_v3_lme_5case` | `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json` | `58bf7951` | fail/projected | `retrieval_miss` | `episode_source_hit_at_10=false`, `planned_evidence_source_hit_at_5=false`, `source_hit=false` | v3 context present, but expected source absent from evidence path | `expected_missing=["The Glass Menagerie"]` | present | `absent_by_default` | Required source was not recovered in episode/planned evidence. |
| longmemeval | `phase0_v3_lme_5case` | `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json` | `1e043500` | pass/projected | `pass` | `episode_source_hit_at_10=true`, `planned_evidence_source_hit_at_5=true`, `source_hit=true` | v3 context present; `source_overlap_ids` non-empty | `expected_present=["Summer Vibes"]` | present | `absent_by_default` | Stable passing baseline case. |

## LoCoMo Cases

| benchmark | run_id | report_path | case_id | result | taxonomy | retrieval_evidence | context_evidence | answer_status | v3_diagnostics | kernel_trace | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| locomo | `phase0_v3_locomo_5case` | `.memoryos/evals/phase0_v3_locomo_5case_locomo.json` | `conv-26_qa_001` | fail/projected | `evidence_hit_answer_fail` | `episode_source_hit_at_10=true`, `planned_evidence_source_hit_at_5=true`, `source_hit=true` | v3 context present; `source_overlap_ids` non-empty | `expected_missing=["7 May 2023"]` | present | `absent_by_default` | Evidence and source overlap exist, but projected answer failed. |
| locomo | `phase0_v3_locomo_5case` | `.memoryos/evals/phase0_v3_locomo_5case_locomo.json` | `conv-26_qa_002` | fail/projected | `retrieval_miss` | `episode_source_hit_at_10=false`, `planned_evidence_source_hit_at_5=false`, `source_hit=false` | v3 context present, but expected source absent from evidence path | `expected_missing=["2022"]` | present | `absent_by_default` | Expected source not recovered. |
| locomo | `phase0_v3_locomo_5case` | `.memoryos/evals/phase0_v3_locomo_5case_locomo.json` | `conv-26_qa_003` | fail/projected | `retrieval_miss` | `episode_source_hit_at_10=false`, `planned_evidence_source_hit_at_5=false`, `source_hit=false` | v3 context present, but expected sources absent from evidence path | `expected_missing=["Psychology, counseling certification"]` | present | `absent_by_default` | Expected sources not recovered. |
| locomo | `phase0_v3_locomo_5case` | `.memoryos/evals/phase0_v3_locomo_5case_locomo.json` | `conv-26_qa_004` | fail/projected | `retrieval_miss` | `episode_source_hit_at_10=false`, `planned_evidence_source_hit_at_5=false`, `source_hit=false` | v3 context present, but expected source absent from evidence path | `expected_missing=["Adoption agencies"]` | present | `absent_by_default` | Expected source not recovered. |
| locomo | `phase0_v3_locomo_5case` | `.memoryos/evals/phase0_v3_locomo_5case_locomo.json` | `conv-26_qa_005` | fail/projected | `retrieval_miss` | `episode_source_hit_at_10=false`, `planned_evidence_source_hit_at_5=false`, `source_hit=false` | v3 context present, but expected source absent from evidence path | `expected_missing=["Transgender woman"]` | present | `absent_by_default` | Expected source not recovered. |

## Opt-In Kernel Smoke

| benchmark | run_id | report_path | case_id | result | taxonomy | retrieval_evidence | context_evidence | answer_status | v3_diagnostics | kernel_trace | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| locomo | `phase0_v3_kernel_locomo_1case` | `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json` | `conv-26_qa_001` | fail/projected | `evidence_hit_answer_fail` | `episode_source_hit_at_10=true`, `planned_evidence_source_hit_at_5=true`, `source_hit=true` | v3 context present; `source_overlap_ids` non-empty | `expected_missing=["7 May 2023"]` | present | `present_opt_in` | Trace sequence: `kernel_step_started`, `tool_policy_decision`, `approval_pending`, `kernel_step_completed`, `kernel_step_started`, `tool_policy_decision`, `approval_granted`, `tool_executed`, `kernel_step_completed`. |

## Diagnostic Gaps

- No required v3 diagnostic gap found in refreshed successful reports.
- No default-kernel trace found in the non-kernel LongMemEval or LoCoMo reports.
- Successful eval commands also wrote same-size `.partial.json` intermediates; these were removed after confirming the final `.json` reports exist, keeping the Phase 0 artifact set to successful reports only.
- No 30-case full-chain LLM judge was run; Phase 0 therefore freezes deterministic smoke diagnostics only and does not claim full-chain milestone completion.

## Decision

`advance`

Phase 0 has a usable no-code baseline freeze: focused tests, full tests, and ruff pass; LongMemEval and LoCoMo are separated; every smoke case has a stable case ID and taxonomy; v3 diagnostics are present; default kernel traces are absent; explicit opt-in kernel traces are present.
