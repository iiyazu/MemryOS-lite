# phase: phase-17

Decision: repair.

The FAIL should be repaired, not repeated, adjusted, or held. The blocking review findings are supported by the artifacts and diff:

- `conv-26_qa_005` is reported as an unchanged judged pass while all source-hit metrics are false, but the summary leaves `source_miss_judge_pass` empty and classifies it as `retrieval_miss`. This violates the phase goal of not hiding source-localization failures behind judge pass/fail.
- Repair-smoke comparison currently tolerates missing baseline rows: unmatched current rows get no pre-context hook and are skipped in movement/source summaries. That can hide pass-to-fail or source regressions.
- `public_case_diagnostics` can emit context-selection/rendering diagnostic classes that `public_repair_smoke` does not bucket, so Phase 17 can still hide required failure modes.

Repair scope should stay narrow:

- Add RED tests for judge-pass/source-miss, missing/extra/duplicate baseline rows, and each dropped diagnostic class.
- Classify judge-pass/source-miss before generic retrieval miss, or normalize it in the repair summary based on verdict plus source metrics.
- Validate fixed-slice baseline/current row parity before running or before writing a successful summary; missing/extra/duplicate rows must block the gate rather than disappear.
- Normalize `evidence_retrieved_not_selected`, `evidence_selected_not_rendered`, and `evidence_rendered_not_answer_evidence` into `context_missing_evidence` or explicit reported buckets.
- Track `src/memoryos_lite/public_repair_smoke.py`; the current tracked diff is not reproducible without it.

No repeat eval is useful before those repairs. No adjustment is warranted because the review criteria match the phase objective and context bundle. Hold is unnecessary because the defects are local and repairable without changing the phase goal or enabling the v3 kernel by default.
