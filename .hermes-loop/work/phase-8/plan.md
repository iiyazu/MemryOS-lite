# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Plan Contract

Controlling context: `work/phase-8/context_bundle.md`.

This is a decision-only Phase 8 plan. Do not edit source code, tests, active docs, or `.hermes-loop/state.json` unless a focused RED test first proves a diagnostic implementation fix is required. Preserve:

- v1 fallback via `MEMORYOS_MEMORY_ARCH=v1`;
- v3 default memory architecture;
- v3 kernel opt-in only via `MEMORYOS_AGENT_KERNEL=v1`.

All commands below are for the EXECUTE lane. This PLAN_DRAFT lane must not run long benchmark commands.

## Files And Artifacts

Create or update during execution:

- `work/phase-8/logs/focused_guard.log`
- `work/phase-8/logs/full_pytest.log`
- `work/phase-8/logs/ruff.log`
- `work/phase-8/logs/phase8_lme50_<timestamp>.log`
- `work/phase-8/logs/phase8_locomo50_<timestamp>.log`
- `work/phase-8/reports/phase8_lme50_<timestamp>.paths.txt`
- `work/phase-8/reports/phase8_locomo50_<timestamp>.paths.txt`
- `work/phase-8/promotion_decision.md`
- `work/phase-8/result.md`
- `work/phase-8/execute_review.md`
- `work/phase-8/review_verdict.json`
- `work/phase-8/ack.json` only if the usable ACK gate passes

If the gate fails, create adjustment artifacts instead of a promotional ACK:

- `work/phase-8/adjustment.md`
- `work/phase-8/review_verdict.json`
- `work/phase-8/result.md`

## RED: Evidence Missing Or Stale

For decision-only work, RED is not a code failure. RED is the current absence of fresh Phase 8 evidence and the presence of stale Phase 8 artifacts that do not cite `work/phase-8/context_bundle.md`.

- [ ] Confirm `work/phase-8/context_bundle.md` is cited as controlling context in new Phase 8 artifacts.
- [ ] Mark old `work/phase-8/research.md` and `work/phase-8/reviews/codex-review.md` stale unless superseded by fresh outputs that cite the bundle.
- [ ] Create log/report directories before running verification:

```bash
mkdir -p .hermes-loop/work/phase-8/logs .hermes-loop/work/phase-8/reports
```

- [ ] Establish unique run ids:

```bash
PHASE8_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LME_RUN_ID="phase8_lme50_${PHASE8_TS}"
LOCOMO_RUN_ID="phase8_locomo50_${PHASE8_TS}"
printf 'LME_RUN_ID=%s\nLOCOMO_RUN_ID=%s\n' "$LME_RUN_ID" "$LOCOMO_RUN_ID" | tee .hermes-loop/work/phase-8/reports/run_ids.txt
```

No production implementation may start from this RED condition. Implementation is allowed only if a focused failing test is added first and the failure blocks a valid diagnostic decision.

## GREEN: Verification And Fresh Evidence

- [ ] Run the focused kernel/default guard and capture the log:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q 2>&1 | tee .hermes-loop/work/phase-8/logs/focused_guard.log
```

Expected: pass. If it fails, stop promotion work and produce `adjustment.md` unless a focused failing test and minimal diagnostic fix are approved by the evidence contract.

- [ ] Run full pytest and capture the log:

```bash
uv run pytest -q 2>&1 | tee .hermes-loop/work/phase-8/logs/full_pytest.log
```

Expected: pass.

- [ ] Run ruff and capture the log:

```bash
uv run ruff check . 2>&1 | tee .hermes-loop/work/phase-8/logs/ruff.log
```

Expected: pass.

- [ ] Run LongMemEval and LoCoMo milestone evals in parallel with explicit v3 memory architecture and no kernel env var:

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

Expected: both commands exit 0. If LLM answer/judge access fails, record the exact failure and do not recommend `expand_eval` or `promote_blueprint`.

- [ ] Capture generated report paths without assuming a fixed output directory:

```bash
find . -type f \( -name "*${LME_RUN_ID}*" -o -name "*${LOCOMO_RUN_ID}*" \) | sort | tee .hermes-loop/work/phase-8/reports/generated_report_paths.txt
grep -R "$LME_RUN_ID" . -n --exclude-dir=.git | tee ".hermes-loop/work/phase-8/reports/${LME_RUN_ID}.paths.txt"
grep -R "$LOCOMO_RUN_ID" . -n --exclude-dir=.git | tee ".hermes-loop/work/phase-8/reports/${LOCOMO_RUN_ID}.paths.txt"
```

Expected: each run id has at least one log path and any generated report paths produced by the CLI.

## REFACTOR: Case-Level Decision Analysis

No source refactor is expected. This step refactors raw evidence into decision artifacts.

- [ ] Produce `work/phase-8/promotion_decision.md` with:
  - first line `# phase: phase-8`;
  - active goal verbatim;
  - `work/phase-8/context_bundle.md` citation;
  - exact run ids, command logs, and report paths;
  - one decision: `continue_targeted`, `expand_eval`, `hold`, or `promote_blueprint`;
  - LongMemEval case groups: pass, fail, fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence hit but context missing, evidence hit but answer fail, unsupported answer, judge questionable, source-grounding movement;
  - LoCoMo case groups with the same categories plus local-cap note and conversation/temporal/speaker/multi-hop clustering;
  - explicit statement that promotion evals did not set `MEMORYOS_AGENT_KERNEL=v1`;
  - explicit statement that aggregate score alone is not the decision basis.

- [ ] If same-subset Phase 0 movement cannot be computed from available reports, state the missing baseline and avoid inventing fail-to-pass or pass-to-fail movement.

- [ ] If deterministic fallback is needed, label it non-promotional in `promotion_decision.md` and choose `continue_targeted` or `hold`.

## Smoke: Artifact Completeness

- [ ] Produce `work/phase-8/result.md` with:
  - first line `# phase: phase-8`;
  - active goal verbatim;
  - controlling context citation;
  - verification command outcomes;
  - eval run ids and statuses;
  - decision summary;
  - blocker summary if any;
  - statement that no source code, tests, active docs, or `state.json` were edited unless a focused RED test forced a diagnostic fix.

- [ ] Produce `work/phase-8/execute_review.md` with:
  - first line `# phase: phase-8`;
  - active goal verbatim;
  - review of evidence freshness, stale artifact replacement, source grounding, LoCoMo risks, kernel opt-in preservation, and aggregate-only risk.

- [ ] Produce `work/phase-8/review_verdict.json` with this shape:

```json
{
  "phase": "phase-8",
  "active_goal": "Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.",
  "context_bundle": "work/phase-8/context_bundle.md",
  "verdict": "usable_ack|adjustment_required",
  "decision": "continue_targeted|expand_eval|hold|promote_blueprint",
  "fresh_evidence": true,
  "longmemeval_analyzed": true,
  "locomo_analyzed": true,
  "pass_to_fail_explicit": true,
  "source_grounding_checked": true,
  "kernel_default_preserved": true,
  "promotion_eval_used_kernel": false,
  "aggregate_only_decision": false,
  "non_promotional_fallback": false,
  "blocking_issues": []
}
```

- [ ] Produce `work/phase-8/ack.json` only when `review_verdict.json.verdict` is `usable_ack` and both benchmarks have usable fresh evidence:

```json
{
  "phase": "phase-8",
  "active_goal": "Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.",
  "context_bundle": "work/phase-8/context_bundle.md",
  "decision": "continue_targeted|expand_eval|hold|promote_blueprint",
  "promotion_decision": "work/phase-8/promotion_decision.md",
  "result": "work/phase-8/result.md",
  "execute_review": "work/phase-8/execute_review.md",
  "review_verdict": "work/phase-8/review_verdict.json",
  "kernel_default_preserved": true,
  "source_grounding_checked": true,
  "case_level_regressions_hidden": false
}
```

- [ ] If the usable ACK gate fails, do not write promotional `ack.json`. Produce `work/phase-8/adjustment.md` with the exact blocker, next proposed target, and why fallback evidence is non-promotional.

## Review Gate

Before finalizing, verify:

- [ ] Every Phase 8 completion artifact cites `work/phase-8/context_bundle.md`.
- [ ] Every Phase 8 completion artifact cites the active goal verbatim.
- [ ] `MEMORYOS_AGENT_KERNEL=v1` is absent from promotion eval commands and logs unless explicitly marked as a separate diagnostic.
- [ ] Pass-to-fail cases are listed explicitly, even if empty.
- [ ] Source-grounding movement is separated from judged answer quality.
- [ ] LoCoMo is analyzed independently and cannot be masked by LongMemEval.
- [ ] No source code, tests, active docs, or `.hermes-loop/state.json` were edited in the decision-only path.
- [ ] `ack.json` exists only if `review_verdict.json` says `usable_ack`.
