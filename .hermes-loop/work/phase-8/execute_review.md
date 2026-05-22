# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context: `work/phase-8/context_bundle.md`.

## Execute Self-Review

Real chain changed:

- Public benchmark behavior: verified, not changed.
- v3 context path: verified by 50-case LongMemEval and LoCoMo reports with `memory_arch = v3`.
- Kernel loop: verified default-off by focused guard and empty `kernel_trace_events` in milestone reports.
- Reliability diagnostics: changed in `.hermes-loop/hermes_hardening.py` to count `movement_status` from real eval reports.

Still demo-only or partial:

- No demo-only completion is being claimed.
- The later heartbeat retry run remained partial/projected/no-judge and is explicitly excluded from promotion evidence.
- LoCoMo remains partial from a benchmark-usability perspective: `20/50` failed, with retrieval miss and evidence-hit-answer-fail clusters.

Tests and verification:

- RED: `uv run pytest tests/test_hermes_hardening.py::test_summarize_eval_report_counts_real_movement_status_field -q` failed because real `movement_status` values were not counted.
- GREEN: `uv run pytest tests/test_hermes_hardening.py -q` passed with `10 passed`.
- Focused kernel/default guard passed with `3 passed`.
- Full pytest passed with `410 passed, 1 warning`.
- Ruff passed.

Benchmark movement:

- LongMemEval: `47/50`, no pass-to-fail, no fail-to-pass, one unchanged fail (`51a45a95`), two new failures (`b86304ba`, `ccb36322`).
- LoCoMo: `30/50`, no pass-to-fail, no fail-to-pass, twelve unchanged fails, eight new failures.

Fallback/default constraints:

- `MEMORYOS_MEMORY_ARCH=v1` fallback was not removed or modified.
- v3 default was preserved.
- `MEMORYOS_AGENT_KERNEL=v1` was not used in the promotion evals and was not made default.

Controller judgment:

- ACK may be usable for the phase-8 decision gate if review agrees that the current artifacts satisfy active-goal alignment and do not hide LoCoMo weakness.
- The phase decision should be `continue_targeted`, not `expand_eval`.
