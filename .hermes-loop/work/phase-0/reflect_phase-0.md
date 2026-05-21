# phase: phase-0

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase-0 Evidence Summary

Phase 0 reached a usable baseline-freeze level for deterministic smoke diagnostics, not a benchmark-improvement milestone.

Evidence reviewed:

- `.hermes-loop/work/phase-0/context_bundle.md` defines Phase 0 as a no-code baseline freeze and diagnostic harness.
- `.hermes-loop/work/phase-0/baseline_case_matrix.md` records stable case IDs, separates LongMemEval from LoCoMo, and classifies each 5-case smoke row.
- `.hermes-loop/work/phase-0/result.md`, `execute_review.md`, `review_verdict.json`, and `ack.json` record passing focused tests, full pytest, ruff, v3 diagnostics, v1 fallback, v3 default, and kernel opt-in boundaries.
- Default LongMemEval and LoCoMo reports have no kernel trace events; the one-case kernel smoke has traces only under explicit `MEMORYOS_AGENT_KERNEL=v1`.
- No Phase 0 behavior optimization is claimed, and no full-chain 30-case LLM judge milestone is claimed.

Case-level baseline:

- LongMemEval 5-case no-LLM smoke: `1/5` projected. Three failures are classified as `evidence_hit_answer_fail` (`e47becba`, `118b2229`, `51a45a95`), one as `retrieval_miss` (`58bf7951`), and one as `pass` (`1e043500`).
- LoCoMo 5-case no-LLM smoke: `0/5` projected. One failure is classified as `evidence_hit_answer_fail` (`conv-26_qa_001`), and four are classified as `retrieval_miss` (`conv-26_qa_002` through `conv-26_qa_005`).
- Opt-in kernel LoCoMo 1-case smoke remains projected fail for `conv-26_qa_001`; this is trace-presence evidence, not answer-quality evidence.

## Reflection

The baseline matrix changes the emphasis for Phase 1, but it does not require changing the blueprint before Phase 1 starts.

The key taxonomy signal is split by benchmark:

- LongMemEval's visible 5-case weakness is mostly at the evidence-to-answer boundary, because several cases recovered planned/source evidence but still missed expected facts.
- LoCoMo's visible 5-case weakness is mostly retrieval or evidence discovery, because most sampled cases did not recover expected evidence through episode/planned paths.

This split argues against advancing directly to answer projection work and also against treating retrieval as the only bottleneck. Phase 1's current purpose, "Letta Gap Matrix And Contract Decisions", is still the correct next step because it forces MemoryOS-specific contracts before implementation. The phase should consume the Phase 0 matrix and rank Letta gaps by benchmark impact:

- For LoCoMo, archive/passage scope, passage eligibility, temporal/session evidence, and retrieval diagnosability should be high-priority contract candidates.
- For LongMemEval, selected evidence survival, answer citation, unsupported-answer behavior, and answer projection contracts should be high-priority contract candidates.
- Core memory blocks and kernel trace contracts should remain in the matrix, but the Phase 0 smoke does not justify making them the first behavior-changing implementation target.

The existing blueprint already supports this. Phase 1 requires `letta_gap_matrix.md` with MemoryOS current behavior, Letta reference behavior, gap, benchmark impact, priority, and proposed contract. Phase 2 then owns deeper evidence taxonomy and mandatory full-chain LLM judge diagnostics, with later dynamic adjustment rules deciding whether retrieval/scope phases or answer-projection phases move earlier. Phase 0's 5-case deterministic smoke is enough to guide priorities, but too small and too no-LLM to justify phase reordering by itself.

## Recommendation

recommendation: no_adjustment

No active blueprint amendment is required before Phase 1.

Phase 1 dispatch should explicitly carry forward the Phase 0 case taxonomy as priority input. It should not rewrite the blueprint, skip the Letta gap matrix, enable the v3 kernel by default, or claim benchmark progress from the frozen smoke baseline.
