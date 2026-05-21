# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Sources

- `.hermes-loop/work/phase-0/context_bundle.md`: defines Phase 0 as a baseline freeze and case harness over the real v3 public benchmark path, with no behavior optimization.
- `.hermes-loop/work/phase-0/brainstorm.md`: recommends the fresh deterministic freeze route: focused tests, refreshed 5-case no-LLM public smoke, one explicit opt-in kernel smoke, then a per-case matrix.
- `.hermes-loop/work/phase-0/god_dispatch.json`: provides the exact verification commands, red evidence, usable ACK checklist, and review focus.

## Baseline Freeze Contract

Phase 0 freezes the current benchmark-visible baseline before later behavior changes. It must prove that current reports expose enough case-level diagnostics to compare future LongMemEval and LoCoMo changes without hiding regressions.

The frozen path is:

```text
public benchmark -> MemoryOSService.ingest/build_context -> v3 ContextComposer -> PublicBenchmarkResult diagnostics
```

Contract requirements:

- LongMemEval and LoCoMo must be reported separately.
- Every smoke case must have a stable case ID and an explicit per-case classification.
- Aggregate pass rate is secondary; it cannot replace case rows.
- `source_hit` / `source_accuracy` must not be treated as pure evidence localization without supporting episode/planned/context diagnostics.
- `MEMORYOS_MEMORY_ARCH=v3` is the v3 public smoke setting; `MEMORYOS_MEMORY_ARCH=v1` fallback must remain available.
- `MEMORYOS_AGENT_KERNEL=v1` is opt-in only; kernel trace evidence is valid only when the command explicitly sets that environment variable.
- Phase 0 must not claim retrieval, context composer, answer prompt, or kernel improvement.
- Missing diagnostics require repeat/adjust, or a focused failing test before production code changes.

## Artifacts

This PLAN_DRAFT task creates only:

- `.hermes-loop/work/phase-0/spec.md`
- `.hermes-loop/work/phase-0/plan.md`

The later execute lane is expected to create or refresh:

- `.hermes-loop/work/phase-0/baseline_case_matrix.md`
- `.hermes-loop/work/phase-0/result.md`
- `.hermes-loop/work/phase-0/execute_review.md`
- review and ACK artifacts only after review passes
- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`
- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json`
- matching `.partial.json` files only as failed-run evidence, never as successful baseline artifacts

## Allowed Writes

For this PLAN_DRAFT dispatch, allowed writes are limited to the two Markdown files named above.

For the later execute lane, allowed writes are limited to phase-local evidence artifacts, generated eval reports, and a focused failing test only if a required diagnostic is absent and cannot be verified from existing tests. Production code changes are not expected in Phase 0.

Forbidden writes for Phase 0 unless a later dispatch explicitly changes scope:

- `src/`
- non-focused `tests/` changes
- `docs/`
- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- benchmark data files
- prompt-only or report-only edits that claim architecture progress
- any change that enables the v3 kernel by default

## Non-Goals

- No retrieval optimization.
- No context composer behavior optimization.
- No answer prompt optimization.
- No kernel-loop behavior optimization.
- No Letta runtime dependency.
- No case-id hack, expected-answer leak, or benchmark-specific shortcut.
- No state promotion from plan text alone.
- No ACK if diagnostics, tests, or case rows are missing.

## Baseline Case Matrix Shape

`baseline_case_matrix.md` must start with the active goal quoted exactly and cite `.hermes-loop/work/phase-0/context_bundle.md`.

Required sections:

- `Source Inputs`: context bundle, brainstorm, dispatch, benchmark data paths, and report paths.
- `Run Summary`: command, run ID, benchmark, limit, LLM answer/judge mode, report path, result count, and command status.
- `Default And Opt-In Checks`: `memory_arch`, v1 fallback evidence, default kernel absence, explicit opt-in kernel trace presence.
- `LongMemEval Cases`: one row per refreshed LongMemEval smoke case.
- `LoCoMo Cases`: one row per refreshed LoCoMo smoke case.
- `Diagnostic Gaps`: any missing fields, partial reports, unstable IDs, or blocked commands.
- `Decision`: `advance`, `repeat`, or `adjust`, with evidence.

Required case-row columns:

| Column | Meaning |
|---|---|
| `benchmark` | `longmemeval` or `locomo`. |
| `run_id` | Exact run ID used in the command. |
| `report_path` | Generated `.memoryos/evals/*.json` path. |
| `case_id` | Stable case ID from the report. |
| `result` | Pass/fail/projected or judged status from the report. |
| `taxonomy` | One failure taxonomy value. |
| `retrieval_evidence` | Episode/planned/retrieved evidence hit or miss, with field names. |
| `context_evidence` | Whether selected context contains the needed evidence, if reported. |
| `answer_status` | Correct, unsupported, overconfident, exact-match fail, or judge issue. |
| `v3_diagnostics` | Presence of `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics`. |
| `kernel_trace` | `absent_by_default`, `present_opt_in`, or `unexpected`. |
| `notes` | Short source-grounded explanation; no aggregate-only claim. |

## Failure Taxonomy

Use exactly one primary taxonomy value per case:

- `pass`: case passed under the report's stated scoring mode.
- `retrieval_miss`: no useful episode/planned/retrieved evidence reached the diagnostic path.
- `evidence_hit_answer_fail`: evidence was found, but the projected or judged answer failed.
- `context_missing_evidence`: retrieval had evidence, but selected context or answer context did not carry it.
- `answer_unsupported_overconfident`: answer claims more than the evidence supports.
- `judge_questionable`: judge or exact-match behavior is suspect and requires manual inspection.
- `diagnostic_gap`: report lacks fields needed to classify the case.
- `run_blocked`: command did not produce a usable report.

## ACK Boundary

Phase 0 can only ACK at usable level when:

- focused tests pass;
- full `uv run pytest -q` and `uv run ruff check .` pass before ACK;
- refreshed LongMemEval and LoCoMo case rows exist separately;
- report fields include `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events`;
- v1 fallback, v3 default, and kernel opt-in constraints are verified;
- `result.md` and `execute_review.md` cite the active goal and context bundle;
- review finds no demo-only completion, hidden regression, benchmark leakage, default-kernel enablement, or missing diagnostic gap.
