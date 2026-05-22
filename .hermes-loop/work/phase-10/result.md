# phase: phase-10

# Phase 10 Result

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Implemented Chain

- retrieval: changed. `RecallMemorySearcher` now attaches bounded session-aware evidence packet metadata to selected direct hits and allows selected packet anchors to preserve same-session neighbors within the configured neighbor window.
- context_composer: changed. v3 context metadata now carries `recall_evidence_packets`, `recall_candidate_session_ids`, and `recall_planned_session_ids`.
- public_eval: verified. The fields are visible in `v3_context.metadata` through public benchmark reports.
- ingest/store/answer_projection/kernel_loop: not changed.

## RED Evidence

- Initial RED: `3 failed in 4.96s` in `.hermes-loop/work/phase-10/red_result.md` for missing `session_diversified_anchor`, `recall_evidence_packets`, and public v3 packet metadata.
- Iteration RED: `tests/test_episode_retrieval.py::test_recall_searcher_preserves_packet_neighbors_when_direct_hits_fill_top_k` failed with `StopIteration` because a selected packet anchor did not preserve its same-session neighbor.

## Verification

- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q` -> 17 passed in 13.45s.
- `uv run pytest tests/test_public_benchmarks.py -q` -> 38 passed in 47.16s.
- `uv run ruff check .` -> All checks passed.
- `uv run pytest -q` -> 419 passed, 1 warning in 584.96s.

## Eval Evidence

- Current-code LongMemEval 30 full-chain LLM: `.memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json` -> 29 pass / 1 fail; movement {'unchanged_pass': 29, 'unchanged_fail': 1}.
- Current-code LoCoMo 30 full-chain LLM: `.memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json` -> 20 pass / 10 fail; movement {'unchanged_pass': 18, 'unchanged_fail': 10, 'fail_to_pass': 2}.
- Current-code LoCoMo 30 projected diagnostic: `.memoryos/evals/phase10_locomo30_projected_packets_20260522T202000Z_locomo.json` -> used to confirm source movement, not as promotion evidence.
- Heartbeats: `.hermes-loop/work/phase-10/eval_heartbeat_longmemeval.json`, `.hermes-loop/work/phase-10/eval_heartbeat_locomo.json`.

## Decision Evidence

- ACK-eligible same-case LoCoMo signal: `conv-26_qa_011` moved from Phase 9 `session_localization_miss` to pass and includes expected source `conv-26_qa_011:conv-26:D3:13` in projected and LLM final context.
- Supporting LoCoMo signal: `conv-26_qa_012` moved from fail to pass with both expected sources present.
- Current-code LoCoMo pass-to-fail: none.
- Current-code LongMemEval pass-to-fail: none.
- Remaining LoCoMo blockers: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_019`, `conv-26_qa_020`, and `conv-26_qa_025` remain retrieval misses; `conv-26_qa_006`, `conv-26_qa_016`, `conv-26_qa_024`, and `conv-26_qa_027` remain answer/evidence-use failures.
