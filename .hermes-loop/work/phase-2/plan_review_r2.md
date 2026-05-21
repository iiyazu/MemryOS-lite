# phase: phase-2

# Phase 2 Plan Self-Review R2

Verdict: FAIL

Reviewed artifacts:

- `.hermes-loop/work/phase-2/context_bundle.md`
- `.hermes-loop/work/phase-2/god_dispatch.json`
- `.hermes-loop/work/phase-2/brainstorm.md`
- `.hermes-loop/work/phase-2/spec.md`
- `.hermes-loop/work/phase-2/plan.md`
- prior failed `.hermes-loop/work/phase-2/plan_review.md`
- executable path checks in `src/memoryos_lite/public_benchmarks.py`, `src/memoryos_lite/cli.py`, `src/memoryos_lite/engine.py`, `src/memoryos_lite/evals.py`, `src/memoryos_lite/agent_answer_eval.py`, and `src/memoryos_lite/diagnostic_report.py`

## Blocking Findings

### High - Milestone commands do not run full-chain LLM answer/judge

References:

- `.hermes-loop/work/phase-2/context_bundle.md` lines 209, 218
- `.hermes-loop/work/phase-2/god_dispatch.json` lines 106-107
- `.hermes-loop/work/phase-2/plan.md` lines 626-646, 650-674
- `src/memoryos_lite/cli.py` lines 355-365

The context bundle and dispatch require 30-case LongMemEval and LoCoMo full-chain LLM judge runs, or an exact provider/data blocker. The revised plan labels Task 11 as "full-chain", but the primary commands omit `--llm-answer --llm-judge`. In the current CLI, both flags default to `False`, so those commands execute deterministic projected/no-LLM runs, not the required full-chain answer/judge path.

Because the fallback commands add `--no-llm-answer --no-llm-judge`, they are effectively the same mode as the current primary commands. Execute lane could run Task 11, produce reports, and still never exercise `PublicAnswerer.answer(...)` or `LLMJudge.judge(...)`, while appearing to satisfy the milestone.

Required fix:

- Change both primary milestone commands to include `--llm-answer --llm-judge`.
- Keep the deterministic fallback commands with `--no-llm-answer --no-llm-judge`.
- Add an explicit review/ACK gate that rejects milestone evidence when `answer_mode` is not `llm` or `judge_status` is `not_run` for the primary full-chain run, unless the exact provider/data blocker is recorded.
- Require Task 12 case-level analysis to report answer mode and judge status coverage per benchmark so no-LLM fallback evidence cannot be mistaken for full-chain evidence.

## Prior Blocker Recheck

### PASS - Movement status now has executable baseline input and real wiring

The revised spec and plan add a comparison-report loader, CLI `--comparison-report`, runner wiring, keyed lookup by `(benchmark, baseline, case_id)`, RED coverage for all movement statuses, and explicit handling of missing baseline rows as insufficient anti-demo evidence.

Relevant plan lines:

- `spec.md` lines 60-74, 170
- `plan.md` lines 17-20, 163-245, 487-515, 624-648, 689-694, 718-720

This fixes the prior blocker.

### PASS - RED tests now force retrieval miss vs evidence-hit answer failure

The revised plan requires a public benchmark fixture where one case retrieves/selects/renders expected evidence and must classify as `evidence_hit_answer_fail`, while a paired missing-evidence case must classify as `retrieval_miss`. It also adds separate `unsupported_answer` coverage so unsupported citation behavior cannot replace the required evidence-hit-answer-fail proof.

Relevant plan lines:

- `spec.md` lines 168-170
- `plan.md` lines 47-157, 293-307, 455-457, 711-716

This fixes the prior blocker.

### PASS - Partial and final JSON report schema parity is explicitly tested

The revised plan adds a RED test that reads both `.partial.json` and final `.json` files produced by `run_public_benchmark()` and asserts parity for `case_diagnostics` plus top-level mirror fields. The current implementation writes both paths through `result.to_report()`, so the planned test is executable against the real write path.

Relevant plan lines:

- `spec.md` lines 136-140, 171-172
- `plan.md` lines 274-291, 519-523
- `public_benchmarks.py` lines 175-179, 269-271

This fixes the prior blocker.

## Positive Checks

- All reviewed phase-local markdown starts with `# phase: phase-2`.
- The plan explicitly consumes `context_bundle.md` and keeps the Phase 2 diagnostic-only boundary.
- It preserves no retrieval ranking optimization, no answer prompt tuning, no archive/scope behavior change, no kernel tool expansion, and no case-id hacks.
- It preserves v3 default, explicit v1 fallback, v2 opt-in compatibility, and kernel opt-in as testable constraints.
- It includes RED -> GREEN -> REFACTOR -> smoke -> milestone eval -> review sequencing.
- It requires diagnostics to be wired into the real `run_public_benchmark` / public JSON path and separates LongMemEval from LoCoMo case-level analysis.

## Required Fix Before PASS

1. Update Task 11 and the ACK/review gate so the mandatory milestone commands truly run `--llm-answer --llm-judge`, and so no-LLM fallback reports cannot satisfy the full-chain milestone.

## Execute Lane Readiness

Executable by execute_lane: NO.

The plan is otherwise ready, but this blocker would allow a demo-only no-LLM milestone to pass under a "full-chain" label. Do not write `plan_final.md` until the milestone command/gate fix is made.
