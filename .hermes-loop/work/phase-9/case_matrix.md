# phase: phase-9

# Phase 9 Case Matrix

Context bundle: `.hermes-loop/work/phase-9/context_bundle.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Source report consumed: `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

Failed LoCoMo cases classified: 20.
Judge/source-support risk cases tracked separately: 1.
Validation errors: none.

| case_id | verdict | report_class | path_class | retrieved_hit | selected_hit | rendered_hit | movement | notes |
|---|---:|---|---|---:|---:|---:|---|---|
| `conv-26_qa_003` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sessions absent from retrieval candidate sessions |
| `conv-26_qa_004` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sessions absent from retrieval candidate sessions |
| `conv-26_qa_006` | fail | `evidence_hit_answer_fail` | `temporal_date_miss` | True | True | True | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected evidence reached rendered context; answer/judge failure is separate |
| `conv-26_qa_008` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sessions absent from retrieval candidate sessions |
| `conv-26_qa_011` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sessions absent from retrieval candidate sessions |
| `conv-26_qa_012` | fail | `evidence_hit_answer_fail` | `temporal_date_miss` | True | True | True | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected evidence reached rendered context; answer/judge failure is separate |
| `conv-26_qa_016` | fail | `evidence_hit_answer_fail` | `evidence_rendered_answer_fails` | True | True | True | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected evidence reached rendered context; answer/judge failure is separate |
| `conv-26_qa_019` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sessions absent from retrieval candidate sessions |
| `conv-26_qa_020` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sessions absent from retrieval candidate sessions |
| `conv-26_qa_024` | fail | `evidence_hit_answer_fail` | `evidence_rendered_answer_fails` | True | True | True | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected evidence reached rendered context; answer/judge failure is separate |
| `conv-26_qa_025` | fail | `retrieval_miss` | `retrieval_miss` | False | False | False | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected sources absent from retrieved evidence ids |
| `conv-26_qa_027` | fail | `evidence_hit_answer_fail` | `refusal_despite_evidence` | True | True | True | `unchanged_fail` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; expected evidence reached rendered context; answer/judge failure is separate |
| `conv-26_qa_033` | fail | `evidence_hit_answer_fail` | `evidence_rendered_answer_fails` | True | True | True | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_033 |
| `conv-26_qa_035` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_035 |
| `conv-26_qa_036` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_036 |
| `conv-26_qa_039` | fail | `retrieval_miss` | `retrieval_miss` | False | False | False | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_039 |
| `conv-26_qa_041` | fail | `evidence_hit_answer_fail` | `temporal_date_miss` | True | True | True | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_041 |
| `conv-26_qa_044` | fail | `retrieval_miss` | `retrieval_miss` | False | False | False | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_044 |
| `conv-26_qa_048` | fail | `evidence_hit_answer_fail` | `temporal_date_miss` | True | True | True | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_048 |
| `conv-26_qa_050` | fail | `retrieval_miss` | `session_localization_miss` | False | False | False | `new_case_no_baseline` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; missing baseline comparison for locomo/memoryos_lite/conv-26_qa_050 |
| `conv-26_qa_015` | pass | `unsupported_answer` | `judge_questionable` | True | True | True | `unchanged_pass` | context bundle: .hermes-loop/work/phase-9/context_bundle.md; tracked separately as judge/source-support risk, not a failed case |
