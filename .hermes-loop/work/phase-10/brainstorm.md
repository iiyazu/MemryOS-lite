# phase: phase-10

# Phase 10 Brainstorm

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Read-order confirmation: `.hermes-loop/work/phase-10/context_bundle.md` was read first, then `.hermes-loop/work/phase-10/god_dispatch.json`, then Phase 9 evidence files, then the recall code/tests named by the bundle.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Current Phase 10 Hypothesis

The Phase 9 LoCoMo failures show a repeated recall/session-localization problem: expected sources are indexed, but retrieved/selected/rendered overlap is zero because lexical ranking fills the evidence window with plausible wrong sessions. The likely weak point is not storage or answer projection; it is the recall packet that reaches v3 context. A Letta-style route should make retrieved evidence more passage-like: scoped, provenance-rich, session-aware, and auditable through the real v3/public benchmark path.

## Implementation Approaches

1. Recommended: session-aware evidence packets in recall.
   - Build ranked packets around direct hits rather than treating every message as an isolated candidate. A packet would keep the anchor message, same benchmark session, neighbor offsets, source refs, and rank features together, then select a bounded mix of packets before rendering.
   - This directly targets Phase 9 session-localization misses while preserving existing diagnostics such as `benchmark_session_id`, `neighbor_of`, `rank_features`, and `planned_evidence_message_ids`.
   - Risk: over-expansion could pull irrelevant same-session context. Guard with unrelated-session neighbor tests and LongMemEval strong-hit stability tests.

2. Session diversification before top-k truncation.
   - Keep current direct-hit scoring, but reserve candidate slots across distinct `benchmark_session_id` values before selecting final hits.
   - This is simple and likely helps broad LoCoMo questions, but it may dilute strong lexical hits and is weaker when the correct session has no direct lexical anchor.
   - Risk: improves candidate variety without improving expected-source recall; should be accepted only if same-case evidence movement is visible.

3. Query-analysis boosts for LoCoMo-style facets.
   - Extend `QueryAnalyzer` beyond temporal/assistant/multi-session into speaker/entity, relationship/status, activity, and support/counseling-style facets, then apply narrow boosts in `RecallMemorySearcher`.
   - This may help specific failure families, but it is more fragile and easier to overfit to benchmark wording.
   - Risk: benchmark-specific lexical knobs. Use only if packet/diversification tests prove insufficient.

Recommendation: start with approach 1, with a small amount of approach 2 only if tests prove packets need pre-truncation session diversity. Avoid approach 3 unless a RED test shows a general query facet, not a case-specific phrase, is required.

## Tradeoffs And Risks

- Recall gain vs noise: larger packets improve session continuity but can crowd out exact direct hits.
- LoCoMo vs LongMemEval: LoCoMo benefits from session continuity; LongMemEval may prefer sharp direct retrieval. The LongMemEval 30 gate must detect collapse.
- Diagnostics vs behavior: adding metadata alone is partial unless `episode_candidate_message_ids`, `planned_evidence_message_ids`, selected/rendered ids, and case movement change through the public path.
- Letta comparison: borrow passage-level provenance, scope, and component accounting semantics only. Do not add Letta as a dependency or port internals.

## Demo-Only Or Partial Work

Demo-only or partial means any of:

- only adding reports, metadata, or docs while Phase 9 failure slices remain unchanged;
- improving aggregate LoCoMo without listing same-case fail-to-pass, pass-to-fail, unchanged-fail, and failure-class movement;
- testing only synthetic happy paths and not encoding at least one real Phase 9 repeated failure pattern;
- using final `source_hit` as proof of retrieval localization without retrieval/selected/rendered evidence movement;
- changing answer projection, scoring, v1 fallback, or kernel defaults to make the phase look complete.

## TDD RED Evidence Candidates

Use real Phase 9 LoCoMo failures as RED inputs or synthetic fixtures derived from their failure shape:

- `conv-26_qa_003`: question asks Caroline education fields; expected session `D1`; retrieved candidate sessions were `D10,D13,D18,D19,D4,D7`; expected sources had zero retrieved/selected/rendered overlap.
- `conv-26_qa_004`: question asks what Caroline researched; expected session `D2`; retrieved candidate sessions were `D1,D10,D17,D19`; answer refused due to missing adoption-agency evidence.
- `conv-26_qa_008`: relationship status; expected sessions `D2,D3`; retrieved candidate sessions were `D11,D12,D14,D19,D7,D8`; no expected evidence reached context.
- `conv-26_qa_019` / `conv-26_qa_020`: Melanie camping/kids preferences; expected sessions `D4,D6` or `D4,D6,D8`; retrieved sessions missed expected session ids entirely.
- `conv-26_qa_050`: pride festival date; expected session `D12`; retrieved candidate sessions were `D10,D13,D14,D17,D19,D8`.

Minimum RED tests before implementation:

- `RecallMemorySearcher` or `RecallPipeline` loses a weak same-session LoCoMo anchor to stronger wrong-session lexical hits.
- Neighbor expansion does not cross `benchmark_session_id` and does not pull unrelated session neighbors.
- A strong LongMemEval-like direct hit remains top-ranked and rendered after packet/session behavior changes.
- Public/v3 diagnostics expose candidate, planned, selected, and rendered movement for the fixed failing slice.

## Explicit Non-Goals

- No answer projection work.
- No v1 fallback regression.
- No kernel default change.
- No case-id hacks.
- No expected-answer hacks.
- No benchmark-specific constants or expected-source leakage.

## Verification And Gates

Minimum focused verification:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
uv run pytest tests/test_public_benchmarks.py -q
uv run ruff check .
```

Baseline verification before promotion:

```bash
uv run pytest -q
uv run ruff check .
```

Milestone eval gate:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge
```

ACK requirements:

- At least one repeated LoCoMo retrieval/session class improves or becomes a more precise downstream class.
- LoCoMo 30 has same-case explainable signal, not aggregate-only movement.
- LongMemEval 30 has no material collapse.
- Every pass-to-fail is listed with cause and disposition.
- `case_matrix.md` separates retrieval/source movement from judged answer quality.
- Kernel remains default-off and explicit `MEMORYOS_MEMORY_ARCH=v1` behavior remains covered.

decision=recommend_session_aware_evidence_packets
