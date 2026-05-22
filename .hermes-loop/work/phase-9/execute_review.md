# phase: phase-9

# Phase 9 Execute Review

Context bundle: `.hermes-loop/work/phase-9/context_bundle.md`.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Review Checklist

- Context bundle was read before `plan_final.md`, `god_dispatch.json`, and
  `research.md`.
- Real source report consumed:
  `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.
- Invalid heartbeat retry artifacts were ignored.
- All 20 phase-8 LoCoMo failed cases are classified.
- `conv-26_qa_015` is tracked as judge/source-support risk only.
- Source/retrieval metrics are separated from answer/judge metrics.
- `diagnostic_gap` is explicit and not hidden.
- Markdown artifacts start with `# phase: phase-9`, and replay JSON rows include
  `"phase": "phase-9"`.
- No score-improvement claim is made.
- No retrieval ranking, answer projection/prompting, benchmark scoring, v1
  fallback, v3 default, or kernel default code was changed.
- `review_verdict.json` was written by review lane with `verdict=PASS`.
- No `ack.json` was written.

## Verification

RED command:

```bash
uv run pytest tests/test_public_failure_replay.py -q
```

RED output summary:

```text
ModuleNotFoundError: No module named 'memoryos_lite.public_failure_replay'
1 error in 0.25s
```

Phase-binding RED output summary:

```text
AssertionError: Extra items in the left set: 'phase'
```

GREEN commands:

```bash
uv run pytest tests/test_public_failure_replay.py -q
uv run pytest tests/test_diagnostic_report.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py -q
uv run ruff check .
uv run pytest -q
```

GREEN output summary:

```text
5 passed in 0.86s
56 passed in 30.48s
All checks passed!
415 passed, 1 warning in 584.85s
validated phase bindings and 20 replay files
```

## Residual Risk

Path-level classes are conservative and report-derived. Some narrower classes
such as speaker/entity confusion remain schema-supported but absent from the
phase-8 LoCoMo failed-case distribution because the consumed report rows did not
deterministically support that narrower class.
