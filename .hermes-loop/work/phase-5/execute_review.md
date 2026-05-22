# phase: phase-5

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context source: `.hermes-loop/work/phase-5/context_bundle.md`.

# Execute Self Review

## What Real Chain Changed

- Real v3 `MemoryOSService.build_context()` emits component accounting and final-context trace metadata through `ContextPackage.metadata` and `context_built` trace payloads.
- `V3ContextComposer` records included and budget-dropped component rows for task/core/recall/archival/recent with source refs, flattened source ids, estimated tokens, inclusion/drop flags, reason codes, and rendered indexes.
- Recall neighbor handling keeps same-`benchmark_session_id` LoCoMo neighbors and rejects cross-session neighbors when both direct hit and neighbor expose benchmark-session metadata.
- Recall budget-drop diagnostics preserve source refs plus neighbor/session metadata.
- Public benchmark outputs expose v3 component accounting fields append-only.
- Public case diagnostics consume `final_context_trace`, nested `source_refs`, component drop counts, and LoCoMo neighbor diagnostics.
- Dropped v3 diagnostics are no longer counted as selected context evidence.

## What Is Still Demo-Only Or Partial

- No remaining demo-only Phase 5 wiring is known: the fields are in the real v3 build-context and public benchmark path.
- The benchmark behavior is still not answer-grounded. Both 30-case full-chain runs report `answer_support_status=unsupported_answer` on all rows.
- Phase 5 does not claim benchmark improvement. LongMemEval stayed 18/30 and LoCoMo stayed 7/30 against the Phase 2 full-chain comparison reports.
- Phase 6 must handle the answer projection/citation contract before any promotion decision.

## Tests Proving Behavior

- Dropped-diagnostic regression: `1 passed in 0.05s`.
- Focused Phase 5 behavior tests: `9 passed in 10.24s`.
- Phase 4 guard tests: `4 passed in 3.95s`.
- Full suite: `388 passed, 1 warning in 549.00s (0:09:09)`.
- Ruff: `All checks passed!`.

## Benchmark Cases Moved Or Regressed

LongMemEval report: `.memoryos/evals/phase5_repeat_20260522_1315_lme_30_longmemeval.json`.

- 18 pass / 12 fail.
- Movement: 18 unchanged pass, 12 unchanged fail, no fail-to-pass, no pass-to-fail, no missing baseline rows.
- Failure classes: retrieval miss 3, context missing evidence 12, unsupported answer 15.
- v3 accounting fields are present on all 30 rows.

LoCoMo report: `.memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json`.

- 7 pass / 23 fail.
- Movement: 7 unchanged pass, 23 unchanged fail, no fail-to-pass, no pass-to-fail, no missing baseline rows.
- Failure classes: retrieval miss 11, context missing evidence 10, unsupported answer 9.
- v3 accounting fields are present on all 30 rows.

## v1/v3/kernel Constraints

- v3 remains the default memory architecture.
- `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback and focused tests prove it does not receive v3 component accounting.
- `MEMORYOS_AGENT_KERNEL` remains opt-in/default-off and focused tests prove public benchmark kernel trace remains default-off.
- No kernel default was changed.

## ACK Recommendation

Recommend usable ACK for Phase 5 only as a context-accounting and diagnostic-path phase. Do not advance to Phase 8 or claim benchmark improvement. Advance to Phase 6 because answer projection/citation is the next bottleneck shown by full-chain evidence.
