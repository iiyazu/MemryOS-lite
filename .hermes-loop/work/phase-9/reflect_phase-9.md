# phase: phase-9

# Phase 9 Reflection

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Goal And Anti-Demo Gate

Phase 9 satisfied the active goal for its diagnostic scope. It did not claim a score improvement, and it made the phase-8 LoCoMo failures replayable and case-level visible instead of hiding them behind aggregate pass rate.

The anti-demo gate is satisfied. The accepted ACK says the real public eval path is wired, all 20 valid phase-8 LoCoMo failed cases have replay JSON artifacts, `conv-26_qa_015` is tracked separately as a judge/source-support risk, and invalid heartbeat artifacts were ignored. Review found no retrieval ranking, answer prompting/projection, benchmark scoring, v1 fallback, v3 default, or kernel default change.

## Blueprint Amendment

No amendment needed before Phase 10.

The current Phase 10 blueprint already targets recall evidence reliability, requires a failing test for a real repeated LoCoMo failure class, requires fixed-slice and 30-case same-case movement tables, and blocks advancement without explainable LoCoMo gain or precise downstream failure conversion.

## Phase 10 Hypothesis

God should carry forward this hypothesis:

LoCoMo is still the controlling benchmark, and Phase 10 should first target the repeated recall/session-localization cluster, not answer prompting. Phase 9 split the 20 LoCoMo failures into 12 report-level retrieval misses and 8 evidence-hit answer failures. At the path level, the largest actionable class is `session_localization_miss` at 9 cases, followed by `temporal_date_miss` at 4 and direct `retrieval_miss` at 3. A benchmark-session-aware evidence packet with same-session neighbor expansion, temporal/date features, and explicit anchor diagnostics is the most likely Phase 10 lever.

Phase 10 should treat evidence-hit answer failures separately. The three `evidence_rendered_answer_fails`, one `refusal_despite_evidence`, and four `temporal_date_miss` cases prove that source/judge separation must remain explicit; improving source retrieval alone is not equivalent to improving judged answers.

## Minimum Next Verification

Phase 10 should require, at minimum:

- focused pytest for the recall change, including one real repeated Phase 9 LoCoMo failure class;
- a fixed-slice replay over selected Phase 9 LoCoMo failures with same-case movement: pass-to-fail, fail-to-pass, unchanged-fail, retrieved/selected/rendered movement, and failure-class movement;
- LoCoMo 30-case full-chain LLM answer plus judge as the recall milestone gate;
- LongMemEval 30-case full-chain LLM answer plus judge as the regression guard;
- replay/schema checks that `source_metrics`, `judge_metrics`, `source_hit_semantics`, and `phase` bindings remain present;
- explicit confirmation that `MEMORYOS_AGENT_KERNEL` remains opt-in and is not enabled by default.

## Risks To Carry Forward

- Phase binding is currently fixed, but Phase 10 must preserve `# phase: phase-10` in new Markdown artifacts and phase-bound JSON rows where applicable.
- Source/judge separation is now a contract. Do not collapse `source_hit` into retrieval success or judged answer quality.
- LoCoMo regressions remain the main stop condition. A LongMemEval win or stable aggregate is insufficient if LoCoMo same-case movement is unexplained.
- The kernel default remained unchanged in Phase 9. Phase 10 must keep any kernel use opt-in and must not make `MEMORYOS_AGENT_KERNEL=v1` implicit.
- Phase 9 was diagnostic-only. Its artifacts are evidence for where to intervene, not evidence that MemoryOS quality improved.
