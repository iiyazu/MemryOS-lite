# phase: phase-9

Active goal, quoted:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-9/context_bundle.md`.

# Phase 9 Final Plan: Evidence Closure And Failure Replay

## Non-Negotiables

- Phase 9 is diagnostic-first.
- Consume `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.
- Ignore invalid heartbeat retry artifacts `phase8_lme50_hb_20260522T160637Z` and `phase8_locomo50_hb_20260522T160637Z`.
- Do not change retrieval ranking, answer prompts/projection, benchmark scoring, v1 fallback, v3 default, or kernel default.
- Do not claim score improvement.
- Do not hide case-level regressions behind aggregate scores.
- Do not write `ack.json` unless validation is fail-closed and usable.

## RED

1. Add focused failing tests before production diagnostic helper changes.

   Required tests:

   - a real phase-8 LoCoMo failed report row can become a complete replay row only after the new replay schema exists;
   - required path-level classes are declared separately from report-level classes;
   - source/retrieval metrics are separated from judged answer metrics;
   - all 20 phase-8 failed LoCoMo case ids are required for coverage.

   Run each new test directly first, then the whole new test file:

   ```bash
   uv run pytest tests/test_public_failure_replay.py -q
   ```

   Expected RED before implementation: missing module, missing schema, missing taxonomy, or missing coverage validation.

2. If the RED tests unexpectedly pass with existing code, do not add production code. Generate phase-local artifacts from existing helpers and record "behavior changes not applicable" in `result.md` and `ack.json`.

## GREEN

3. Add the minimal diagnostic-only helper, expected file:

   ```text
   src/memoryos_lite/public_failure_replay.py
   ```

   Required API:

   ```python
   REQUIRED_PATH_LEVEL_CLASSES: set[str]
   FAILED_LOCOMO_PHASE8_CASE_IDS: tuple[str, ...]
   JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS: tuple[str, ...]

   def build_replay_row(row: Mapping[str, Any], *, context_bundle: str) -> dict[str, Any]: ...
   def classify_path_level_failure(row: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> str: ...
   def build_case_matrix(rows: Iterable[Mapping[str, Any]], *, context_bundle: str) -> list[dict[str, Any]]: ...
   def validate_phase9_case_coverage(matrix: Sequence[Mapping[str, Any]]) -> list[str]: ...
   ```

   The module must be pure diagnostics: no LLM calls, no retrieval calls, no service construction, no settings mutation, no writes outside explicit artifact generation.

4. Build replay rows with these required fields:

   ```text
   case_id, benchmark, baseline, question, expected_source_ids,
   expected_session_ids, indexed_source_status, indexed_source_ids,
   retrieved_ids, retrieved_overlap_ids, retrieval_candidate_session_ids,
   selected_ids, selected_overlap_ids, rendered_ids, rendered_overlap_ids,
   answer_output, cited_source_ids, unsupported_citation_ids,
   citation_contract_status, answer_support_status,
   explicit_no_evidence_refusal, judge_verdict, judge_reasoning,
   movement_status, report_level_failure_class, path_level_failure_class,
   source_metrics, judge_metrics, source_hit_semantics,
   diagnostic_notes, context_bundle
   ```

5. Classify conservatively:

   - use `judge_questionable` for judge-questionable diagnostics and the `conv-26_qa_015` risk artifact;
   - use `unsupported_citation` for unsupported citations;
   - use `refusal_despite_evidence` for refusal with rendered expected evidence;
   - use `evidence_rendered_answer_fails` for fail verdicts with rendered expected evidence;
   - use `evidence_selected_not_rendered` when expected evidence is selected but absent from rendered ids;
   - use `evidence_retrieved_not_selected` when expected evidence is retrieved but absent from selected ids;
   - use `session_localization_miss` when expected sessions are absent from retrieval candidates;
   - use `retrieval_miss` when expected sources are not retrieved;
   - use `temporal_date_miss` or `speaker_entity_confusion` only when row fields/reasoning deterministically support that narrower class;
   - otherwise use `diagnostic_gap` and write notes.

   `diagnostic_gap` is acceptable when honest. It is not acceptable to hide it or convert it into a cleaner class without evidence.

## REFACTOR

6. Keep helper boundaries small. If artifact writing is added, keep the writer deterministic and phase-local. Do not wire it into default benchmark execution unless needed by tests.

7. Generate required artifacts:

   - `.hermes-loop/work/phase-9/failure_taxonomy.md`
   - `.hermes-loop/work/phase-9/replay_schema.md`
   - `.hermes-loop/work/phase-9/case_matrix.md`
   - `.hermes-loop/work/phase-9/replay_cases/<case_id>.json` for all 20 failed LoCoMo cases
   - `.hermes-loop/work/phase-9/result.md`

   Every artifact must cite `.hermes-loop/work/phase-9/context_bundle.md`.

8. Fail closed before ACK:

   - missing required replay field -> no ACK;
   - missing failed LoCoMo case -> no ACK;
   - source metrics mixed with judge metrics -> no ACK;
   - `conv-26_qa_015` hidden or counted as a failed case -> no ACK;
   - behavior changes made without RED diagnostic proof -> no ACK;
   - kernel default changed -> no ACK;
   - v1 fallback removed or obscured -> no ACK.

## Smoke

9. Run focused tests:

   ```bash
   uv run pytest tests/test_diagnostic_report.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py -q
   ```

10. Run baseline checks:

   ```bash
   uv run pytest -q
   uv run ruff check .
   ```

11. Do not run long benchmark evals unless the implementation changes real public benchmark behavior. If such behavior changes are made, this final plan is no longer sufficient; write `.hermes-loop/work/phase-9/adjustment.md` and require the full 30-case LongMemEval and LoCoMo gate policy from the context bundle.

## Review

12. Write review artifacts:

   - `.hermes-loop/work/phase-9/execute_review.md`
   - `.hermes-loop/work/phase-9/reviews/*.md`
   - `.hermes-loop/work/phase-9/review_verdict.json`

   Review must verify:

   - active goal is satisfied;
   - no demo-only completion;
   - all 20 failed LoCoMo cases are classified;
   - `conv-26_qa_015` is tracked as judge/source-support risk only;
   - real phase-8 rows were consumed;
   - invalid heartbeat artifacts were ignored;
   - no score-improvement claim is made;
   - source metrics and judged answer quality are separated;
   - v1 fallback remains explicit;
   - v3 remains default;
   - kernel remains opt-in.

13. Write final decision:

   - If all gates pass, write `.hermes-loop/work/phase-9/ack.json` with `ack_level: "usable"`.
   - If any gate fails, write `.hermes-loop/work/phase-9/adjustment.md` with exact blockers and next RED test.
