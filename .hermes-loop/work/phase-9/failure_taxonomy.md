# phase: phase-9

# Phase 9 Failure Taxonomy

Context bundle: `.hermes-loop/work/phase-9/context_bundle.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Source report consumed: `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

## Required Path-Level Classes

- `diagnostic_gap`
- `evidence_rendered_answer_fails`
- `evidence_retrieved_not_selected`
- `evidence_selected_not_rendered`
- `judge_questionable`
- `refusal_despite_evidence`
- `retrieval_miss`
- `session_localization_miss`
- `speaker_entity_confusion`
- `temporal_date_miss`
- `unsupported_citation`


## Phase 8 LoCoMo Failed-Case Distribution

- `evidence_rendered_answer_fails`: 3
- `refusal_despite_evidence`: 1
- `retrieval_miss`: 3
- `session_localization_miss`: 9
- `temporal_date_miss`: 4


## Report-Level Distribution Kept Separate

- `evidence_hit_answer_fail`: 8
- `retrieval_miss`: 12


## Judge/Source-Support Risk

- `conv-26_qa_015` is tracked separately as `judge_questionable` and is not counted among the 20 failed cases.

## Diagnostic-Gap Policy

Missing or unclassifiable evidence is represented as `diagnostic_gap` with explicit notes. It is not converted into retrieval, selection, rendering, or answer failure unless the real report row contains the needed evidence-path fields.
