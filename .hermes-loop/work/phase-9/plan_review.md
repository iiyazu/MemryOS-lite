# phase: phase-9

Active goal, quoted:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-9/context_bundle.md`.

# PLAN_SELF_REVIEW

## Review Criteria

The draft plan was reviewed against:

- active goal;
- anti-demo completion criteria;
- v1 fallback preservation;
- v3 default preservation;
- kernel opt-in preservation;
- benchmark overfitting risk;
- context bundle coverage;
- Phase 9 diagnostic-first scope.

## Findings

### Active goal

Pass. The plan keeps the goal quoted and targets benchmark-usable diagnostics rather than production-ready claims.

### Anti-demo gate

Pass with one required reinforcement. The draft requires real phase-8 rows and all 20 failed LoCoMo cases, but `plan_final.md` should explicitly require artifact generation to fail closed if any required field is missing rather than writing partial JSON.

### v1 fallback

Pass. The plan forbids changes to v1 fallback and does not route through runtime memory behavior.

### v3 default

Pass. The plan consumes existing v3 phase-8 reports and does not modify `MEMORYOS_MEMORY_ARCH` defaults.

### Kernel opt-in

Pass. The plan forbids enabling the kernel and does not use kernel execution.

### Benchmark overfitting

Pass with caution. The plan uses the 20 failed LoCoMo cases by design, but only for diagnostic replay. It must not use case-id hacks or expected-answer leaks for behavior changes. `plan_final.md` should keep classification conservative and allow `diagnostic_gap`.

### Context bundle coverage

Pass. The plan cites `.hermes-loop/work/phase-9/context_bundle.md` and uses the bundle's required cases, classes, invalid-artifact warning, smoke policy, and invariants.

### Diagnostic-first scope

Pass. The plan does not propose retrieval or answer behavior changes. It allows production diagnostic helper code only after RED tests prove the missing replay schema/path taxonomy.

## Required Revisions For Final Plan

- Add a fail-closed validation step before ACK: no `ack.json` if required fields are missing, if any failed case is absent, or if source/judge metric separation is broken.
- Make `diagnostic_gap` explicit as an acceptable honest output, not a blocker by itself.
- Require review to check no score-improvement claim is made.
- Require invalid heartbeat retry artifacts to be ignored.

These revisions are applied in `plan_final.md`.
