# phase: phase-10

# Phase 10 Execute Self Review

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Real Chain Changed

- Retrieval changed in the real v3/public benchmark path via `RecallMemorySearcher` and `RecallPipeline`.
- v3 composer and service conversion preserve packet/session metadata into public benchmark `v3_context` reports.
- No answer prompt/projection, scoring, v1 fallback, or kernel-default changes were made.

## Demo-Only Or Partial Risk

- Not demo-only: packet metadata is emitted by real recall hits and appears in public benchmark reports.
- Not metadata-only: selected packet anchors now preserve bounded same-session neighbors, which moved `conv-26_qa_011` expected source into final context.
- Remaining partial area: several LoCoMo retrieval misses remain unsolved and should drive the next phase/iteration.

## Tests Proving Behavior

- `test_recall_searcher_session_diversity_keeps_weak_same_session_anchor` proves session-diversified anchor metadata is selected.
- `test_recall_searcher_preserves_packet_neighbors_when_direct_hits_fill_top_k` proves full direct-hit sets still preserve same-session packet neighbors.
- `test_recall_pipeline_emits_session_packet_metadata` proves package/evidence metadata propagation.
- `test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice` proves real public/v3 reporting path visibility and kernel default-off.

## Benchmark Movement

- LongMemEval current-code 30: 29 pass / 1 fail; no pass-to-fail vs Phase 8 same cases.
- LoCoMo current-code 30: 20 pass / 10 fail; `conv-26_qa_011` and `conv-26_qa_012` fail-to-pass; no pass-to-fail.
- Source/retrieval evidence is kept separate from judged answer quality in `case_matrix.md`.

## Defaults And Fallbacks

- v1 fallback preserved by explicit public benchmark guard.
- v3 default preserved by context composer/public benchmark guards.
- kernel default remains off; public benchmark packet test and kernel default-off test report empty `kernel_trace_events` unless explicitly enabled.
