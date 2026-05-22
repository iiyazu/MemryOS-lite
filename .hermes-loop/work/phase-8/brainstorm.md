# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Context Used

Confirmed: this brainstorm used `work/phase-8/context_bundle.md` as the first phase-local artifact, then used `work/phase-8/god_dispatch.json` and its read-first sources as controlling context.

Key constraints from the bundle and dispatch:

- Phase 8 is decision-only by default. Its RED condition is missing fresh 50-case full-chain promotion evidence plus stale phase-8 artifacts that do not cite this bundle.
- Promotion evals must use `MEMORYOS_MEMORY_ARCH=v3` and must not set `MEMORYOS_AGENT_KERNEL=v1`.
- `MEMORYOS_AGENT_KERNEL` currently defaults to `off`; `MEMORYOS_AGENT_KERNEL=v1` is an opt-in diagnostic/control-plane path only.
- Existing `work/phase-8/research.md` and `work/phase-8/reviews/codex-review.md` predate this bundle and must be treated as stale unless superseded by a lane output that cites this bundle.
- Phase 7 proved opt-in structured kernel traces, not answer-quality improvement; LoCoMo remains the main benchmark risk.

## Viable Approaches

### Approach A: Strict Promotion Gate First

PLAN_DRAFT writes a decision-only plan: run focused kernel-default guard, full pytest, ruff, then parallel LongMemEval/LoCoMo 50-case full-chain LLM judge with unique run ids. The execution lane then produces `promotion_decision.md` from case-level movement and source-grounding analysis before any code change.

Tradeoffs:

- Best matches the active blueprint and avoids accidental implementation without current evidence.
- Cleanly separates LongMemEval gains from LoCoMo weakness.
- Requires live LLM provider availability. If provider access fails, this route can only produce a diagnostic/blocker result, not `expand_eval` or `promote_blueprint`.

### Approach B: Evidence-Gate With Deterministic Fallback

PLAN_DRAFT uses the same strict gate, but explicitly predefines fallback behavior: if full-chain LLM answer/judge is unavailable, record the exact blocker, run only no-LLM deterministic diagnostics with unique run ids, and issue `continue_targeted` or `hold` rather than promotion.

Tradeoffs:

- More robust for autonomous execution in uncertain API environments.
- Avoids stale or empty phase completion when external judge access is missing.
- Cannot prove benchmark usability by itself; deterministic fallback is diagnostic only.

### Approach C: Targeted LoCoMo Investigation Before Promotion Gate

PLAN_DRAFT starts by analyzing known LoCoMo failure classes from Phase 6 and Phase 7, then decides whether a small test-first diagnostic fix is required before milestone eval.

Tradeoffs:

- Useful if LoCoMo failure evidence is clearly blocking and localized.
- Higher risk of turning Phase 8 into an implementation phase without fresh promotion evidence.
- Can drift into expected-answer leakage or case-id overfitting if it precedes the required 50-case same-subset comparison.

## Recommended Route

Recommend Approach B as the PLAN_DRAFT route: strict promotion gate first, with deterministic fallback explicitly marked non-promotional.

Reasoning:

- It preserves the Phase 8 decision objective while making the no-provider path safe.
- It forces fresh case-level evidence before any `expand_eval` or `promote_blueprint` recommendation.
- It prevents demo-only completion by requiring `promotion_decision.md` to cite fresh Phase 8 verification/eval outputs or record a blocker.
- It keeps the kernel off by default and avoids treating Phase 7 kernel traces as answer-quality evidence.

## What Counts As Demo-Only Or Stale Completion

Demo-only or stale completion includes:

- Advancing from plan text, old docs, stale `research.md`, or stale review artifacts without fresh Phase 8 outputs that cite `work/phase-8/context_bundle.md`.
- Claiming Phase 8 usable from no-LLM smoke diagnostics alone.
- Reporting only aggregate pass rates without fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence-hit-answer-fail, unsupported answer, and judge-questionable groups.
- Treating public `source_hit` as pure retrieval localization instead of final projection source overlap.
- Treating kernel trace presence as evidence of answer-quality improvement.
- Running promotion evals with `MEMORYOS_AGENT_KERNEL=v1`, or silently changing the default from kernel-off.
- Producing `ack.json` without both benchmarks analyzed and without explicit kernel-default/source-grounding checks.

## Specific Risks

- LoCoMo: Phase 6 still had LoCoMo `18/30` with retrieval misses and evidence-hit-answer-fail cases; Phase 7 LoCoMo kernel smoke was `0/5` and diagnostic only. Any Phase 8 promotion must keep LoCoMo separate from LongMemEval and explain residual misses case by case.
- Source grounding: `source_hit` can be true while the selected/rendered evidence or citation support is wrong. PLAN_DRAFT should require source-grounding movement from diagnostics, not just verdict movement.
- Kernel default: `src/memoryos_lite/config.py` defaults `memoryos_agent_kernel` to `off`; promotion evals must omit `MEMORYOS_AGENT_KERNEL=v1`. Kernel traces should be empty on default-off reports.
- Stale phase-8 artifacts: existing `research.md` and `reviews/codex-review.md` predate this bundle and refer to a legacy default/deprecation decision. They cannot support Phase 8 completion.
- Parallel eval run-id collisions: Phase 7 observed a collision when parallel evals shared the default timestamp run id. Phase 8 must use distinct explicit run ids such as `phase8_lme50_<timestamp>` and `phase8_locomo50_<timestamp>`.

## Concise Recommendation For PLAN_DRAFT

Draft a decision-only Phase 8 plan that:

1. Cites `work/phase-8/context_bundle.md` and the active goal verbatim.
2. Runs the focused kernel-default guard, `uv run pytest -q`, and `uv run ruff check .`.
3. Runs LongMemEval 50 and LoCoMo 50/local-cap full-chain LLM judge in parallel with `MEMORYOS_MEMORY_ARCH=v3`, unique run ids, and no `MEMORYOS_AGENT_KERNEL=v1`.
4. Compares same-case movement against available Phase 0 or prior comparison reports; if same-subset baseline is missing, state that explicitly instead of inventing movement.
5. Produces `promotion_decision.md` with one of `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`, justified by case-level evidence and source-grounding movement.
6. If LLM provider access fails, record the exact failure and run deterministic fallback only as diagnostic evidence; do not recommend `expand_eval` or `promote_blueprint`.
