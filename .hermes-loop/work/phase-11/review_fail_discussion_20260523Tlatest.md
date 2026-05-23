# phase: phase-11

## Active Goal
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Latest Evidence
- The fresh `20260523T032753Z` gate still fails: LongMemEval is `29 pass / 1 fail`, LoCoMo is `20 pass / 10 fail`.
- The earlier review verdict is stale relative to the fresh reports. It flags `3b6f954b` and `conv-26_qa_028`, but the new reports mark both as `unchanged_pass`.
- The current LongMemEval regression is `51a45a95` with `failure_class=evidence_hit_answer_fail` and full handoff intact through citation.
- The current LoCoMo regression of interest is `conv-26_qa_027` with `failure_class=evidence_hit_answer_fail` and `failure_boundary=citation_drop`.
- Remaining LoCoMo retrieval misses are still present, so the gate is not yet at same-case ACK quality.

## Decision
Continue fixing Phase 11. Do not escalate to `GOD_ADJUST` yet; the lane still has concrete, localizable handoff diagnostics to tighten.

## Narrowest Next RED Test
Add a public-case diagnostic test that simulates an expected source surviving retrieval and selection but being dropped before rendering, and assert the report classifies it as `selected-drop` rather than generic missing evidence or answer failure.
