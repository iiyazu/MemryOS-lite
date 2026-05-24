# phase: phase-17

# Phase 17 Reflection

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Diagnostic Completion

Phase 17 completed the active goal slice as usable diagnostic repair-measurement evidence, not as benchmark-quality promotion evidence.

The phase reached the required real-path standard:

- LoCoMo repair smoke runs through the public v3 benchmark path.
- Kernel maintenance writes require explicit `MEMORYOS_AGENT_KERNEL=v1`.
- Approved repair writes execute through `SimpleAgentStepRunner.run_step()` and the Phase 16 tool surface.
- Repair artifacts are persisted in an isolated eval store and verified as session-attached eligible archive artifacts.
- Default v3 behavior, explicit v1 fallback, and kernel-default-off behavior remain preserved.
- Same-slice movement, failure classes, source-metric movement, and baseline coverage are reported case-by-case.
- Review FAIL items were repaired before ACK: source-miss judge-pass rows are visible, baseline mismatch blocks the gate, and context-selection/rendering diagnostic classes are retained.

The evidence is usable because it answers the K4 question negatively or narrowly: the current maintenance-write path can be measured safely, but it did not improve LoCoMo 10 r3 judged pass rate or source metrics.

The r3 full-chain LoCoMo evidence:

- baseline: `8 pass / 2 fail`, `judge_done=10/10`;
- repair smoke: `8 pass / 2 fail`, `judge_done=10/10`;
- `fail_to_pass=[]`;
- `pass_to_fail=[]`;
- `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`;
- `retrieval_miss=["conv-26_qa_008"]`;
- `evidence_hit_answer_fail=["conv-26_qa_006"]`;
- `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`;
- source metric improvements and regressions were both empty.

Gate interpretation remains correct: `full_chain_gate_status="not_satisfied"` and same-slice repair smoke is diagnostic only.

## r3 LoCoMo Lesson

The next hypothesis should not be "archive_write maintenance artifacts alone will repair LoCoMo." Phase 17 showed that even when four repair artifacts were executed and verified as attached, the fixed-slice source metrics did not move.

Case-level implications:

- `conv-26_qa_006` is still evidence-hit-answer-fail, so the next bottleneck is likely answer projection, citation use, or evidence-to-answer reasoning rather than retrieval availability alone.
- `conv-26_qa_008` is still retrieval miss, so at least one remaining failure needs retrieval/query/source ranking repair before answer work can help.
- `conv-26_qa_002` through `conv-26_qa_005` passed the judge while missing source localization, proving that judged pass rate can hide source-grounding defects. Future governance must keep `source_miss_judge_pass` as a first-class row class, not a secondary note.
- Denied repair rows were useful evidence too: five were denied for forbidden gold or benchmark values in executable payloads, and one for an unknown or unopened kernel tool. The sanitizer is doing necessary work and should remain strict.

The most plausible next targeted hypothesis is split:

1. For source-miss judged-pass rows, improve evidence selection/rendering/citation accounting so answers that pass also expose the correct source grounding.
2. For `conv-26_qa_006`, inspect answer projection and citation behavior over already retrieved evidence.
3. For `conv-26_qa_008`, inspect retrieval/query expansion or episode/archive source ranking.

This is a narrower hypothesis than "run more maintenance writes." Phase 18 should treat Phase 17 as diagnostic evidence that maintenance artifacts are measurable and safe, but not yet effective.

## Blueprint Decision

No root `blueprint.md` amendment is required before Phase 18.

Reason: the existing Phase 18 scope already covers the correct next control decision:

- report LongMemEval and LoCoMo separately;
- split judged pass movement from source-grounded movement;
- block graduation on source-grounding regressions or leakage;
- require held-out or clean-store evidence before any improvement claim;
- allow `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`.

The important Phase 18 constraint is execution discipline, not a blueprint rewrite. Because Phase 17 produced no useful same-slice source movement, Phase 18 should not assume promotion readiness. It should start from the r3 evidence and decide whether to `continue_targeted` on the source-grounding bottlenecks above, `hold`, or run broader milestone evals only if the controller explicitly needs a governance baseline.

Minimum verification if Phase 18 chooses targeted continuation:

- preserve a fixed case matrix including `conv-26_qa_006`, `conv-26_qa_008`, and the four `source_miss_judge_pass` rows;
- require full-chain LLM answer/judge for any quality claim;
- report judged pass, source-hit, planned evidence hit, episode hit, and source-miss judge-pass separately;
- run clean-store or held-out validation before any improvement claim;
- keep `MEMORYOS_AGENT_KERNEL=v1` opt-in only.

Minimum verification if Phase 18 chooses larger governance eval:

- LongMemEval and LoCoMo reported separately;
- same-case pass-to-fail and fail-to-pass lists;
- source metric movement separated from judged answer movement;
- no promotion from same-slice repair smoke;
- invalid, stale, partial, or heartbeat-only artifacts quarantined.

## Residual Risks

- Same-slice overfitting remains medium risk. Phase 17 did not show positive same-slice movement, but future rules or artifacts could still overfit if the same LoCoMo slice becomes the optimization target.
- `source_miss_judge_pass` is now visible but not solved. These rows are a key governance risk because aggregate judge pass can look healthy while source localization is not benchmark-usable.
- The repair-smoke path is safe but not yet effective. Verified archive artifacts did not change r3 source metrics, so the next phase should avoid treating execution success as memory-quality success.
- `conv-26_qa_006` and `conv-26_qa_008` remain useful hard cases for separating answer-projection failure from retrieval failure.
- LongMemEval was not rerun in Phase 17. That is acceptable for the explicit LoCoMo repair-smoke scope, but Phase 18 promotion or governance expansion must not omit LongMemEval if it makes milestone claims.
- Full-project `mypy src` remains blocked by unrelated pre-existing errors; the new repair-smoke module passed targeted mypy only.
- HEAD `4aa404b feat: add locomo repair smoke harness` includes the previously noted `public_repair_smoke.py` implementation in the commit stat, so the earlier untracked-source risk is resolved at HEAD.
- Local hygiene still needs controller attention: `git status --short` shows modified `.hermes-loop/state.json`, untracked `.hermes-loop/active_job.json`, and untracked phase-17 eval logs. The active job file reportedly names phase-16, so stale orchestration state must not be used as phase-18 truth.
