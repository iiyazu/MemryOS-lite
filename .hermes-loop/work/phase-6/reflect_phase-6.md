# phase: phase-6

# Reflection: Answer Projection And Citation Contract

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

The earlier reflection for "Context Composer + Agentic Kernel" was stale and is superseded.

## What Changed

Phase 6 started as an answer citation contract phase, then GOD_ADJUST narrowed the repeat around LoCoMo `conv-26_qa_028` after the stricter answer contract exposed a pass-to-fail case.

Final evidence shows the blocker was two-part:

- expected same-session neighbor evidence `D7:5` / `D7:9` needed to survive into selected/rendered evidence;
- the answerer needed a citation-safe way to answer yes/no career/preference questions from alternative-plan evidence instead of over-refusing.

## Evidence

- Full suite: `uv run pytest -q` -> `396 passed, 1 warning`.
- Lint: `uv run ruff check .` -> `All checks passed!`.
- LongMemEval 30 full-chain LLM judge: `29/30`, `pass_to_fail=0`.
- LoCoMo 30 full-chain LLM judge: `18/30`, `pass_to_fail=0`.
- `conv-26_qa_028`: `unchanged_pass`, `supported_cited_answer`, source overlap includes `D7:5` and `D7:9`.
- Kernel trace rows stayed empty in both milestone reports, so kernel default-off was preserved.

## Blueprint Impact

No immediate blueprint rewrite is required before ACK. Future phases should use the remaining LoCoMo failure taxonomy rather than moving blindly into kernel work:

- LoCoMo unchanged retrieval misses remain: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, plus fail-to-pass cases that still classify as retrieval misses under source metrics.
- Remaining evidence-hit-answer-fail cases should be separated from retrieval misses.
- The yes/no career/preference prompt rule should be watched for overfitting, even though `conv-26_qa_028` now has real expected-source overlap.
