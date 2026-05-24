# phase: phase-18

# Phase 18 Context Bundle

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase id: `phase-18`.
Name: Benchmark Governance And Promotion.
Target state: `governed-promotion-ready`.

Objective: execute the K5 governance decision for MemoryOS Lite v3. The phase must decide, from case-level evidence, whether to `promote_blueprint`, `expand_eval`, `continue_targeted`, or `hold`. It must not promote from same-slice repair smoke, aggregate pass rate alone, LongMemEval-only evidence, or kernel trace presence.

Target chain component: public benchmark governance across the real v3 public eval path, source-grounding diagnostics, and opt-in kernel boundary. No product behavior change is assumed at dispatch time.

## Why This Phase Exists Now

`state.json` points to `current_state = GOD_DISPATCH`, `current_phase_idx = 18`, and `execute_lane.phase = phase-18`.

Phases below 18 are either completed or explicitly superseded:

- phase-11 is superseded by narrower phase-12/phase-13 work.
- phase-17 completed with usable diagnostic repair-measurement evidence.
- phase-18 is now `in_progress`.

Phase 17 proved the repair-smoke path is measurable and safe, but it did not improve the fixed LoCoMo 10 same-slice judged pass rate or source metrics. That result makes Phase 18 a governance decision, not an automatic promotion.

## Current Hypothesis

Hypothesis: current MemoryOS Lite v3 is benchmark-usable only if Phase 18 can report LongMemEval and LoCoMo separately, preserve source-grounding diagnostics, quarantine invalid artifacts, and explain LoCoMo source-miss/judge-pass and remaining failure cases. Phase 17 evidence suggests the likely decision is `continue_targeted` unless fresh clean milestone evidence shows stable source-grounded quality without hidden regressions.

Disconfirming evidence:

- Any same-case LoCoMo pass-to-fail or source metric regression that remains unexplained.
- Aggregate judged pass improvement while `source_miss_judge_pass`, retrieval miss, or planned-evidence metrics regress.
- LongMemEval 50 materially regresses from accepted phase-8 baseline without an explicit hold decision.
- Any use of same-slice repair-smoke movement as promotion evidence.
- Any benchmark gold field, expected answer, expected source id, case-id rule, or judge label enters model-visible memory, tool payloads, archive artifacts, promotion candidates, or context composer inputs.
- Kernel becomes default or public benchmark default behavior requires `MEMORYOS_AGENT_KERNEL=v1`.

## Scope

Allowed:

- Generate phase-18 governance artifacts under `.hermes-loop/work/phase-18/`.
- Run no-LLM structural smoke only as wiring evidence.
- Run LongMemEval and LoCoMo full-chain LLM answer/judge milestone evals in parallel when a promotion or governance baseline decision needs fresh evidence.
- Compare same-case movement against accepted phase-8 50-case baselines and phase-17 r3 repair-smoke evidence.
- Classify each failing case as retrieval miss, context missing evidence, evidence-hit-answer-fail, unsupported/overconfident answer, source-miss judge-pass, or judge-questionable.
- Quarantine invalid, partial, heartbeat-only, projected, stale, or mismatched artifacts.
- Write `result.md`, `execute_review.md`, `review_verdict.json`, and `ack.json` only after aligning outcomes to the active goal.

Non-goals:

- Do not change default v3 retrieval, context composition, answer projection, or public scoring just to improve a score.
- Do not enable the v3 kernel by default.
- Do not open new kernel tools beyond the existing phase-16/17 surface.
- Do not mutate benchmark datasets or original eval reports.
- Do not claim global improvement from LongMemEval alone, LoCoMo alone, or a 10-case repair smoke.
- Do not hide source-miss judged-pass rows under generic pass counts.

## Relevant State

From `.hermes-loop/state.json` at startup:

- `current_state`: `GOD_DISPATCH`
- `current_phase_idx`: `18`
- `execute_lane.phase`: `phase-18`
- `execute_lane.state`: `GOD_DISPATCH`
- `phase-17.status`: `completed`
- `phase-18.status`: `in_progress`
- `last_updated`: `2026-05-24T03:47:56Z`

Bootstrap safety:

- `work/phase-18/context_bundle.md`, `work/phase-18/god_dispatch.json`, and `work/phase-18/plan_final.md` did not exist at startup.
- This controller pass may generate or refresh phase-local context, dispatch, and planning artifacts before any implementation, test, eval, or product-code change.

Local hygiene:

- `git status --short` showed untracked `.hermes-loop/active_job.json` and phase-17 eval logs.
- `.hermes-loop/active_job.json` names phase-18 and is orchestration state, not phase evidence.
- Phase-17 logs are runtime artifacts and must not be committed as promotion evidence unless explicitly referenced and reviewed.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md`:

- `Purpose`
- `Current Baseline And Phase 8 Evidence`
- `Hard Constraints`
- `Superpowers And Goal Discipline`
- `Completion Levels`
- `Required ACK Evidence`
- `Context Bundle Requirement`
- `Execute Goal Contract`
- `Full-Chain LLM Judge Gates`
- `Kernel And Eval Boundary`
- `Kernel Agent Graduation Blueprint`
- `Phase 17 - LoCoMo Maintenance Repair Eval`
- `Phase 18 - Benchmark Governance And Promotion`
- `Stop Conditions`
- `Expected Outcome`

Phase 18 required gates:

- no-LLM structural smoke for wiring;
- full-chain LLM answer/judge for quality;
- LongMemEval 50 full-chain LLM judge;
- LoCoMo 50 full-chain LLM judge;
- same-case comparison;
- pass-to-fail and fail-to-pass lists;
- retrieval/source metrics separate from judged answer quality;
- invalid artifact quarantine;
- reviewed phase ACK only.

## Letta Reference Files

Phase 18 is governance-first and should not port Letta internals. If a lane proposes product changes or kernel-tool changes, it must inspect the relevant Letta reference first:

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

Do not add Letta as a runtime dependency.

## Required MemoryOS Files To Read First

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/config.json`
- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/work/phase-17/ack.json`
- `.hermes-loop/work/phase-17/result.md`
- `.hermes-loop/work/phase-17/execute_review.md`
- `.hermes-loop/work/phase-17/review_verdict.json`
- `.hermes-loop/work/phase-17/reflect_phase-17.md`
- `.hermes-loop/work/phase-17/stale_index.md`
- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`
- `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json`
- `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json`
- `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo_repair_smoke_summary.json`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_repair_smoke.py`
- `src/memoryos_lite/diagnostic_report.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/config.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_kernel.py`
- `tests/test_context_composer.py`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`

## Prior Evidence

Accepted phase-8 milestone baseline:

- LongMemEval 50 full-chain LLM judge: `47/50`.
- LoCoMo 50 full-chain LLM judge: `30/50`.
- Valid reports:
  - `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
  - `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`
- Invalid for promotion:
  - `phase8_lme50_hb_20260522T160637Z`
  - `phase8_locomo50_hb_20260522T160637Z`
  because they were killed/partial/projected/no-judge.

Accepted phase-10 milestone:

- LongMemEval 30 full-chain: `29 pass / 1 fail`; no pass-to-fail.
- LoCoMo 30 full-chain: `20 pass / 10 fail`; `fail_to_pass=conv-26_qa_011,conv-26_qa_012`; no pass-to-fail; remaining `retrieval_miss=6`; remaining `evidence_hit_answer_fail=4`.

Phase-17 r3 repair-smoke evidence:

- Baseline LoCoMo 10 full-chain: `8 pass / 2 fail`, `judge_done=10/10`.
- Opt-in kernel repair smoke LoCoMo 10 full-chain: `8 pass / 2 fail`, `judge_done=10/10`.
- `fail_to_pass=[]`
- `pass_to_fail=[]`
- `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`
- `retrieval_miss=["conv-26_qa_008"]`
- `evidence_hit_answer_fail=["conv-26_qa_006"]`
- `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`
- source metric movement: no improvements and no regressions.
- `full_chain_gate_status="not_satisfied"`.
- Same-slice repair smoke is diagnostic only and not promotion evidence.

## Known Pass-To-Fail Risks

- Source-miss judged-pass rows can make judged pass rate look strong while source localization remains weak.
- Repair-smoke archive writes are measurable but not effective on the fixed LoCoMo 10 r3 slice.
- Answer projection can fail even when evidence is retrieved, especially `conv-26_qa_006`.
- Retrieval/query/source ranking can still miss, especially `conv-26_qa_008`.
- LongMemEval may remain strong while LoCoMo remains unexplained; this cannot be called chain-level improvement.
- Provider/API instability can create partial or projected runs that are invalid for promotion.
- Full-project `mypy src` has known unrelated pre-existing type errors; targeted mypy may be used when code changes are scoped.

## Failing Or Watch Cases

Start governance analysis from:

- `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`: judged pass with source miss in Phase 17 r3.
- `conv-26_qa_006`: unchanged evidence-hit-answer-fail in Phase 17 r3.
- `conv-26_qa_008`: unchanged retrieval miss in Phase 17 r3.

Do not hard-code case ids in product behavior. These ids are allowed only in diagnostic reports, phase-local plans, and eval analysis.

## Expected Verification Commands

Bootstrap/planning must not run tests or evals until `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` exist.

Baseline checks if code changes:

```bash
uv run pytest -q
uv run ruff check .
```

No-LLM structural smoke if governance needs fresh wiring evidence:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 5 \
  --run-id phase18_lme5_structural \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --run-id phase18_locomo5_structural \
  --no-llm-answer \
  --no-llm-judge
```

Milestone governance evals must run LongMemEval and LoCoMo in parallel when required:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 50 \
  --run-id phase18_lme50_<timestamp>
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 50 \
  --run-id phase18_locomo50_<timestamp>
```

Do not add `MEMORYOS_AGENT_KERNEL=v1` unless explicitly testing the opt-in kernel path. Phase 18 promotion governance should normally evaluate default kernel-off v3 behavior.

For every long-running public eval, write and refresh `work/phase-18/eval_heartbeat*.json` at least every two minutes while running. Judge completion must be verified from final report rows, not process existence alone.

## Anti-Demo Completion Criteria

Phase 18 can ACK only if:

- `result.md`, `execute_review.md`, `review_verdict.json`, and `ack.json` cite this context bundle and the active goal.
- Any fresh milestone report is full-chain LLM answer/judge, not projected/no-LLM.
- LongMemEval and LoCoMo are reported separately.
- Same-case fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence-hit-answer-fail, source-miss judge-pass, context-missing-evidence, unsupported answer, and judge-questionable rows are listed.
- Invalid or stale artifacts are quarantined and not used as promotion evidence.
- The decision is one of `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`, with case-level evidence.
- `ack_level` is `usable`; plan-only, demo-only, and partial results cannot advance.

## Constraint Checks

- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and is not used for default promotion evidence.
- SQLite remains the authoritative store.
- Public benchmark gold fields remain eval-only sidecars.
- No new daemon, scheduler, or orchestration rewrite is allowed.
