# phase: phase-9

Active goal, quoted:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-9/context_bundle.md`.

## PLAN_STORM: Evidence Closure And Failure Replay

Phase 9 is diagnostic-first. The implementation should make phase-8 LoCoMo failures replayable and classifiable from existing real v3 public benchmark report rows before Phase 10 changes retrieval, answer projection, or memory behavior.

## Approaches Compared

### Approach A: Phase-local manual replay matrix only

Write `failure_taxonomy.md`, `case_matrix.md`, `replay_schema.md`, and per-case JSON artifacts by manually transforming `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

Pros:

- Fastest path to readable artifacts.
- No production code risk.
- Cannot accidentally change benchmark behavior.

Cons:

- Easy to drift from future report schema.
- Hard to test completeness beyond ad hoc artifact review.
- Demo-only risk is high because repeatability depends on manual work.

Verdict: reject as the primary approach. It may be acceptable for notes, but not for a usable ACK gate.

### Approach B: Diagnostic replay generator over existing report rows

Add a small diagnostic helper that consumes existing `PublicBenchmarkResult.to_report()` rows or loaded report dictionaries, emits a stable replay row schema, maps report-level failure classes to required path-level classes, and writes phase-local artifacts.

Pros:

- Uses real phase-8 report rows and keeps source metrics separate from judge metrics.
- Testable with focused RED tests before implementation.
- Keeps retrieval, answer, kernel, store, and v1/v3 routing behavior unchanged.
- Repeatable for the 20 failed LoCoMo cases and the `conv-26_qa_015` judge/source-support risk case.

Cons:

- Requires a new diagnostic-only helper and test surface.
- Path-level classes may still need `diagnostic_gap` when the existing report lacks semantic evidence to distinguish temporal/date from speaker/entity confusion.
- Must be careful not to infer unsupported facts from case ids or expected answers.

Verdict: choose this approach.

### Approach C: Re-run selected benchmark cases with richer tracing

Add replay instrumentation to the public benchmark runner and rerun selected phase-8 failures to capture additional trace fields.

Pros:

- Could produce richer current-path evidence if existing report rows are incomplete.
- Useful if a focused RED test proves real phase-8 rows cannot classify cases.

Cons:

- More expensive and more likely to blur diagnostic work with behavior changes.
- Re-runs can produce LLM/judge drift and would weaken same-row reproducibility.
- Not needed unless existing report rows fail the replay completeness tests.

Verdict: keep as fallback only. Do not run long benchmark evals in Phase 9 planning or default execution.

## Chosen Design

Use Approach B: a diagnostic replay generator over the existing phase-8 report rows. The implementation plan should first add RED tests proving the missing durable replay schema/path taxonomy, then add the minimal diagnostic helper and artifact writer. The helper should classify all 20 failed LoCoMo cases and track `conv-26_qa_015` as judge/source-support risk without converting it into a failure.

The replay row should expose the path:

```text
indexed -> retrieved -> selected -> rendered -> cited -> judged
```

It should distinguish:

- source/retrieval metrics: indexed source status, retrieved ids, selected ids, rendered ids, source overlaps, session overlaps;
- answer/judge metrics: answer output, cited/source support, unsupported citations, refusal status, judge verdict/reasoning;
- classification: report-level failure class, path-level failure class, movement status, diagnostic notes.

## Risks

- Over-classification: the code may label a temporal or speaker/entity issue without enough evidence. Mitigation: emit `diagnostic_gap` plus notes instead of guessing.
- Metric mixing: `source_hit` could be treated as retrieval localization. Mitigation: replay schema must carry `source_hit_semantics = final_projection_source_overlap` and separate retrieval/selected/rendered overlaps.
- Case hiding: aggregate `30/50` or `47/50` could obscure the 20 LoCoMo failures. Mitigation: artifact gate must enumerate every required case id.
- Judge/source-support ambiguity: `conv-26_qa_015` passed but has citation/source-support risk. Mitigation: track it separately and do not inflate failure counts.
- Behavior drift: diagnostic helper could change report generation. Mitigation: no retrieval, answer, v1 fallback, v3 default, or kernel default changes are allowed in Phase 9 unless a RED diagnostic test proves existing rows cannot classify real cases.

## Demo-only Definition

Phase 9 would be demo-only if any of these are true:

- It produces artifacts from synthetic rows only and does not consume `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.
- It classifies only example cases instead of all 20 phase-8 LoCoMo failures.
- It reports aggregate pass/fail without per-case replay rows.
- It collapses required path classes into only `retrieval_miss` and `evidence_hit_answer_fail`.
- It hides `diagnostic_gap` cases or silently drops missing fields.
- It treats the passed `conv-26_qa_015` risk case as either a normal clean pass or an extra failure.
- It changes retrieval, answer projection, scoring, v1 fallback, v3 default, or kernel default to make diagnostics look better.
