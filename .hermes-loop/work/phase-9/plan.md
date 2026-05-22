# phase: phase-9

Active goal, quoted:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-9/context_bundle.md`.

# Phase 9 Evidence Replay Implementation Plan

> For agentic workers: execute this plan task-by-task. Use TDD. Do not edit retrieval ranking, answer projection, benchmark scoring, v1 fallback, v3 default, kernel default, state, blueprint, or eval reports.

## Goal

Create repeatable diagnostic replay artifacts for the 20 phase-8 LoCoMo failures from real v3 public benchmark report rows.

## Architecture

Add a diagnostic-only replay helper that reads existing public benchmark report rows and emits a stable replay row schema plus path-level failure class. The helper should be separate from retrieval and answer behavior. Artifact writing should be deterministic and phase-local under `.hermes-loop/work/phase-9/`.

## File Structure For Execute Lane

- Create `src/memoryos_lite/public_failure_replay.py`: pure diagnostic transforms from report dictionaries to replay rows, taxonomy classes, and artifact payloads.
- Modify `tests/test_diagnostic_report.py` or create `tests/test_public_failure_replay.py`: focused RED/GREEN tests for replay row completeness, path-level class mapping, and metric separation.
- Modify no retrieval, answer, context composer, engine, store, config default, or kernel behavior unless a RED diagnostic test proves current real report rows cannot classify real cases.
- Write phase-local artifacts under `.hermes-loop/work/phase-9/`: taxonomy, schema, matrix, per-case replay JSON, result, review, verdict, ACK/adjustment.

## RED

1. Add `tests/test_public_failure_replay.py`.

   Test 1 should load a real phase-8 LoCoMo report row, preferably `conv-26_qa_006`, and assert that a replay row exposes every required field:

   ```python
   import json
   from pathlib import Path

   from memoryos_lite.public_failure_replay import build_replay_row


   REQUIRED_FIELDS = {
       "case_id",
       "benchmark",
       "baseline",
       "question",
       "expected_source_ids",
       "expected_session_ids",
       "indexed_source_status",
       "indexed_source_ids",
       "retrieved_ids",
       "retrieved_overlap_ids",
       "retrieval_candidate_session_ids",
       "selected_ids",
       "selected_overlap_ids",
       "rendered_ids",
       "rendered_overlap_ids",
       "answer_output",
       "cited_source_ids",
       "unsupported_citation_ids",
       "citation_contract_status",
       "answer_support_status",
       "explicit_no_evidence_refusal",
       "judge_verdict",
       "judge_reasoning",
       "movement_status",
       "report_level_failure_class",
       "path_level_failure_class",
       "source_metrics",
       "judge_metrics",
       "source_hit_semantics",
       "diagnostic_notes",
       "context_bundle",
   }


   def _load_row(case_id: str) -> dict[str, object]:
       rows = json.loads(
           Path(".memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json")
           .read_text(encoding="utf-8")
       )
       return next(row for row in rows if row["case_id"] == case_id)


   def test_real_locomo_failure_replay_row_is_complete():
       replay = build_replay_row(
           _load_row("conv-26_qa_006"),
           context_bundle=".hermes-loop/work/phase-9/context_bundle.md",
       )

       assert REQUIRED_FIELDS <= set(replay)
       assert replay["case_id"] == "conv-26_qa_006"
       assert replay["context_bundle"] == ".hermes-loop/work/phase-9/context_bundle.md"
       assert replay["expected_source_ids"]
       assert replay["retrieved_ids"]
       assert replay["selected_ids"]
       assert replay["rendered_ids"]
       assert replay["report_level_failure_class"] == "evidence_hit_answer_fail"
       assert replay["path_level_failure_class"] in {
           "temporal_date_miss",
           "evidence_rendered_answer_fails",
           "diagnostic_gap",
       }
   ```

   Run:

   ```bash
   uv run pytest tests/test_public_failure_replay.py::test_real_locomo_failure_replay_row_is_complete -q
   ```

   Expected RED: import failure for `memoryos_lite.public_failure_replay` or missing replay fields.

2. Add a RED test proving source metrics and judged answer metrics are separated:

   ```python
   def test_replay_row_keeps_source_metrics_separate_from_judge_metrics():
       replay = build_replay_row(
           _load_row("conv-26_qa_003"),
           context_bundle=".hermes-loop/work/phase-9/context_bundle.md",
       )

       assert replay["source_hit_semantics"] == "final_projection_source_overlap"
       assert "source_hit" in replay["source_metrics"]
       assert "retrieved_overlap_ids" in replay["source_metrics"]
       assert "selected_overlap_ids" in replay["source_metrics"]
       assert "rendered_overlap_ids" in replay["source_metrics"]
       assert "judge_verdict" not in replay["source_metrics"]
       assert "judge_verdict" in replay["judge_metrics"]
       assert "unsupported_citation_ids" in replay["judge_metrics"]
       assert "source_hit" not in replay["judge_metrics"]
   ```

   Run:

   ```bash
   uv run pytest tests/test_public_failure_replay.py::test_replay_row_keeps_source_metrics_separate_from_judge_metrics -q
   ```

   Expected RED: import failure or mixed metrics.

3. Add a RED test proving the required path classes are represented:

   ```python
   from memoryos_lite.public_failure_replay import REQUIRED_PATH_LEVEL_CLASSES


   def test_required_path_level_classes_are_declared():
       assert {
           "retrieval_miss",
           "session_localization_miss",
           "temporal_date_miss",
           "speaker_entity_confusion",
           "evidence_retrieved_not_selected",
           "evidence_selected_not_rendered",
           "evidence_rendered_answer_fails",
           "unsupported_citation",
           "refusal_despite_evidence",
           "judge_questionable",
           "diagnostic_gap",
       } <= REQUIRED_PATH_LEVEL_CLASSES
   ```

   Run:

   ```bash
   uv run pytest tests/test_public_failure_replay.py::test_required_path_level_classes_are_declared -q
   ```

   Expected RED: missing module or missing taxonomy.

## GREEN

4. Implement `src/memoryos_lite/public_failure_replay.py` with only pure transforms:

   - `REQUIRED_PATH_LEVEL_CLASSES: set[str]`
   - `FAILED_LOCOMO_PHASE8_CASE_IDS: tuple[str, ...]`
   - `JUDGE_SOURCE_SUPPORT_RISK_CASE_IDS: tuple[str, ...]`
   - `build_replay_row(row: Mapping[str, Any], *, context_bundle: str) -> dict[str, Any]`
   - `classify_path_level_failure(row: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> str`
   - `build_case_matrix(rows: Iterable[Mapping[str, Any]], *, context_bundle: str) -> list[dict[str, Any]]`
   - `validate_phase9_case_coverage(matrix: Sequence[Mapping[str, Any]]) -> list[str]`

   Keep all functions read-only and deterministic. Do not import `MemoryOSService`, call retrieval, call LLMs, mutate settings, or write files from this module.

5. Minimal classification implementation:

   - Use `case_diagnostics` when present for `retrieved_evidence_ids`, `selected_context_ids`, `selected_context_overlap_ids`, `rendered_evidence_ids`, `cited_source_ids`, `unsupported_citation_ids`, `citation_contract_status`, `answer_support_status`, `judge_status`, `failure_class`, `movement_status`, and `source_hit_semantics`.
   - Compute expected/retrieved/selected/rendered overlaps from ids.
   - Use report row fields for `expected_session_ids`, `retrieval_candidate_session_ids`, `session_overlap_ids`, and indexed source fields.
   - Return `unsupported_citation` when unsupported citations exist.
   - Return `refusal_despite_evidence` when `explicit_no_evidence_refusal` is true and expected evidence is rendered.
   - Return `evidence_rendered_answer_fails` when expected evidence is rendered and judge verdict is fail.
   - Return `evidence_selected_not_rendered` when expected evidence is selected but not rendered.
   - Return `evidence_retrieved_not_selected` when expected evidence is retrieved but not selected.
   - Return `session_localization_miss` when expected sessions are missing from retrieved candidate sessions.
   - Return `retrieval_miss` when expected sources are not retrieved.
   - Return `judge_questionable` for configured risk rows or judge-questionable diagnostics.
   - Return `diagnostic_gap` when required evidence is absent or the row cannot support a narrower class.

6. Run focused tests:

   ```bash
   uv run pytest tests/test_public_failure_replay.py -q
   ```

   Expected GREEN: all replay tests pass.

## REFACTOR

7. Add a small scriptable artifact writer only if needed. Prefer a function in `public_failure_replay.py` that returns payloads, and use an existing CLI pattern only if the repo already has a suitable diagnostic command. Keep writes phase-local.

8. Generate phase-local artifacts from `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`:

   - `failure_taxonomy.md`: required classes, rule order, diagnostic-gap policy, and `conv-26_qa_015` risk handling.
   - `replay_schema.md`: exact schema with source metrics and judge metrics separated.
   - `case_matrix.md`: all 20 failed LoCoMo cases, plus separate risk section for `conv-26_qa_015`.
   - `replay_cases/<case_id>.json`: one JSON artifact per failed case.
   - `result.md`: verification summary, no behavior-change statement, and no score-improvement claim.

   Every artifact must include `.hermes-loop/work/phase-9/context_bundle.md`.

9. Add coverage validation:

   ```python
   def test_phase9_case_matrix_requires_all_failed_locomo_cases():
       rows = json.loads(
           Path(".memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json")
           .read_text(encoding="utf-8")
       )
       matrix = build_case_matrix(
           rows,
           context_bundle=".hermes-loop/work/phase-9/context_bundle.md",
       )
       missing = validate_phase9_case_coverage(matrix)
       assert missing == []
       assert {row["case_id"] for row in matrix} >= set(FAILED_LOCOMO_PHASE8_CASE_IDS)
   ```

   Run:

   ```bash
   uv run pytest tests/test_public_failure_replay.py::test_phase9_case_matrix_requires_all_failed_locomo_cases -q
   ```

   Expected: PASS.

## Smoke

10. Run focused diagnostics tests:

    ```bash
    uv run pytest tests/test_diagnostic_report.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py -q
    ```

    Expected: PASS.

11. Run baseline checks:

    ```bash
    uv run pytest -q
    uv run ruff check .
    ```

    Expected: PASS, or explicitly blocking failures in `.hermes-loop/work/phase-9/adjustment.md`.

12. Do not run long benchmark evals. Phase 9 is diagnostic-first and should not need 30-case LLM judge gates unless execution changes real public benchmark behavior.

## Review

13. Write `.hermes-loop/work/phase-9/execute_review.md` and `.hermes-loop/work/phase-9/reviews/*.md` covering:

    - active goal match;
    - anti-demo gate;
    - all 20 failed LoCoMo cases classified;
    - `conv-26_qa_015` tracked separately;
    - real phase-8 rows consumed;
    - source metrics separated from judged answer quality;
    - no retrieval/answer/scoring changes;
    - v1 fallback preserved;
    - v3 default preserved;
    - kernel remains opt-in.

14. Write `.hermes-loop/work/phase-9/review_verdict.json`.

15. If all gates pass, write `.hermes-loop/work/phase-9/ack.json` with `ack_level: "usable"`. Otherwise write `.hermes-loop/work/phase-9/adjustment.md` and list the exact blockers.
