# phase: phase-1

# Plan Self Review - PASS

Verdict: PASS.

The phase-1 plan is acceptable as a contract plan for later implementation phases. It is not a Phase 3 implementation plan, does not propose code changes in Phase 1, and keeps the active goal centered on benchmark-usable, source-attributed MemoryOS Lite v3 behavior for LongMemEval and LoCoMo.

## Review Inputs

- Read order was respected: `context_bundle.md` was read before the other phase-local artifacts.
- Reviewed artifacts: `god_dispatch.json`, `research.md`, `letta_gap_matrix.md`, `brainstorm.md`, `spec.md`, and `plan.md`.
- Reviewed active blueprint/state constraints for phase binding, context-bundle use, v1 fallback, v3 default, kernel opt-in, no Letta runtime, and anti-demo gates.

## Findings

### PASS - Active Goal Binding

`brainstorm.md`, `spec.md`, and `plan.md` all bind to phase-1 and repeat the active goal. The chosen route is MemoryOS-native contract work, not a broad Letta port. The plan explicitly rejects runtime Letta dependencies, benchmark case-id hacks, prompt-only progress claims, and kernel trace-only benchmark claims.

### PASS - Anti-Demo Gate

The plan keeps Phase 1 no-code and requires future work to start from RED tests or concrete Phase 0 benchmark anchors. It preserves case-level diagnostics and rejects aggregate-only pass-rate claims. The plan also keeps `source_hit` as final projection/source overlap rather than evidence localization, which prevents retrieval success, answer support, and final projection from being conflated.

### PASS - LongMemEval And LoCoMo Separation

The plan separates benchmark pressure correctly:

- LongMemEval: `e47becba`, `118b2229`, and `51a45a95` remain evidence-hit-answer-fail anchors; `58bf7951` remains a retrieval-miss anchor.
- LoCoMo: `conv-26_qa_001` remains the evidence-hit-answer-fail anchor; `conv-26_qa_002` through `conv-26_qa_005` remain retrieval/scope anchors.

This satisfies the requirement not to hide LoCoMo retrieval/scope failures behind LongMemEval answer-projection work, and not to hide LongMemEval answer-use failures behind retrieval/source-overlap metrics.

### PASS - v1 Fallback, v3 Default, Kernel Opt-In

The plan preserves explicit `MEMORYOS_MEMORY_ARCH=v1` fallback and does not remove v1. It treats default v3 routing as a contract that must be verified through the real service/public benchmark path rather than assumed from documentation. It keeps `MEMORYOS_AGENT_KERNEL=v1` opt-in and requires `kernel_trace_events == []` by default for public eval tests.

### PASS - No Letta Runtime Dependency

The plan uses Letta semantics as reference points only: archive attachment, passage role/source auditability, selected evidence citation, component accounting, and traceable tool mutation. It does not propose importing Letta schemas, managers, services, agents, database providers, or tool executors.

### PASS - High-Priority Gap Coverage

Every P0 gap from `letta_gap_matrix.md` maps to a future RED test shape or concrete Phase 0 case anchor:

- Default v3 route and v1 fallback: `tests/test_public_benchmarks.py` default/v1 route tests.
- Archive attachment scope: two-archive synthetic composer/searcher tests plus LoCoMo retrieval-miss anchors.
- Passage source-vs-agent role: `tests/test_v3_contracts.py` role invariant and public diagnostics.
- Answer citation and unsupported behavior: public answer artifact tests anchored to LongMemEval evidence-hit-answer-fail cases and `conv-26_qa_001`.
- Rendered evidence survival: composer/public report tests for selected evidence inclusion and drops.
- Public benchmark diagnostics: taxonomy and conservative `source_hit` tests across all Phase 0 anchors.

### PASS - Phase Binding And Lane Hygiene

The plan-lane artifacts are phase-bound with `# phase: phase-1`. The plan itself does not instruct Phase 1 to edit `src/`, `tests/`, docs, benchmark data, state, blueprint, or commits. Future file maps and test names are framed as later-phase RED contracts, not current-phase implementation instructions.

## Non-Blocking Note

The existing `plan_final.md` was stale Phase 3 core-memory implementation content and must be replaced. This is not a failure of the new `brainstorm/spec/plan` chain, but leaving that stale final artifact in place would violate the phase-1 contract and no-Phase-3-plan requirement.

## Approval Conditions

The approved final contract plan must:

- start with `# phase: phase-1`;
- cite the active goal and context-bundle contract;
- remain contract-first and no-code for Phase 1;
- preserve v1 fallback, default-v3 verification, kernel opt-in, and no-Letta-runtime constraints;
- keep LongMemEval and LoCoMo case anchors separate;
- keep `source_hit` conservative;
- avoid claiming final implementation or benchmark improvement.
