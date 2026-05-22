# phase: phase-10

# Codex CLI Review - Phase 10

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle path: `.hermes-loop/work/phase-10/context_bundle.md`.

Review mode: read-mostly. I wrote only this review file: `.hermes-loop/work/phase-10/reviews/codex-review-phase-10-cli.md`.

## Files Reviewed

- Phase 10 artifacts: `.hermes-loop/work/phase-10/context_bundle.md`, `god_dispatch.json`, `plan_final.md`, `result.md`, `execute_review.md`, `case_matrix.md`, `stale_index.md`, `red_result.md`, eval heartbeat files, eval summary JSON files, and existing review artifact.
- Phase 9 baseline artifacts: `.hermes-loop/work/phase-9/ack.json`, `result.md`, `case_matrix.md`, `failure_taxonomy.md`.
- Current git status/diff, including modified source/tests: `src/memoryos_lite/retrieval/episode_searcher.py`, `src/memoryos_lite/retrieval/recall_pipeline.py`, `src/memoryos_lite/context_composer.py`, `src/memoryos_lite/engine.py`, `tests/test_episode_retrieval.py`, `tests/test_recall_pipeline.py`, `tests/test_public_benchmarks.py`.
- Eval reports: `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`, `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`, `.memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json`, `.memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json`, `.memoryos/evals/phase10_locomo30_projected_packets_20260522T202000Z_locomo.json`.
- Defaults and public diagnostics: `src/memoryos_lite/config.py`, `src/memoryos_lite/public_benchmarks.py`, `src/memoryos_lite/public_case_diagnostics.py`.

## Findings By Severity

Blocking: none.

High: none.

Medium: none.

Low: raw Phase 10 report rows still have `movement_status: new_case_no_baseline` because the reports were not generated with comparison paths. The phase matrix re-derives same-case movement and is internally consistent, but consumers should not trust the raw report-row movement field for promotion. Evidence: same-case movement is recorded in `.hermes-loop/work/phase-10/case_matrix.md:17` and `.hermes-loop/work/phase-10/case_matrix.md:18`, while the current reports require external comparison to Phase 8.

Low: the new tests cover LoCoMo weak-session anchor, packet-neighbor preservation, recall-pipeline metadata, public v3 packet reporting, and kernel default-off behavior. I did not find a new focused LongMemEval-style unit guard in the added tests; the LongMemEval regression guard is mainly the 30-case full-chain gate plus the existing direct-hit test at `tests/test_episode_retrieval.py:145`. This is acceptable for Phase 10 because the selector is gated and LongMemEval same-case movement has no pass-to-fail, but it should be tightened if packet selection broadens.

## Behavioral Review

The change is real behavior on the v3/public path, not demo-only metadata. `RecallMemorySearcher.search()` routes direct hits through `_select_direct_hits()` before top-k selection at `src/memoryos_lite/retrieval/episode_searcher.py:227`; packet metadata and session diversification are gated by `preserve_neighbors` plus benchmark session metadata at `src/memoryos_lite/retrieval/episode_searcher.py:319`. Same-session neighbor expansion still rejects cross-session neighbors when both sides carry `benchmark_session_id` at `src/memoryos_lite/retrieval/episode_searcher.py:531`.

Packet/session metadata propagates through the real chain: recall metadata at `src/memoryos_lite/retrieval/recall_pipeline.py:132`, v3 composer metadata at `src/memoryos_lite/context_composer.py:169`, and service conversion into public/eval context metadata at `src/memoryos_lite/engine.py:2226`.

Defaults and fallbacks are preserved. Config still defaults to v3 memory arch, kernel off, and recall pipeline v1 at `src/memoryos_lite/config.py:29`. The v3 route remains controlled by `resolved_memory_arch` at `src/memoryos_lite/engine.py:2124`, and the public benchmark tests explicitly cover default-off kernel behavior at `tests/test_public_benchmarks.py:1970` and opt-in kernel behavior at `tests/test_public_benchmarks.py:1989`.

I found no case-id, expected-answer, expected-source, fixed QA-string, or benchmark-run-id leakage in the modified source. `benchmark_session_id` is used as provenance/scope metadata, not as a known-case branch.

## Test And Eval Assessment

I did not rerun pytest in this CLI review because the lane was read-only except for this review file. I did run read-only parsing checks over the JSON reports and phase artifacts.

Lane-recorded verification in `.hermes-loop/work/phase-10/result.md:23` through `.hermes-loop/work/phase-10/result.md:26` reports:

- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q` -> 17 passed.
- `uv run pytest tests/test_public_benchmarks.py -q` -> 38 passed.
- `uv run ruff check .` -> all checks passed.
- `uv run pytest -q` -> 419 passed, 1 warning.

RED evidence is present before implementation: `.hermes-loop/work/phase-10/red_result.md` records three initial failures for missing session-diversity rank features, missing recall packet metadata, and missing public v3 packet metadata; `.hermes-loop/work/phase-10/result.md:18` and `.hermes-loop/work/phase-10/result.md:19` summarize both the initial RED and neighbor-preservation iteration RED.

The milestone eval evidence is usable. I parsed the Phase 8 and current Phase 10 reports and re-derived same-case movement:

- LongMemEval 30: 29 pass / 1 fail, movement `unchanged_pass=29`, `unchanged_fail=1`, pass-to-fail=0.
- LoCoMo 30: 20 pass / 10 fail, movement `unchanged_pass=18`, `unchanged_fail=10`, `fail_to_pass=2`, pass-to-fail=0.

The ACK-eligible LoCoMo signal is case-level, not aggregate-only: `conv-26_qa_011` moved from Phase 9 `session_localization_miss` to pass with expected source `conv-26_qa_011:conv-26:D3:13` in final context, recorded at `.hermes-loop/work/phase-10/case_matrix.md:29` and summarized at `.hermes-loop/work/phase-10/case_matrix.md:47`. `conv-26_qa_012` is correctly treated as supporting signal from a temporal/date class at `.hermes-loop/work/phase-10/case_matrix.md:30` and `.hermes-loop/work/phase-10/case_matrix.md:48`.

The heartbeat and summary JSON artifacts are now phase-bound and show final 30-row judged LLM runs: `.hermes-loop/work/phase-10/eval_heartbeat_longmemeval.json:2`, `.hermes-loop/work/phase-10/eval_heartbeat_locomo.json:2`, `.hermes-loop/work/phase-10/eval_parallel_30_summary_packets_20260522T202553Z.json:2`. This satisfies the JSON phase-binding requirement from `.hermes-loop/work/phase-10/context_bundle.md:392`.

## Stale Artifact And Context Lineage

The reviewed Phase 10 Markdown artifacts start with `# phase: phase-10`, and the reviewed Phase 10 JSON artifacts include `"phase": "phase-10"`. `stale_index.md` correctly excludes invalid Phase 8 heartbeat retry reports from promotion evidence. The plan, result, execute review, and case matrix cite `.hermes-loop/work/phase-10/context_bundle.md`.

## Verdict

God may create `review_verdict.json` and `ack.json`.

PASS
