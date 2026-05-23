# phase: phase-11

# Phase 11 Case Matrix

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Evidence Scope

Current Phase 11 reports:

- Summary: `.hermes-loop/work/phase-11/eval_parallel_30_summary_20260523T095835Z.json`
- LongMemEval: `.memoryos/evals/phase11_lme30_handoff_20260523T095835Z_longmemeval.json`
- LoCoMo: `.memoryos/evals/phase11_locomo30_handoff_20260523T095835Z_locomo.json`

## Movement Lists

| benchmark | pass/fail | fail_to_pass | pass_to_fail | unchanged_fail |
|---|---:|---|---|---|
| LongMemEval | `30/0` | `51a45a95` | `-` | `-` |
| LoCoMo | `20/10` | `conv-26_qa_027` | `conv-26_qa_028` | `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025` |

## Support / Citation Summary

| benchmark | supported_cited_answer | unsupported_answer | answer_not_supported_by_judge |
|---|---:|---:|---:|
| LongMemEval | `30` | `0` | `0` |
| LoCoMo | `20` | `1` | `9` |

## Current ACK Blockers

| benchmark | case_id | verdict | movement | failure_class | support_status | source_hit | handoff_boundary | disposition |
|---|---|---|---|---|---|---|---|---|
| LoCoMo | `conv-26_qa_028` | `fail` | `pass_to_fail` | `evidence_hit_answer_fail` | `answer_not_supported_by_judge` | `true` | `none` | new regression |
| LoCoMo | `conv-26_qa_005` | `pass` | `unchanged_pass` | `retrieval_miss` | `supported_cited_answer` | `false` | `retrieval_miss` | judged pass but source-miss remains visible |
| LoCoMo | `conv-26_qa_003` | `fail` | `fail_to_pass` | `retrieval_miss` | `answer_not_supported_by_judge` | `false` | `retrieval_miss` | still not ACK-grade because expected source was not hit |
| LoCoMo | `conv-26_qa_004` | `fail` | `unchanged_fail` | `retrieval_miss` | `answer_not_supported_by_judge` | `false` | `retrieval_miss` | still blocking |
| LoCoMo | `conv-26_qa_006` | `fail` | `unchanged_fail` | `evidence_hit_answer_fail` | `answer_not_supported_by_judge` | `true` | `none` | still blocking |
| LoCoMo | `conv-26_qa_008` | `fail` | `unchanged_fail` | `retrieval_miss` | `answer_not_supported_by_judge` | `false` | `retrieval_miss` | still blocking |
| LoCoMo | `conv-26_qa_016` | `fail` | `unchanged_fail` | `evidence_hit_answer_fail` | `answer_not_supported_by_judge` | `true` | `none` | still blocking |
| LoCoMo | `conv-26_qa_019` | `fail` | `unchanged_fail` | `retrieval_miss` | `answer_not_supported_by_judge` | `false` | `retrieval_miss` | still blocking |
| LoCoMo | `conv-26_qa_020` | `fail` | `unchanged_fail` | `retrieval_miss` | `answer_not_supported_by_judge` | `false` | `retrieval_miss` | still blocking |
| LoCoMo | `conv-26_qa_024` | `fail` | `unchanged_fail` | `evidence_hit_answer_fail` | `answer_not_supported_by_judge` | `true` | `none` | still blocking |
| LoCoMo | `conv-26_qa_025` | `fail` | `unchanged_fail` | `retrieval_miss` | `answer_not_supported_by_judge` | `false` | `retrieval_miss` | still blocking |

## Diagnostic Lists

- Retrieval-miss blockers: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`.
- Evidence-hit-answer-fail blockers: `conv-26_qa_006`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_028`.
- Source-miss judged-pass risk: `conv-26_qa_005`.

## Gate Reading

The current `095835Z` gate removes the LongMemEval blocker class entirely, but LoCoMo still has the same retrieval and evidence-hit cluster plus one new pass-to-fail regression. That is an improvement in source grounding, but not enough to claim ACK.
