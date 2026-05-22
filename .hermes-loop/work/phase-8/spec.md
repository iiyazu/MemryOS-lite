# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Controlling Context

`work/phase-8/context_bundle.md` is the controlling context for Phase 8. This spec also follows `work/phase-8/brainstorm.md` and `work/phase-8/god_dispatch.json`, but any conflict is resolved in favor of `work/phase-8/context_bundle.md`.

Existing Phase 8 `research.md` and `reviews/codex-review.md` are stale for this objective unless superseded by a fresh lane output that cites `work/phase-8/context_bundle.md`.

## Phase Objective

Phase 8 is the promotion gate and next-blueprint decision for the active Letta-style benchmark-usability loop. It must decide, from fresh Phase 8 evidence, whether MemoryOS Lite v3 should `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`.

The decision must be based on benchmark-usable evidence for LongMemEval and LoCoMo, not on demo completion, old artifacts, aggregate-only scores, or opt-in kernel trace presence.

## Scope

In scope:

- Refresh Phase 8 plan/spec artifacts from `work/phase-8/context_bundle.md`.
- Verify default behavior with a focused kernel-default guard.
- Run full tests and lint before interpreting benchmark evidence.
- Run fresh LongMemEval and LoCoMo milestone evals with `MEMORYOS_MEMORY_ARCH=v3`, unique run ids, and no `MEMORYOS_AGENT_KERNEL=v1`.
- Analyze both benchmarks case by case: pass, fail, fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence hit but context missing, evidence hit but answer fail, unsupported answer, judge questionable, and source-grounding movement.
- Produce `work/phase-8/promotion_decision.md` with one of the approved decision options.
- Produce execution, review, verdict, and ACK artifacts only when their evidence contract is satisfied.

Out of scope:

- Enabling the v3 kernel by default.
- Running promotion evals through `MEMORYOS_AGENT_KERNEL=v1`.
- Treating Phase 7 opt-in kernel traces as answer-quality evidence.
- Rewriting `.hermes-loop` infrastructure.
- Using benchmark case-id hacks, expected-answer leaks, or per-case prompt shortcuts.
- Claiming MemoryOS Lite is production ready.
- Editing source code, tests, active docs, or `.hermes-loop/state.json` for this PLAN_DRAFT task.

## Decision Options

`continue_targeted`: choose when fresh evidence exposes a specific remaining bottleneck that should become the next blueprint target.

`expand_eval`: choose only when 50-case or local-cap evidence is stable across LongMemEval and LoCoMo, pass-to-fail cases are explicit, and source grounding does not regress silently.

`hold`: choose when aggregate pass rate moves but evidence quality, source grounding, judge stability, or LoCoMo behavior regresses or remains unexplained.

`promote_blueprint`: choose when the active blueprint/state should be amended for the next loop, with the amendment justified by fresh case-level evidence.

## Evidence Contract

Fresh Phase 8 evidence must include:

- Focused guard output proving v3 remains default and the kernel remains opt-in.
- Full `uv run pytest -q` output.
- Full `uv run ruff check .` output.
- LongMemEval milestone eval output with a unique Phase 8 run id.
- LoCoMo milestone eval output with a different unique Phase 8 run id.
- Report paths and log paths for every verification and eval command.
- Same-subset case movement against Phase 0 or the best available prior comparable baseline; if a comparable baseline is missing, the artifact must say so explicitly.
- Separate retrieval/source metrics from judged answer quality.
- No promotion recommendation from aggregate score alone.

If full-chain LLM answer or judge access is unavailable, record the exact failure and optionally run no-LLM deterministic diagnostics as fallback evidence. That fallback is non-promotional and can support only `continue_targeted` or `hold`.

## Source-Grounding Requirements

Phase 8 must not treat public `source_hit` as pure evidence localization unless the metric is explicitly derived from planned or retrieved evidence. The decision must distinguish:

- final answer pass/fail;
- retrieved/planned evidence source overlap;
- selected/rendered context source overlap;
- answer support and unsupported answer cases;
- evidence-hit-answer-fail cases;
- source-grounding regressions even when pass rate improves.

Source-grounding movement must be summarized for both LongMemEval and LoCoMo. Any pass-to-fail or newly unsupported answer case blocks `expand_eval` until explained.

## LoCoMo-Specific Requirements

LoCoMo must be analyzed independently from LongMemEval. Phase 8 cannot let LongMemEval improvement hide LoCoMo weakness.

The LoCoMo report must call out:

- local case cap if fewer than 50 cases are available;
- retrieval misses;
- evidence hit but context missing;
- evidence hit but answer fail;
- unsupported answers;
- judge-questionable cases;
- pass-to-fail and unchanged-fail cases;
- whether failures cluster around conversation, temporal, speaker, or multi-hop memory behavior.

If LoCoMo remains weak or opaque, the valid decision is `continue_targeted` or `hold`, not `expand_eval`.

## Implementation Boundary

Phase 8 is decision-only unless a focused RED test proves a diagnostic implementation fix is needed.

No production code edits are allowed unless all of the following are true:

- fresh evidence identifies a concrete diagnostic defect that blocks a valid Phase 8 decision;
- a focused failing test is added first;
- the failing command and failure text are recorded in `work/phase-8/result.md`;
- the fix is minimal and preserves v1 fallback, v3 default composer behavior, and kernel opt-in behavior.

For this PLAN_DRAFT task, do not edit source code, tests, active docs, or `.hermes-loop/state.json`.

## Acceptance Criteria

Usable ACK requires:

- `work/phase-8/context_bundle.md` cited in plan, result, review, verdict, ACK, and promotion decision artifacts.
- The active goal cited verbatim in every Phase 8 completion artifact.
- Focused guard, full pytest, and ruff outputs recorded with log paths.
- LongMemEval and LoCoMo milestone evals completed, or an exact LLM/provider blocker recorded.
- Case-level analysis for both benchmarks includes fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence-hit-answer-fail, unsupported answer, judge-questionable, and source-grounding movement.
- Kernel default remains off; promotion evals do not set `MEMORYOS_AGENT_KERNEL=v1`.
- `promotion_decision.md` selects exactly one approved decision and justifies it from fresh evidence.
- `review_verdict.json` validates that the ACK is not demo-only and not aggregate-only.

Non-promotional fallback acceptance requires:

- exact blocker recorded with command, run id, log path, and timestamp;
- optional deterministic no-LLM diagnostics clearly labeled non-promotional;
- `promotion_decision.md` selects `continue_targeted` or `hold`;
- no `ack.json` claims usable promotion unless both benchmark evidence and review gate are satisfied.
