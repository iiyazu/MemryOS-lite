# phase: phase-5

# Final Plan: Context Composer And Accounting

## Verdict

Use the plan in `.hermes-loop/work/phase-5/plan.md`.

The self-review in `.hermes-loop/work/phase-5/plan_review.md` passes. No GOD_ADJUST is required.

Primary context source: `.hermes-loop/work/phase-5/context_bundle.md`.

## Execution Summary

Implement the narrow Phase 5 path:

1. Add RED tests for v3 component accounting, final-context trace source ids, budget drops, LoCoMo same-session neighbors, v1 exclusion, kernel default-off, and public report exposure.
2. Add metadata builders in `src/memoryos_lite/context_composer.py`.
3. Carry LoCoMo neighbor metadata through `src/memoryos_lite/retrieval/episode_searcher.py` and `src/memoryos_lite/retrieval/recall_pipeline.py`.
4. Propagate v3 metadata through `src/memoryos_lite/engine.py`, `src/memoryos_lite/evals.py`, and `src/memoryos_lite/public_benchmarks.py`.
5. Teach `src/memoryos_lite/public_case_diagnostics.py` to flatten nested `source_refs` and use `final_context_trace`.
6. Run focused smoke, full `pytest`, `ruff`, and required LongMemEval/LoCoMo milestone evals if public benchmark behavior changes.

## Non-negotiable Gates

- Do not enable `MEMORYOS_AGENT_KERNEL` by default.
- Do not remove or weaken `MEMORYOS_MEMORY_ARCH=v1`.
- Do not use benchmark case-id rules or expected-answer leaks.
- Do not claim benchmark improvement from small slices.
- Do not hide LoCoMo behind LongMemEval.
- Preserve current public benchmark fields and add new fields append-only.
