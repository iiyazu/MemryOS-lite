# phase: phase-11

# GOD_ADJUST - Phase 11

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

Decision: `repeat_phase`.

## Evidence Used

- `.hermes-loop/work/phase-11/eval_parallel_30_summary_20260523T095835Z.json`
- `.memoryos/evals/phase11_lme30_handoff_20260523T095835Z_longmemeval.json`
- `.memoryos/evals/phase11_locomo30_handoff_20260523T095835Z_locomo.json`

No stale or partial gate is used for this adjustment.

## ACK Decision

ACK is blocked.

The current gate improves LongMemEval to a clean `30/30`, but it still does not satisfy the usable anti-demo gate because LoCoMo has a new pass-to-fail regression and still carries the same retrieval / evidence-hit failure cluster.

## Current Blockers

LongMemEval:

- clean in this gate.

LoCoMo:

- `conv-26_qa_028`: `pass_to_fail`, `evidence_hit_answer_fail`.
- `conv-26_qa_005`: `judge_pass`, `source_hit=false`, `retrieval_miss`.
- `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`: remaining failures.

## Next Required Action

Return to `EXECUTE`.

Investigate why the LoCoMo pass-to-fail regression still appears while LongMemEval is clean. Any further fix must start with focused RED tests, preserve the current no-synthesis guard, and then rerun the parallel 30-case full-chain gate before ACK is reconsidered.
