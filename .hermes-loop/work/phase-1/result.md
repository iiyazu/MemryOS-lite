# phase: phase-1

# Result - Phase 1 Letta Gap Matrix And Contract Decisions

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context citation: `.hermes-loop/work/phase-1/context_bundle.md` defines Phase 1 as contract and evidence planning only. This result consumes that bundle and reports contract output only.

## Real Chain Status

Phase 1 changed no runtime chain behavior. Status by chain component:

| Component | Status | Note |
|---|---|---|
| ingest | not_applicable | No ingest behavior changed. |
| store | not_applicable | No SQLite, migration, debug mirror, or persistence behavior changed. |
| retrieval | contract_decision_only | Archive scope, passage-role, and LoCoMo retrieval/scope contracts were defined for later phases. |
| context_composer | contract_decision_only | Rendered evidence survival and component-accounting contracts were defined for later phases. |
| answer_projection | contract_decision_only | Answer citation, unsupported-answer, and case-taxonomy contracts were defined for later phases. |
| kernel_loop | contract_decision_only | Kernel remains opt-in; future tool-result/source-ref trace contracts were reserved. |
| public_eval | contract_decision_only | Case-level diagnostics and conservative `source_hit` interpretation were specified for later phases. |

Executed real chain status: `contract_decision_only` for retrieval, context composer, answer projection, kernel loop, and public eval; `not_applicable` for ingest and store.

## Produced Artifacts

- `.hermes-loop/work/phase-1/context_bundle.md` - phase source of truth and active-goal context.
- `.hermes-loop/work/phase-1/god_dispatch.json` - execute/plan/research dispatch contract.
- `.hermes-loop/work/phase-1/research.md` - read-only Letta and MemoryOS observations.
- `.hermes-loop/work/phase-1/letta_gap_matrix.md` - execute-lane gap matrix and P0/P1 contract priorities.
- `.hermes-loop/work/phase-1/brainstorm.md` - split P0 route by benchmark failure mode.
- `.hermes-loop/work/phase-1/spec.md` - phase-1 contract specification.
- `.hermes-loop/work/phase-1/plan.md` - future RED/GREEN/REFACTOR contract plan.
- `.hermes-loop/work/phase-1/plan_review.md` - plan-lane self-review, PASS.
- `.hermes-loop/work/phase-1/plan_final.md` - approved final contract plan.
- `.hermes-loop/work/phase-1/result.md` - this execute result.
- `.hermes-loop/work/phase-1/execute_review.md` - execute self-review.
- `.hermes-loop/work/phase-1/control_workspace_quarantine.md` - post-review GOD_ADJUST boundary for dirty active-control files.

Stale Phase 3 result content was replaced. No fresh `ack.json` was written by this execute step. The stale tracked `ack.json` was later deleted by GOD_ADJUST because it could falsely signal completion before a passing review.

## Contract Decisions

- Keep LongMemEval and LoCoMo impacts separate:
  - LongMemEval sampled pressure remains mostly evidence-hit-answer-fail: `e47becba`, `118b2229`, `51a45a95`.
  - LongMemEval retrieval miss remains separate: `58bf7951`.
  - LoCoMo sampled pressure remains mostly retrieval/scope miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
  - LoCoMo evidence-hit-answer-fail remains separate: `conv-26_qa_001`.
- Treat Letta as a reference only. No Letta runtime dependency, import, schema inheritance, manager reuse, service reuse, database provider reuse, or agent runtime reuse is part of Phase 1.
- Preserve explicit `MEMORYOS_MEMORY_ARCH=v1` fallback.
- Verify default v3 through the real service/public benchmark path in a later phase instead of relying only on settings documentation.
- Preserve `MEMORYOS_AGENT_KERNEL=v1` as opt-in. Kernel trace presence is not answer-quality evidence.
- Keep `source_hit` conservative: final projection/source overlap, not pure evidence localization.
- Require later phases to preserve case-level taxonomy and not hide regressions behind aggregate movement.

## Verification Commands To Run

```bash
python -m json.tool .hermes-loop/work/phase-1/god_dispatch.json
test "$(sed -n '1p' .hermes-loop/work/phase-1/context_bundle.md)" = "# phase: phase-1"
test "$(sed -n '1p' .hermes-loop/work/phase-1/result.md)" = "# phase: phase-1"
test "$(sed -n '1p' .hermes-loop/work/phase-1/execute_review.md)" = "# phase: phase-1"
rg -n "source_hit|LoCoMo|LongMemEval|MEMORYOS_AGENT_KERNEL|Letta|contract|context_bundle.md" .hermes-loop/work/phase-1/result.md .hermes-loop/work/phase-1/execute_review.md
git diff -- .hermes-loop/work/phase-1/result.md .hermes-loop/work/phase-1/execute_review.md
git diff -- src tests docs benchmarks .hermes-loop/state.json
test ! -e .hermes-loop/work/phase-1/ack.json
test "$(sed -n '1p' .hermes-loop/work/phase-1/control_workspace_quarantine.md)" = "# phase: phase-1"
git status --short .hermes-loop/blueprint.md .hermes-loop/config.json .hermes-loop/god_launcher.sh .hermes-loop/god_loop_prompt.md .hermes-loop/hermes_loop.py .hermes-loop/hermes_reporter.py AGENTS.md CLAUDE.md
```

Expected result: phase-local contract files are phase-bound, active-goal and `context_bundle.md` citations are present, no stale active `ack.json` remains, and there is no code/test/docs/benchmark/state behavior change. Dirty active-control files are not assumed harmless or pre-existing; they are explicitly excluded from Phase 1 ownership by `control_workspace_quarantine.md` and remain separate workspace risk.

## Behavior Change Statement

No code behavior changed. No test behavior changed. No benchmark data or benchmark scoring behavior changed. No source files, tests, benchmark data, `.hermes-loop/state.json`, or commits were modified by this execute step.

The wider workspace has dirty active-control files. Phase 1 does not claim those files are clean, harmless, promoted, or benchmark evidence; `control_workspace_quarantine.md` records the GOD_ADJUST boundary for re-review.

Benchmark movement is not applicable for Phase 1. No usable benchmark improvement is claimed.
