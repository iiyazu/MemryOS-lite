# phase: phase-16

/goal Implement Phase 16 as a bounded K3 kernel maintenance tool surface for MemoryOS Lite v3, aligned with the active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `work/phase-16/context_bundle.md`.
Final plan: `work/phase-16/plan_final.md`.

## Real Path This Phase May Change

- Opt-in kernel path only: `MEMORYOS_AGENT_KERNEL=v1` with `SimpleAgentStepRunner.run_step()`.
- Tool selection, policy, approval replay, execution, verification, and trace emission for Level 1 tools:
  - `archive_write`
  - `archive_attach`
  - `core_promotion_request`
- SQLite-backed store and Alembic migration only where needed for durable pending promotion candidates.
- Named service boundaries for archive maintenance and lifecycle promotion requests.
- v3 context visibility checks for archive attachment eligibility and non-visibility of pending core promotions.
- Public benchmark structural reporting only to verify kernel default-off and opt-in trace shape.

## Required Artifacts

- `work/phase-16/result.md`
- `work/phase-16/execute_review.md`
- Focused RED/GREEN test evidence before production changes.
- Verification command outputs summarized in result artifacts.
- Case-level structural smoke evidence for default-off and opt-in kernel behavior if public eval is run.

## Explicit Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change the default `v3` memory architecture.
- Do not remove or weaken `MEMORYOS_MEMORY_ARCH=v1`.
- Do not add Letta as a runtime dependency.
- Do not open `core_memory_append`, `core_memory_replace`, destructive archive/core tools, `recall_search`, `archive_search`, or unknown tools.
- Do not use benchmark case ids, expected answers, expected source ids, judge labels, failure classes, or gold-derived sidecars as executable tool inputs.
- Do not claim LongMemEval or LoCoMo quality improvement from Phase 16.
- Do not write demo-only registry constants without real selection, policy, service, verification, trace, and tests.

Max repair cycles: 2.

Benchmark scores are diagnostic evidence only, not goal constraints. If a benchmark or smoke regresses, classify the failure and choose `repair`, `repeat_phase`, `god_adjust`, or `hold`; do not keep optimizing for score improvement.
