# phase: phase-9

Active goal, quoted:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-9/context_bundle.md`.

# Phase 9 Diagnostic Replay Specification

## Objective

Build diagnostic replay artifacts for Phase 9 from the real phase-8 v3 public benchmark report rows. The target is `failure-replay-ready`, not a benchmark score improvement. This phase must classify all 20 phase-8 LoCoMo failures and track the `conv-26_qa_015` judge/source-support risk case separately.

## Inputs

- Required context: `.hermes-loop/work/phase-9/context_bundle.md`.
- Dispatch: `.hermes-loop/work/phase-9/god_dispatch.json`.
- Real baseline report: `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.
- Regression context report: `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`.
- Current diagnostic source: `src/memoryos_lite/public_case_diagnostics.py`, `src/memoryos_lite/public_benchmarks.py`, `src/memoryos_lite/diagnostic_report.py`.
- Letta semantic reference only: explicit source-attributed passages, component accounting, and traceable provenance. Do not add Letta as a dependency.

## Required Outputs For Execute Lane

- `.hermes-loop/work/phase-9/failure_taxonomy.md`
- `.hermes-loop/work/phase-9/case_matrix.md`
- `.hermes-loop/work/phase-9/replay_schema.md`
- `.hermes-loop/work/phase-9/replay_cases/<case_id>.json` for each of the 20 failed LoCoMo cases
- `.hermes-loop/work/phase-9/result.md`
- `.hermes-loop/work/phase-9/execute_review.md`
- `.hermes-loop/work/phase-9/reviews/*.md`
- `.hermes-loop/work/phase-9/review_verdict.json`
- `.hermes-loop/work/phase-9/ack.json` or `.hermes-loop/work/phase-9/adjustment.md`

Every artifact must cite `.hermes-loop/work/phase-9/context_bundle.md`.

## Replay Row Contract

Each failed LoCoMo replay row must contain:

- `case_id`
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

`source_metrics` must include retrieval/source overlap fields only. `judge_metrics` must include verdict, reasoning, answer support, citation contract, and unsupported/refusal fields. This prevents treating public `source_hit` as pure retrieval localization.

## Required Path-Level Classes

The taxonomy must represent:

- `retrieval_miss`
- `session_localization_miss`
- `temporal_date_miss`
- `speaker_entity_confusion`
- `evidence_retrieved_not_selected`
- `evidence_selected_not_rendered`
- `evidence_rendered_answer_fails`
- `unsupported_citation`
- `refusal_despite_evidence`
- `judge_questionable`
- `diagnostic_gap`

When the report row supports only a broader class, the replay generator must use `diagnostic_gap` with notes instead of guessing. For example, semantic distinctions such as temporal/date miss versus speaker/entity confusion require explicit evidence in the row or a deterministic diagnostic note; otherwise they remain `diagnostic_gap`.

## Classification Rules

Rules run in order:

1. If judge status is questionable or the case is a configured judge/source-support risk, classify as `judge_questionable` for the risk artifact without changing its pass/fail count.
2. If no expected source is indexed, classify as `diagnostic_gap` unless the row explicitly identifies source-not-indexed.
3. If expected sources are absent from retrieved ids and expected sessions are absent from retrieval sessions, classify as `session_localization_miss`.
4. If expected sources are absent from retrieved ids but expected sessions are present, classify as `retrieval_miss`.
5. If expected sources are retrieved but not selected, classify as `evidence_retrieved_not_selected`.
6. If expected sources are selected but not rendered, classify as `evidence_selected_not_rendered`.
7. If citations reference unsupported ids, classify as `unsupported_citation`.
8. If the answer refuses despite rendered expected evidence, classify as `refusal_despite_evidence`.
9. If expected evidence is rendered and the judge still fails, classify as `evidence_rendered_answer_fails`.
10. If row text/reasoning deterministically identifies a date mismatch, classify as `temporal_date_miss`.
11. If row text/reasoning deterministically identifies speaker/entity confusion, classify as `speaker_entity_confusion`.
12. Otherwise classify as `diagnostic_gap`.

Rules 10 and 11 may be implemented conservatively by notes-only detection in Phase 9. They must not rely on case-id hacks or expected-answer leaks.

## Anti-Demo Gate

Usable completion requires:

- all 20 phase-8 LoCoMo failed cases are present in the matrix and per-case artifacts;
- `conv-26_qa_015` is tracked as judge/source-support risk and not counted as a failure;
- real phase-8 report rows are consumed;
- generated replay artifacts separate source/retrieval metrics from judged answer quality;
- every missing or unclassifiable field becomes an explicit `diagnostic_gap` note;
- no retrieval ranking, answer prompt/projection, benchmark scoring, v1 fallback, v3 default, or kernel default change is made.

## Testing Requirement

Before production diagnostic helper changes, add focused RED tests that fail because the current code does not expose the Phase 9 replay schema and path-level taxonomy. The RED tests must consume at least one real phase-8 LoCoMo report row or a fixture copied from a real row. Production code is only allowed after those tests fail for the expected missing diagnostic capability.

If execution proves no production code is needed, the lane must still test the artifact generator and explicitly record that retrieval/answer behavior changes are not applicable.
