# phase: phase-10

# Phase 10 Case Matrix

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Final current-code reports:

- LongMemEval 30 LLM: `.memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json` -> 29 pass / 1 fail.
- LoCoMo 30 LLM: `.memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json` -> 20 pass / 10 fail.
- LoCoMo 30 projected diagnostic: `.memoryos/evals/phase10_locomo30_projected_packets_20260522T202000Z_locomo.json` -> source/session movement only, not promotion by itself.

## Movement Summary

- LongMemEval same-case movement vs Phase 8: {'unchanged_pass': 29, 'unchanged_fail': 1}.
- LoCoMo same-case movement vs Phase 8: {'unchanged_pass': 18, 'unchanged_fail': 10, 'fail_to_pass': 2}.
- LoCoMo final failure classes: {'retrieval_miss': 6, 'evidence_hit_answer_fail': 4}.

## LoCoMo Cases

| case_id | movement | phase9_path | old_class | new_class | llm_source_overlap | projected_source_overlap | packet_sessions | disposition |
|---|---|---|---|---|---|---|---|---|
| `conv-26_qa_003` | `unchanged_fail` | `session_localization_miss` | `retrieval_miss` | `retrieval_miss` | `-` | `-` | `D4,D10,D18,D7,D13,D14,D2,D11,D5` | still blocking |
| `conv-26_qa_004` | `unchanged_fail` | `session_localization_miss` | `retrieval_miss` | `retrieval_miss` | `-` | `-` | `D1,D10,D17,D15,D16,D14,D5,D8` | still blocking |
| `conv-26_qa_006` | `unchanged_fail` | `temporal_date_miss` | `evidence_hit_answer_fail` | `evidence_hit_answer_fail` | `conv-26_qa_006:conv-26:D2:1` | `conv-26_qa_006:conv-26:D2:1` | `D2,D8,D14,D3,D11` | still blocking |
| `conv-26_qa_008` | `unchanged_fail` | `session_localization_miss` | `retrieval_miss` | `retrieval_miss` | `-` | `-` | `D14,D7,D11,D8,D12,D15,D16,D9` | still blocking |
| `conv-26_qa_011` | `fail_to_pass` | `session_localization_miss` | `retrieval_miss` | `supported_cited_answer` | `conv-26_qa_011:conv-26:D3:13` | `conv-26_qa_011:conv-26:D3:13` | `D1,D12,D6,D15,D8,D3,D10,D7` | accepted same-case improvement |
| `conv-26_qa_012` | `fail_to_pass` | `temporal_date_miss` | `evidence_hit_answer_fail` | `supported_cited_answer` | `conv-26_qa_012:conv-26:D3:13,conv-26_qa_012:conv-26:D4:3` | `conv-26_qa_012:conv-26:D3:13,conv-26_qa_012:conv-26:D4:3` | `D15,D7,D3,D4,D8,D19,D16` | accepted same-case improvement |
| `conv-26_qa_015` | `unchanged_pass` | `judge_questionable` | `unsupported_answer` | `supported_cited_answer` | `conv-26_qa_015:conv-26:D3:5,conv-26_qa_015:conv-26:D4:15` | `conv-26_qa_015:conv-26:D3:5,conv-26_qa_015:conv-26:D4:15` | `D4,D7,D19,D5,D3,D1` | tracked risk remains pass |
| `conv-26_qa_016` | `unchanged_fail` | `evidence_rendered_answer_fails` | `evidence_hit_answer_fail` | `evidence_hit_answer_fail` | `conv-26_qa_016:conv-26:D5:4` | `conv-26_qa_016:conv-26:D5:4` | `D17,D15,D5,D13,D11,D6,D7,D9,D1` | still blocking |
| `conv-26_qa_019` | `unchanged_fail` | `session_localization_miss` | `retrieval_miss` | `retrieval_miss` | `-` | `-` | `D14,D7,D5,D16,D19,D6` | still blocking |
| `conv-26_qa_020` | `unchanged_fail` | `session_localization_miss` | `retrieval_miss` | `retrieval_miss` | `-` | `-` | `D11,D13,D8,D10,D9,D1,D15,D16` | still blocking |
| `conv-26_qa_024` | `unchanged_fail` | `evidence_rendered_answer_fails` | `evidence_hit_answer_fail` | `evidence_hit_answer_fail` | `conv-26_qa_024:conv-26:D6:10,conv-26_qa_024:conv-26:D7:8` | `conv-26_qa_024:conv-26:D6:10,conv-26_qa_024:conv-26:D7:8` | `D7,D6,D16,D5,D19` | still blocking |
| `conv-26_qa_025` | `unchanged_fail` | `retrieval_miss` | `retrieval_miss` | `retrieval_miss` | `-` | `-` | `D13,D17,D7,D15,D12,D11,D4,D8` | still blocking |
| `conv-26_qa_027` | `unchanged_fail` | `refusal_despite_evidence` | `evidence_hit_answer_fail` | `evidence_hit_answer_fail` | `conv-26_qa_027:conv-26:D7:8` | `conv-26_qa_027:conv-26:D7:8` | `D7,D17,D14,D15,D18,D2,D8` | still blocking |

## LongMemEval Cases

| case_id | movement | old_class | new_class | source_overlap | disposition |
|---|---|---|---|---|---|
| `51a45a95` | `unchanged_fail` | `evidence_hit_answer_fail` | `evidence_hit_answer_fail` | `51a45a95:answer_d61669c7:005` | unchanged fail; no pass-to-fail |

## Gate Reading

- The usable signal is not aggregate-only: `conv-26_qa_011` moved from Phase 9 `session_localization_miss` to pass with expected source `conv-26_qa_011:conv-26:D3:13` in both projected and LLM reports.
- `conv-26_qa_012` also moved fail-to-pass with both expected sources present; Phase 9 classified it as `temporal_date_miss`, so it is supporting but not the primary session-localization signal.
- LoCoMo has no pass-to-fail cases in the current-code 30-case LLM gate.
- LongMemEval has no pass-to-fail cases in the current-code 30-case LLM gate.
