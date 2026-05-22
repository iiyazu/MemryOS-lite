# phase: phase-4

# Execute Self-Review

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle used first: `.hermes-loop/work/phase-4/context_bundle.md`.

## Verdict

PASS for review-lane handoff.

The previous blocking review finding was valid for the earlier tree: archival eligibility selected fields could describe pre-budget search hits. The current tree now derives `selected_passage_ids`, `selected_source_refs`, `selected_passage_count`, and `archival_selected` diagnostics from archival items actually present in `ContextPackageV3.items` after the budget gate.

## Real Chain Changed

- ingest: verified unchanged.
- store: changed for scoped archive eligibility, archive attachment resolution, scoped passage listing, and passage identity invariants.
- retrieval: changed by feeding the archival searcher only eligible scoped passages in the v3 composer path.
- context_composer: changed to emit scoped archival eligibility metadata and post-budget selected archival diagnostics.
- answer_projection: verified unchanged.
- kernel_loop: verified unchanged; `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.
- public_eval: changed only by append-only archival eligibility diagnostics in public case diagnostics.

## Demo-Only Or Partial Risk

- No demo-only archival helper remains as the success path: real `MemoryOSService.build_context()` routes v3 requests through `ContextComposerRequest` and `V3ContextComposer`.
- The public 30-case benchmark data did not seed attached archives, so the archival eligibility counters are zero in those reports. This is diagnostic plumbing evidence, not an archive-quality improvement claim.
- LoCoMo remains weak at `0/30`; phase-4 must not claim chain-level improvement.

## Tests And Verification

- Review-fix regression: `uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected -q` -> `1 passed in 0.91s`.
- Focused phase-4 suite: `uv run pytest tests/test_archival_store.py tests/test_archival_searcher.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q` -> `76 passed in 56.57s`.
- Full suite: `uv run pytest -q` -> `378 passed, 1 warning in 600.25s`.
- Lint: `uv run ruff check .` -> `All checks passed!`.

## Case-Level Evidence

LongMemEval report: `.memoryos/evals/public_20260522_010216_longmemeval.json`.

- 30 cases, 17 pass / 13 fail.
- Movement: `new_case_no_baseline=30`; no fail-to-pass or pass-to-fail claim.
- Failure classes: `context_missing_evidence=12`, `evidence_hit_answer_fail=4`, `retrieval_miss=3`, `supported_cited_answer=11`.
- Retrieval miss: `58bf7951`, `6ade9755`, `75499fd8`.
- Context missing evidence: `e47becba`, `118b2229`, `58ef2f1c`, `5d3d2817`, `7527f7e2`, `94f70d80`, `66f24dbb`, `af8d2e46`, `c8c3f81d`, `8ebdbe50`, `0862e8bf`, `853b0a1d`.
- Evidence hit answer fail: `51a45a95`, `f8c5f88b`, `3b6f954b`, `dccbc061`.
- Judge questionable: none identified.
- Archival eligibility totals: `selected=0`, `scope_excluded=0`, `no_match=0`.

LoCoMo report: `.memoryos/evals/public_20260522_011335_locomo.json`.

- 30 cases, 0 pass / 30 fail.
- Movement: `new_case_no_baseline=30`; no fail-to-pass or pass-to-fail claim.
- Failure classes: `evidence_hit_answer_fail=9`, `retrieval_miss=11`, `context_missing_evidence=10`.
- Retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- Context missing evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- Evidence hit answer fail: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`.
- Judge questionable: none identified.
- Archival eligibility totals: `selected=0`, `scope_excluded=0`, `no_match=0`.

## Constraints Check

- v1 fallback preserved: explicit v1 guard test passes and v1 context excludes v3 archival eligibility metadata.
- v3 default preserved: no setting change was made to default memory architecture.
- kernel opt-in preserved: no setting change was made to `MEMORYOS_AGENT_KERNEL`.
- Source grounding: post-budget archival selected diagnostics now align with actual context inclusion.
- Benchmark overfitting: no production source case-id or expected-answer hacks were introduced.

Review lane should now regenerate `.hermes-loop/work/phase-4/reviews/codex-review.md`, `.hermes-loop/work/phase-4/review_verdict.json`, and only then allow a usable `ack.json`.
