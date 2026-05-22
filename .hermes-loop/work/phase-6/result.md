# phase: phase-6

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-6/context_bundle.md`.

Status: REVIEW_READY_AFTER_GOD_ADJUST_REPEAT.

## Summary

Phase 6 now has both parts of the answer boundary wired into the real public benchmark path:

- answer evidence is structured as `AnswerEvidence` with citation IDs, component, source IDs, session/date metadata, and rendered order;
- deterministic projected answers cite rendered evidence IDs;
- LLM answer prompts require exact allowed `[id]` citations or explicit refusal;
- v3 recall evidence is preserved as answer-renderable retrieved evidence;
- LoCoMo same-session neighbor evidence is preserved for benchmark-session clusters without case IDs or expected-answer leakage;
- answer evidence is ordered by final-context render order instead of lexicographic source ID;
- yes/no career/preference questions can return cautious cited likely yes/no answers when evidence supports an alternative plan or interest.

The earlier blocker `conv-26_qa_028` moved from retrieval miss to supported cited answer in the repeat milestone. No `MEMORYOS_AGENT_KERNEL=v1` run was used for this evidence.

## RED To GREEN Evidence

RED tests added or expanded before implementation:

- `test_public_benchmark_v3_preserves_locomo_neighbor_sources_for_answer_evidence`
  - RED: expected same-session sources `D7:5` / `D7:9` did not survive into public benchmark `source_ids` / rendered evidence.
- `test_public_answerer_guides_yes_no_inference_before_refusal`
  - RED: answerer prompt did not instruct cautious yes/no inference before exact refusal.
- `test_answer_evidence_preserves_final_context_render_order`
  - RED: `_answer_evidence_from_output()` sorted source IDs lexicographically instead of final-context render order.

Supporting earlier Phase 6 RED tests remain green:

- projected answers cite selected evidence;
- unsupported citations are diagnosed;
- structured answer evidence is rendered;
- temporal evidence is not over-refused;
- partial evidence can produce a cited limited answer.

## Implementation

Changed real chain components:

- `retrieval`: `RecallMemorySearcher` can preserve bounded same-session neighbor spans when benchmark-session metadata is present. It keeps legacy behavior for normal capped recall and expands single-hit neighbor diagnostics when top-k is not saturated.
- `context_composer`: verified through v3 final-context trace and LoCoMo neighbor diagnostics.
- `answer_projection`: v3 recall/archival/episode evidence is treated as retrieved evidence for rendered answer sources; answer evidence uses final-context rendered order.
- `public_eval`: LLM answerer uses structured citation evidence and stricter/no-over-refusal prompt rules.

Not changed:

- `ingest` and `store` schemas;
- v1 fallback behavior;
- v3 default setting;
- kernel default. Kernel trace count is `0` in both milestone reports.

## Verification Commands

- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_preserves_locomo_neighbor_sources_for_answer_evidence -q` -> `1 passed`.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_preserves_locomo_neighbor_sources_for_answer_evidence tests/test_episode_retrieval.py -q` -> `11 passed`.
- `uv run pytest tests/test_context_composer.py::test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session tests/test_context_composer.py::test_v3_composer_records_locomo_neighbor_budget_drop tests/test_public_benchmarks.py::test_public_benchmark_reports_locomo_neighbor_diagnostics tests/test_public_benchmarks.py::test_public_benchmark_v3_preserves_locomo_neighbor_sources_for_answer_evidence tests/test_episode_retrieval.py -q` -> `14 passed`.
- `uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py tests/test_episode_retrieval.py tests/test_context_composer.py -q` -> `106 passed`.
- `uv run pytest -q` -> `396 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.
- Single-case LLM smoke: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path .memoryos/tmp/locomo_conv26_qa028.json --baseline memoryos_lite --limit 1 --llm-answer --llm-judge --run-id phase6_god_adjust_conv26_qa028_single_prompt2` -> `conv-26_qa_001 pass`, source overlap includes `D7:5` / `D7:9`.
- Parallel milestone repeat:
  - `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_lme_30_longmemeval.json --run-id phase6_god_adjust_prompt2_lme_30`
  - `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json --run-id phase6_god_adjust_prompt2_locomo_30`

## Case-Level Milestone

LongMemEval report: `.memoryos/evals/phase6_god_adjust_prompt2_lme_30_longmemeval.json`

- rows: 30; pass/fail/error: `29/1/0`
- movement vs Phase 5: `fail_to_pass=11`, `pass_to_fail=0`, `unchanged_pass=18`, `unchanged_fail=1`
- fail-to-pass: `e47becba`, `118b2229`, `58bf7951`, `6ade9755`, `58ef2f1c`, `5d3d2817`, `94f70d80`, `66f24dbb`, `c8c3f81d`, `75499fd8`, `0862e8bf`
- unchanged fail: `51a45a95`
- failure classes: `supported_cited_answer=28`, `evidence_hit_answer_fail=1`, `unsupported_answer=1`
- retrieval miss: `[]`
- context missing evidence: `[]`
- kernel trace non-empty rows: `0`

LoCoMo report: `.memoryos/evals/phase6_god_adjust_prompt2_locomo_30_locomo.json`

- rows: 30; pass/fail/error: `18/12/0`
- movement vs Phase 5: `fail_to_pass=11`, `pass_to_fail=0`, `unchanged_pass=7`, `unchanged_fail=12`
- fail-to-pass: `conv-26_qa_002`, `conv-26_qa_005`, `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_014`, `conv-26_qa_015`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`
- unchanged pass: `conv-26_qa_001`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_028`
- unchanged fail: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_027`
- retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`
- evidence-hit-answer-fail: `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`
- unsupported answer: `[]`
- kernel trace non-empty rows: `0`

`conv-26_qa_028`:

- verdict: `pass`
- movement: `unchanged_pass`
- failure class: `supported_cited_answer`
- source overlap: `D7:5`, `D7:9`
- missing source IDs: `[]`
- `source_hit=true`, `source_hit_at_k=false`, preserving the distinction between top-k retrieval and final evidence overlap.

## Decision

Decision for review lane: `ack_candidate`.

Phase 6 is no longer blocked by `conv-26_qa_028`, has no pass-to-fail cases in either required milestone report, and remains aligned with the active goal. Final ACK still requires read-only review verdict validation.
