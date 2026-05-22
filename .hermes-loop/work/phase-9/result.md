# phase: phase-9

# Phase 9 Result

Context bundle: `.hermes-loop/work/phase-9/context_bundle.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Summary

Implemented diagnostic-only Phase 9 failure replay support. No retrieval ranking,
answer prompting/projection, benchmark scoring, v1 fallback, v3 default, or kernel
default behavior was changed.

Source report consumed:
`.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

Invalid heartbeat retry artifacts were not used.

Final artifacts include explicit phase binding: Markdown artifacts start with
`# phase: phase-9`, and replay JSON rows include `"phase": "phase-9"`.

## Changed Files

- `src/memoryos_lite/public_failure_replay.py`
- `tests/test_public_failure_replay.py`
- `.hermes-loop/work/phase-9/failure_taxonomy.md`
- `.hermes-loop/work/phase-9/replay_schema.md`
- `.hermes-loop/work/phase-9/case_matrix.md`
- `.hermes-loop/work/phase-9/replay_cases/*.json`
- `.hermes-loop/work/phase-9/result.md`
- `.hermes-loop/work/phase-9/execute_review.md`

## RED

Command:

```bash
uv run pytest tests/test_public_failure_replay.py -q
```

Observed RED:

```text
ModuleNotFoundError: No module named 'memoryos_lite.public_failure_replay'
1 error in 0.25s
```

Additional phase-binding RED after review:

```text
AssertionError: Extra items in the left set: 'phase'
```

## GREEN

Commands:

```bash
uv run pytest tests/test_public_failure_replay.py -q
uv run pytest tests/test_diagnostic_report.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py -q
uv run ruff check .
```

Observed GREEN:

```text
5 passed in 0.86s
56 passed in 30.48s
All checks passed!
415 passed, 1 warning in 584.85s
validated phase bindings and 20 replay files
```

Review-lane local checks:

```text
5 passed in 0.87s
All checks passed!
```

## Replay Coverage

All 20 phase-8 LoCoMo failed cases have replay JSON artifacts under
`.hermes-loop/work/phase-9/replay_cases/`.

Path-level class distribution:

- `session_localization_miss`: 9
- `retrieval_miss`: 3
- `temporal_date_miss`: 4
- `evidence_rendered_answer_fails`: 3
- `refusal_despite_evidence`: 1

`conv-26_qa_015` is tracked separately as `judge_questionable` in
`.hermes-loop/work/phase-9/case_matrix.md`; it is not counted as a failed case
and no replay JSON was generated for it.

## Notes

`source_metrics` and `judge_metrics` are separate in every replay row.
`diagnostic_gap` remains an explicit class for missing or unclassifiable evidence,
not a hidden fallback.
