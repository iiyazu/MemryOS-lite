# phase: phase-1

# Reflection - Phase 1

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Blueprint Adjustment Decision

The blueprint does not need adjustment after Phase 1.

Phase 1 produced the intended Letta-to-MemoryOS contract map and converted the comparison into benchmark-tied contracts without runtime changes, Letta dependency, source/test/doc/benchmark edits, or default kernel enablement. The existing blueprint already contains the right next gate: Phase 2 evidence harness and failure taxonomy before Phase 4 retrieval/scope work or Phase 6 answer projection work.

The main correction is not a blueprint rewrite. It is dispatch discipline: Phase 2 must consume the Phase 1 contract priorities and must not treat Phase 1 ACK wording as proof that retrieval, context composer, answer projection, kernel loop, or public eval behavior improved. Phase 1 is contract-complete, not implementation-complete.

## Phase Ordering

No phase reorder is recommended.

Do not move Phase 4 or Phase 6 ahead of Phase 2 yet:

- LongMemEval currently shows mostly evidence-hit-answer-fail pressure, especially `e47becba`, `118b2229`, and `51a45a95`, but Phase 2 still needs to prove where selected evidence is lost or ignored.
- LoCoMo currently shows mostly retrieval/scope miss pressure, especially `conv-26_qa_002` through `conv-26_qa_005`, but Phase 2 still needs stable case taxonomy and evidence IDs before archive scope changes can be judged.
- `conv-26_qa_001` remains the LoCoMo evidence-hit-answer-fail bridge case and should be carried as an answer-contract anchor, not mixed into the retrieval-miss bucket.

No phase split is required yet. Phase 2 can remain one phase if its dispatch is narrowed to diagnostics, taxonomy, and report contracts rather than optimization.

## Phase 2 Dispatch Priorities

Phase 2 should prioritize, in order:

1. Prove the default real public benchmark path emits v3 diagnostics without requiring `MEMORYOS_MEMORY_ARCH=v3`, while preserving explicit `MEMORYOS_MEMORY_ARCH=v1` fallback.
2. Add or harden case-level taxonomy so retrieval miss, evidence-hit-answer-fail, unsupported answer, supported cited answer, pass-to-fail, and fail-to-pass remain visible per case.
3. Treat `source_hit` conservatively as final projection/source overlap, not pure evidence localization. Keep it separate from retrieved evidence IDs, selected context IDs, rendered evidence IDs, citation support, and answer correctness.
4. Emit retrieved evidence IDs, selected context IDs, rendered answer-context evidence IDs, projected answer evidence/citation IDs, judge status, and kernel trace events in a backward-compatible public report shape.
5. Run LongMemEval and LoCoMo milestone evidence separately. If full-chain LLM judge access is unavailable, record that blocker and do deterministic smoke only as fallback evidence, without claiming the mandatory milestone gate is satisfied.
6. Preserve `MEMORYOS_AGENT_KERNEL=v1` as opt-in. Kernel trace presence should remain an audit signal, not answer-quality evidence.

Phase 2 should not implement archive retrieval optimization, answer prompt tuning, core-memory mutation expansion, or kernel tool expansion unless a missing diagnostic blocks the taxonomy itself.

## LongMemEval And LoCoMo Handling

LongMemEval should be reported around the sampled split:

- stable pass: `1e043500`;
- retrieval miss: `58bf7951`;
- evidence-hit-answer-fail: `e47becba`, `118b2229`, `51a45a95`.

LoCoMo should be reported separately:

- evidence-hit-answer-fail: `conv-26_qa_001`;
- retrieval/scope misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

Do not promote LongMemEval movement if LoCoMo remains unexplained. Do not claim LoCoMo retrieval improvement from answer-side changes. Do not allow aggregate score movement to hide case-level regressions.

## Control Workspace Quarantine

The dirty active-control quarantine remains important. `.hermes-loop/blueprint.md`, launcher/config/reporter files, `AGENTS.md`, and `CLAUDE.md` are outside Phase 1 ownership and must not be used as Phase 1 implementation, benchmark, ACK, or blueprint-amendment evidence.

Phase 2 dispatch should explicitly restate this boundary or require God to resolve it before any commit/promotion decision. The quarantine is acceptable for continuing phase-local work, but it is still a workspace risk for integration.

recommendation: no_adjustment
