# phase: phase-6

# Plan Review: Answer Projection And Citation Contract

Context source: `.hermes-loop/work/phase-6/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Verdict

PASS with two execution constraints:

- keep the implementation at the answer boundary unless a required RED test proves source wiring is impossible there;
- treat milestone eval output as diagnostic case movement, not as an improvement claim.

## Checks

- Active goal: covered. The plan targets benchmark-usable grounding, preserves case-level reporting, and explicitly avoids kernel defaulting.
- Anti-demo gate: covered. Required tests exercise the real public benchmark projected path, unretrieved citation diagnostics, and LLM answerer structured rendering. Prompt-only changes are not enough.
- v1 fallback: covered by an explicit regression command for `test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context`.
- v3 default: covered. The plan does not change config defaults or require callers to opt into v3 for normal public benchmark behavior.
- Kernel opt-in: covered. Phase 6 does not use `MEMORYOS_AGENT_KERNEL=v1` as a dependency and does not edit kernel defaults.
- LoCoMo risk: covered. The spec requires date/session metadata in structured evidence and milestone LoCoMo reporting separate from LongMemEval.
- Overfitting: covered. The plan forbids case-id rules, expected-answer leaks, dataset-specific citation hacks, and aggregate-only claims.
- Deterministic no-LLM preservation: covered. Projected answers cite selected evidence and no-evidence answers refuse without API calls.

## Gaps To Carry Into `plan_final.md`

- Make the temporal LoCoMo/date-session test explicit as a recommended additional RED/GREEN test, even though the three named tests are mandatory.
- Require report rows to expose citation fields append-only in both partial and final reports.
- Require executor to record provider-access blockers if milestone LLM eval cannot run.
