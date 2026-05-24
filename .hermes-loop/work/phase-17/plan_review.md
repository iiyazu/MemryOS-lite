# phase: phase-17

# Phase 17 Plan Self-Review

Review status: PASS

Context cited: `work/phase-17/context_bundle.md`.

Active goal quoted from `work/phase-17/context_bundle.md`:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Review Scope

Reviewed the revised `work/phase-17/spec.md` and `work/phase-17/plan.md` against the active goal, anti-demo gate, explicit `MEMORYOS_MEMORY_ARCH=v1` fallback, default `v3` architecture, opt-in `MEMORYOS_AGENT_KERNEL=v1`, benchmark leakage rules, Review Eval Autonomy Policy, and phase bootstrap safety from `work/phase-17/context_bundle.md`.

Also rechecked the current CLI contract in `src/memoryos_lite/cli.py`: `eval public` still defaults `llm_answer=False` and `llm_judge=False`, so full-chain public eval commands require explicit `--llm-answer` and `--llm-judge`.

## PASS Rationale

1. Full-chain public eval commands are now explicit under the current CLI.

   The revised spec states that the current CLI defaults `llm_answer` and `llm_judge` to `False`, and every full-chain gate command must explicitly pass `--llm-answer` and `--llm-judge`. The LoCoMo baseline, opt-in LoCoMo repair-smoke rerun, and conditional LongMemEval regression guard commands in `work/phase-17/spec.md` all include both flags.

   The revised plan also includes both flags in Task 12, Task 13, Task 14, and the final full-chain verification command set. No spec/plan full-chain public eval command remains in projected/no-LLM form.

2. The positive real-path repair-smoke test no longer requires execution from leaked executable content.

   The Task 3 positive test still uses a synthetic baseline row, but its `maintenance_proposal.arguments.content` is `Alice records a model-visible context note.`, not the sidecar expected answer `repair marker`. The test asserts the serialized repair-smoke execution report does not contain `repair marker`, does not contain the unaliased benchmark source id `sample_repair_qa_001:sample_repair:D1:1`, and does contain a repair-store-local alias such as `repair_msg_`.

   This now aligns with the plan's sanitizer requirements: source ids may originate in model-visible context, but the executable `ToolExecutionRequest` must use aliased repair-store ids and must not carry expected answers, expected source ids, judge labels, failure classes, movement labels, or case ids.

3. Anti-demo and real-path requirements are preserved.

   The plan requires approved Phase 16 Level 1 tools through `SimpleAgentStepRunner.run_step()`, rejects direct fixture/store writes as success evidence, routes the hook after public ingestion/page and before `service.build_context(...)`, and requires v3 consumption through archive/session eligibility or approved lifecycle visibility.

4. Default behavior boundaries are intact.

   The plan keeps repair smoke disabled unless an explicit baseline report is supplied, requires `settings.resolved_agent_kernel == "v1"` for repair-smoke execution, preserves default public v3 behavior, includes explicit v1 fallback regression checks, and rejects default kernel behavior changes.

5. Benchmark leakage and same-slice overfitting boundaries are explicit.

   The plan adds denial tests for gold fields, requires alias rewriting for benchmark-labeled source ids, separates source metric movement from judged answer movement, reports pass-to-fail and fail-to-pass case lists, and labels same-slice repair-smoke movement as diagnostic only.

6. Review Eval Autonomy Policy is satisfied for planning.

   No projected/no-LLM report is allowed to satisfy a quality gate. Missing provider handling records `blocked_provider_unavailable` and forbids quality or promotion claims. The plan also keeps LongMemEval as a regression guard if default v3/non-kernel behavior changes and notes parallel execution when it is required alongside LoCoMo milestone evidence.

7. Phase bootstrap safety is respected.

   This review made no source, test, eval output, state, ACK, or blueprint edits. The only permitted writes are this `work/phase-17/plan_review.md` and the promoted `work/phase-17/plan_final.md`.

## Non-Blocking Clarifications Added To Final Plan

- `work/phase-17/plan_final.md` treats the reviewed spec/plan command blocks as authoritative for execution. Any stale no-LLM-shaped command examples in dispatch metadata are not execution instructions.
- The Task 3 positive real-path test is structural/no-LLM wiring coverage only because it calls `run_public_benchmark(..., llm_answer=False, llm_judge=False)`. It must not be used as quality evidence.
- The repair-smoke runner must execute only the sanitized, aliased `ToolExecutionRequest`; raw baseline report source ids and eval sidecar fields remain report/validation inputs only.

## Decision

Promote `work/phase-17/plan.md` to `work/phase-17/plan_final.md` with the non-blocking clarifications above. Execution may proceed in a later bootstrap that sees `context_bundle.md`, `god_dispatch.json`, and `plan_final.md` already present and promotes the phase to `EXECUTE`.
