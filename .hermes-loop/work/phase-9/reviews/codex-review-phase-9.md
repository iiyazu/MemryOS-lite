# phase: phase-9

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Verdict

PASS. Recommended ack level: `usable`.

## Findings

No blockers found in the final phase-binding re-review.

## Review Evidence

- Required read order honored: `.hermes-loop/work/phase-9/context_bundle.md` was read before `god_dispatch.json`, `plan_final.md`, `result.md`, `execute_review.md`, existing `review_verdict.json`, implementation, tests, taxonomy, schema, matrix, replay JSON, and git status/diff.
- All checked phase-9 Markdown artifacts, including this review file, begin with `# phase: phase-9`.
- `review_verdict.json` contains `"phase": "phase-9"`.
- All 20 replay JSON rows contain `"phase": "phase-9"`.
- Replay JSON files are exactly the 20 failed phase-8 LoCoMo cases. `conv-26_qa_015` is tracked separately in `case_matrix.md` as `judge_questionable` and is not emitted as replay JSON.
- `src/memoryos_lite/public_failure_replay.py` is diagnostic-only: no retrieval ranking, answer projection/prompting, scoring, v1 fallback, v3 default, or kernel default behavior changes were found.
- Constants for phase-8 failed ids are used for phase coverage and validation, not answer behavior.
- `source_metrics`, `judge_metrics`, and `source_hit_semantics = final_projection_source_overlap_not_retrieval_localization` keep source/retrieval accounting separate from judged answer quality.
- Replay JSON rows do not contain `expected_answer`, `gold_answer`, `reference_answer`, `ground_truth`, or `target_answer` fields.
- No aggregate score improvement claim was found in the reviewed phase-9 result path.
- Workspace status still includes unrelated tracked dirt in `.hermes-loop/blueprint.md`, `AGENTS.md`, and `CLAUDE.md`; those files are outside this review and were not modified.

## Final Verification Evidence

God-side final verification after the phase-binding patch:

```text
RED: uv run pytest tests/test_public_failure_replay.py::test_real_phase8_failed_row_builds_complete_replay_row -q -> failed because 'phase' field was missing
uv run pytest tests/test_public_failure_replay.py -q -> 5 passed in 0.86s
uv run pytest tests/test_diagnostic_report.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py -q -> 56 passed in 30.48s
uv run ruff check . -> All checks passed!
uv run pytest -q -> 415 passed, 1 warning in 584.85s
artifact/phase-binding validator -> validated phase bindings and 20 replay files
```

Read-only review checks performed here:

```text
20 replay JSON files found
all replay JSON phases: phase-9
conv-26_qa_015 replay JSON present: false
all replay JSON judge verdicts: fail
gold/expected-answer-like replay JSON fields: none
source/judge metric separation: true
```

## Residual Risk

Path-level classes remain report-derived and conservative. Schema-supported classes that do not appear in the phase-8 LoCoMo failed-case distribution should not be interpreted as newly improved answer behavior.
