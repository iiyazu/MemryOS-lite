# phase: phase-8

## Active Goal

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Controlling Context

Use `work/phase-8/context_bundle.md` as the controlling context. Treat older `work/phase-8/research.md` and `work/phase-8/reviews/codex-review.md` as stale unless superseded by fresh outputs that cite `work/phase-8/context_bundle.md`.

This is a decision-only plan unless a focused RED test proves a diagnostic implementation fix is required. Preserve `MEMORYOS_MEMORY_ARCH=v1` fallback, v3 as the default memory architecture, and v3 kernel opt-in only via `MEMORYOS_AGENT_KERNEL=v1`.

## RED

Confirm the current RED condition: fresh Phase 8 evidence is missing, and stale Phase 8 artifacts cannot support completion.

```bash
mkdir -p .hermes-loop/work/phase-8/logs .hermes-loop/work/phase-8/reports
PHASE8_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LME_RUN_ID="phase8_lme50_${PHASE8_TS}"
LOCOMO_RUN_ID="phase8_locomo50_${PHASE8_TS}"
printf 'LME_RUN_ID=%s\nLOCOMO_RUN_ID=%s\n' "$LME_RUN_ID" "$LOCOMO_RUN_ID" | tee .hermes-loop/work/phase-8/reports/run_ids.txt
```

Do not edit source code, tests, active docs, or `.hermes-loop/state.json` from this RED state.

## GREEN

Run the focused guard, full tests, and lint:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q 2>&1 | tee .hermes-loop/work/phase-8/logs/focused_guard.log
uv run pytest -q 2>&1 | tee .hermes-loop/work/phase-8/logs/full_pytest.log
uv run ruff check . 2>&1 | tee .hermes-loop/work/phase-8/logs/ruff.log
```

Run LongMemEval and LoCoMo milestone evals in parallel with unique run ids, explicit v3 memory architecture, and no `MEMORYOS_AGENT_KERNEL=v1`:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 50 --run-id "$LME_RUN_ID" 2>&1 | tee ".hermes-loop/work/phase-8/logs/${LME_RUN_ID}.log" &
LME_PID=$!
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 50 --run-id "$LOCOMO_RUN_ID" 2>&1 | tee ".hermes-loop/work/phase-8/logs/${LOCOMO_RUN_ID}.log" &
LOCOMO_PID=$!
wait "$LME_PID"
LME_STATUS=$?
wait "$LOCOMO_PID"
LOCOMO_STATUS=$?
printf 'LongMemEval status=%s\nLoCoMo status=%s\n' "$LME_STATUS" "$LOCOMO_STATUS" | tee .hermes-loop/work/phase-8/logs/eval_status.log
test "$LME_STATUS" -eq 0
test "$LOCOMO_STATUS" -eq 0
```

Capture generated paths:

```bash
find . -type f \( -name "*${LME_RUN_ID}*" -o -name "*${LOCOMO_RUN_ID}*" \) | sort | tee .hermes-loop/work/phase-8/reports/generated_report_paths.txt
grep -R "$LME_RUN_ID" . -n --exclude-dir=.git | tee ".hermes-loop/work/phase-8/reports/${LME_RUN_ID}.paths.txt"
grep -R "$LOCOMO_RUN_ID" . -n --exclude-dir=.git | tee ".hermes-loop/work/phase-8/reports/${LOCOMO_RUN_ID}.paths.txt"
```

If LLM answer/judge access fails, record the exact command, run id, log path, timestamp, and failure text. Optional no-LLM diagnostics are non-promotional and can support only `continue_targeted` or `hold`.

## REFACTOR

Turn raw evidence into `work/phase-8/promotion_decision.md` with first line `# phase: phase-8`. Include the active goal verbatim, cite `work/phase-8/context_bundle.md`, list exact run ids/logs/report paths, and select exactly one decision: `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`.

Analyze LongMemEval and LoCoMo separately. For each benchmark, include pass, fail, fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence hit but context missing, evidence hit but answer fail, unsupported answer, judge questionable, and source-grounding movement. For LoCoMo, also note the local cap and whether failures cluster around conversation, temporal, speaker, or multi-hop memory behavior.

Do not recommend from aggregate score alone. If same-subset Phase 0 movement cannot be computed, say so explicitly and do not invent movement groups.

## Smoke

Produce:

- `work/phase-8/result.md`
- `work/phase-8/execute_review.md`
- `work/phase-8/review_verdict.json`
- `work/phase-8/ack.json` only when the usable ACK gate passes
- `work/phase-8/adjustment.md` instead of promotional ACK when the gate fails

Every Markdown artifact must start with `# phase: phase-8`, cite the active goal verbatim, and cite `work/phase-8/context_bundle.md`.

## Review

Before finalizing, verify:

- LongMemEval and LoCoMo both have fresh Phase 8 evidence or an exact provider blocker.
- Pass-to-fail cases are explicit, even if empty.
- Source-grounding movement is separate from judged answer quality.
- LoCoMo weakness is not hidden by LongMemEval.
- Promotion eval commands and logs did not set `MEMORYOS_AGENT_KERNEL=v1`.
- No source code, tests, active docs, or `.hermes-loop/state.json` were edited in the decision-only path.
- `ack.json` exists only if `review_verdict.json.verdict` is `usable_ack`.
