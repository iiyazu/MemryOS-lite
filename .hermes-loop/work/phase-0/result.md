# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Sources

- `.hermes-loop/work/phase-0/context_bundle.md`
- `.hermes-loop/work/phase-0/plan_final.md`
- `.hermes-loop/work/phase-0/spec.md`
- `.hermes-loop/work/phase-0/god_dispatch.json`

## Commands

| command | status | output |
|---|---:|---|
| `uv run pytest tests/test_agent_kernel.py tests/test_public_benchmarks.py tests/test_context_composer.py tests/test_evals.py -q` | pass | `61 passed in 368.61s` |
| `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 5 --run-id phase0_v3_lme_5case --no-llm-answer --no-llm-judge` | pass | report written |
| `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --run-id phase0_v3_locomo_5case --no-llm-answer --no-llm-judge` | pass | report written |
| `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 1 --run-id phase0_v3_kernel_locomo_1case --no-llm-answer --no-llm-judge` | pass | report written |
| `uv run pytest -q` | pass | `355 passed, 1 warning in 482.85s` |
| `uv run ruff check .` | pass | `All checks passed!` |

## Reports Inspected

- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`
- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json`
- `.hermes-loop/work/phase-0/baseline_case_matrix.md`

## Baseline Result

- LongMemEval no-LLM 5-case projected smoke: 1 pass, 4 fail.
- LoCoMo no-LLM 5-case projected smoke: 0 pass, 5 fail.
- LoCoMo opt-in kernel no-LLM 1-case projected smoke: 0 pass, 1 fail.
- LongMemEval and LoCoMo failures remain separated in `baseline_case_matrix.md`.
- `source_hit` is not treated as pure evidence localization; rows use `episode_source_hit_at_10`, `planned_evidence_source_hit_at_5`, source overlap, and projected answer status.

## Default Checks

- v3 default: `Settings()` resolved `memory_arch= v3`.
- v1 fallback: `Settings(memoryos_memory_arch="v1")` resolved `memory_arch= v1`, and focused v1 fallback tests passed.
- kernel default: `Settings()` resolved `agent_kernel= off`; default phase0 reports have `kernel_trace_events=[]`.
- kernel opt-in: `Settings(memoryos_agent_kernel="v1")` resolved `agent_kernel= v1`; `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json` has the expected kernel trace sequence.
- v3 diagnostics: all successful report rows expose `memory_arch`, `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events`.

## Write Boundary

Phase execution wrote only the allowed Phase 0 artifacts and generated eval reports:

- `.hermes-loop/work/phase-0/baseline_case_matrix.md`
- `.hermes-loop/work/phase-0/result.md`
- `.hermes-loop/work/phase-0/execute_review.md`
- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`
- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json`

No `src/`, `tests/`, `docs/`, review verdict, ACK file, or behavior optimization was modified by execution.

Pre-existing dirty governance files were explicitly observed before ACK review:

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`

Those files were already dirty before Phase 0 EXECUTE and are not counted as Phase 0 execution writes. This result does not claim a clean worktree for active state or active blueprint inputs.

## Decision

`advance`

ACK should be considered at usable Phase 0 level because the no-code baseline freeze is complete, diagnostics are present, required commands passed, and the matrix exposes case-level LongMemEval and LoCoMo regressions separately. This is not a full-chain LLM judge milestone claim because optional 30-case LLM judge runs were not executed.
