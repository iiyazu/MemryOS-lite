# phase: phase-9

# Phase 9 Replay Schema

Context bundle: `.hermes-loop/work/phase-9/context_bundle.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Source report consumed: `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

## Row Fields

- `case_id`
- `phase`
- `benchmark`
- `baseline`
- `question`
- `expected_source_ids`
- `expected_session_ids`
- `indexed_source_status`
- `indexed_source_ids`
- `retrieved_ids`
- `retrieved_overlap_ids`
- `retrieval_candidate_session_ids`
- `selected_ids`
- `selected_overlap_ids`
- `rendered_ids`
- `rendered_overlap_ids`
- `answer_output`
- `cited_source_ids`
- `unsupported_citation_ids`
- `citation_contract_status`
- `answer_support_status`
- `explicit_no_evidence_refusal`
- `judge_verdict`
- `judge_reasoning`
- `movement_status`
- `report_level_failure_class`
- `path_level_failure_class`
- `source_metrics`
- `judge_metrics`
- `source_hit_semantics`
- `diagnostic_notes`
- `context_bundle`

## Separation Contract

`source_metrics` contains retrieval/source-overlap accounting only: expected source counts, indexed/retrieved/selected/rendered source counts, overlap counts, stage hit booleans, retrieval session hit, final source hit, and source-hit semantics.

`judge_metrics` contains answer/judge accounting only: judge verdict, judge status, answer support status, citation contract status, unsupported citation count, and explicit no-evidence refusal.

`source_hit_semantics` is `final_projection_source_overlap_not_retrieval_localization`; it must not be treated as proof that expected evidence was retrieved, selected, or rendered.
