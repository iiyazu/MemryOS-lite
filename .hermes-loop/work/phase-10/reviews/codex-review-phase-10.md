# phase: phase-10

# Codex Review - Phase 10

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle path: `.hermes-loop/work/phase-10/context_bundle.md`.

Review mode: read-only. No source, test, docs, state, blueprint, or active lane artifacts were modified by this review. This review wrote only `.hermes-loop/work/phase-10/reviews/codex-review-phase-10.md`.

## Files Reviewed

- Phase 10 artifacts: `.hermes-loop/work/phase-10/context_bundle.md`, `god_dispatch.json`, `plan_final.md`, `result.md`, `execute_review.md`, `case_matrix.md`, `stale_index.md`, `red_result.md`, eval heartbeat and summary artifacts.
- Phase 9 baseline artifacts: `.hermes-loop/work/phase-9/ack.json`, `result.md`, `case_matrix.md`, `failure_taxonomy.md`, selected replay cases including `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_011`, and `conv-26_qa_012`.
- Modified source/tests: `src/memoryos_lite/retrieval/episode_searcher.py`, `src/memoryos_lite/retrieval/recall_pipeline.py`, `src/memoryos_lite/context_composer.py`, `src/memoryos_lite/engine.py`, `tests/test_episode_retrieval.py`, `tests/test_recall_pipeline.py`, `tests/test_public_benchmarks.py`.
- Supporting docs/default guards: `docs/known-issues.md`, `docs/public-benchmark-diagnosis.md`, `docs/agentic-memory-roadmap-zh.md`, `src/memoryos_lite/config.py`.
- Git diff/status and eval reports: `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`, `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`, `.memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json`, `.memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json`, `.memoryos/evals/phase10_locomo30_projected_packets_20260522T202000Z_locomo.json`.

## Findings By Severity

Blocking: none.

High: none.

Medium: none.

Low: raw eval report rows still carry `movement_status: new_case_no_baseline`, so same-case movement is not self-contained in the report JSON. I independently re-derived the Phase 8 vs Phase 10 movement and it matches the lane artifact, but promotion consumers must use `case_matrix.md` or an equivalent cross-report comparison rather than trusting report-row movement fields. The phase artifact does list the cross-report movement at `.hermes-loop/work/phase-10/case_matrix.md:15`-`19` and case-level movement at `.hermes-loop/work/phase-10/case_matrix.md:23`-`37`.

Low: the new RED tests cover the target LoCoMo weak-anchor and same-session packet-neighbor behavior, but there is no new focused unit test named as a LongMemEval-like strong direct-hit guard. Existing direct-hit behavior remains covered without `preserve_neighbors` at `tests/test_episode_retrieval.py:145`-`157`, and the LongMemEval 30 gate shows no same-case collapse. This is acceptable for Phase 10 but should be tightened if the selector broadens.

## Behavioral Review

The source change is real behavior, not metadata-only. `RecallMemorySearcher.search()` now calls `_select_direct_hits()` before top-k selection at `src/memoryos_lite/retrieval/episode_searcher.py:227`-`235`. The selector is gated on `preserve_neighbors` and the presence of `benchmark_session_id`, then annotates selected hits with packet metadata at `src/memoryos_lite/retrieval/episode_searcher.py:319`-`390`. Same-session neighbor expansion uses packet anchors and still rejects cross-`benchmark_session_id` neighbors when both sides provide session metadata at `src/memoryos_lite/retrieval/episode_searcher.py:525`-`536`.

Packet/session metadata is propagated through the real v3/public path: recall package metadata at `src/memoryos_lite/retrieval/recall_pipeline.py:132`-`149`, v3 composer metadata at `src/memoryos_lite/context_composer.py:169`-`200`, and service conversion for public/eval packages at `src/memoryos_lite/engine.py:2226`-`2237`.

Defaults and fallbacks are preserved. Config still defaults to `memoryos_memory_arch = "v3"`, `memoryos_agent_kernel = "off"`, and `memoryos_recall_pipeline = "v1"` at `src/memoryos_lite/config.py:29`-`31`. The v3 path remains selected only by resolved memory arch at `src/memoryos_lite/engine.py:2124`-`2125`, v2 recall remains opt-in for ingest/build routing at `src/memoryos_lite/engine.py:1566`-`1569` and `src/memoryos_lite/engine.py:2028`-`2034`, and explicit kernel behavior remains covered by tests at `tests/test_public_benchmarks.py:1970`-`1986` and `tests/test_public_benchmarks.py:2017`-`2045`.

I did not find case-id, expected-answer, expected-source, or fixed QA-string leakage in the modified source. The one benchmark-specific input is `benchmark_session_id`, which is already part of the public benchmark diagnostics and is used as provenance/scope metadata rather than branching on known cases.

## Test And Eval Evidence Assessment

Fresh review-run verification:

- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q` -> `17 passed in 5.87s`.
- `uv run pytest tests/test_public_benchmarks.py -q` -> `38 passed in 79.59s`.
- `uv run ruff check .` -> `All checks passed!`.

Lane-reported full verification was not fully rerun by this review, but `result.md` records `uv run pytest -q -> 419 passed, 1 warning` at `.hermes-loop/work/phase-10/result.md:21`-`26`.

RED evidence is adequate for the implemented behavior: `red_result.md` records failing tests before production code for missing `session_diversified_anchor`, missing `recall_evidence_packets`, and missing public v3 packet metadata at `.hermes-loop/work/phase-10/red_result.md:11`-`33`. The implemented tests exercise the searcher, recall pipeline, and public v3 benchmark report path at `tests/test_episode_retrieval.py:160`-`209`, `tests/test_recall_pipeline.py:125`-`161`, and `tests/test_public_benchmarks.py:1015`-`1085`.

I independently parsed the Phase 8 and Phase 10 reports for the current 30-case slices. LoCoMo same-case movement is `unchanged_pass=18`, `unchanged_fail=10`, `fail_to_pass=2`, `pass_to_fail=0`; LongMemEval same-case movement is `unchanged_pass=29`, `unchanged_fail=1`, `pass_to_fail=0`. This matches `result.md` at `.hermes-loop/work/phase-10/result.md:28`-`41` and `case_matrix.md` at `.hermes-loop/work/phase-10/case_matrix.md:15`-`19`.

The ACK-eligible LoCoMo signal is case-level, not aggregate-only: `conv-26_qa_011` moved from Phase 9 `session_localization_miss` to pass with expected source `conv-26_qa_011:conv-26:D3:13` in the current LLM report, as recorded at `.hermes-loop/work/phase-10/case_matrix.md:29` and summarized at `.hermes-loop/work/phase-10/case_matrix.md:45`-`50`. `conv-26_qa_012` is supporting signal from a temporal/date failure, not the primary session-localization proof, and is correctly labeled that way at `.hermes-loop/work/phase-10/case_matrix.md:30` and `.hermes-loop/work/phase-10/case_matrix.md:47`-`48`.

The milestone eval evidence is usable but conservative: the heartbeat files show 30/30 judged rows, `answer_mode=llm`, and 29/1 LongMemEval plus 20/10 LoCoMo at `.hermes-loop/work/phase-10/eval_heartbeat_longmemeval.json:2`-`17` and `.hermes-loop/work/phase-10/eval_heartbeat_locomo.json:2`-`17`. Kernel traces are empty in the parsed 30-case reports and in the public default-off test.

## Stale Artifact And Context Lineage

Phase 10 lane artifacts reviewed here start with `# phase: phase-10` and cite `.hermes-loop/work/phase-10/context_bundle.md`. `stale_index.md` says no pre-existing phase-10 `ack.json`, `review_verdict.json`, or `result.md` were present at phase start, and correctly excludes the invalid Phase 8 heartbeat retry reports from promotion evidence.

## Verdict

Final verdict: PASS

God may create `review_verdict.json` and `ack.json`.
