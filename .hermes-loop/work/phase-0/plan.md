# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Implementation Plan

This plan follows `.hermes-loop/work/phase-0/context_bundle.md`, `.hermes-loop/work/phase-0/brainstorm.md`, and `.hermes-loop/work/phase-0/god_dispatch.json`. It is TDD-oriented even though Phase 0 is expected to be no-code: start from RED evidence, verify diagnostics, add a failing test only if required diagnostics are missing, keep refactor as no-op, then smoke and review.

## File Boundary

Expected execute-lane writes:

- `.hermes-loop/work/phase-0/baseline_case_matrix.md`
- `.hermes-loop/work/phase-0/result.md`
- `.hermes-loop/work/phase-0/execute_review.md`
- generated `.memoryos/evals/phase0_*.json` reports

Do not modify `src/`, `tests/`, `docs/`, `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, review artifacts, or ACK artifacts unless diagnostics are proven missing and the plan explicitly enters the failing-test branch. Even then, production behavior optimization remains out of scope.

## Step 1: RED Evidence

- [ ] Re-read `.hermes-loop/work/phase-0/context_bundle.md`, `.hermes-loop/work/phase-0/brainstorm.md`, and `.hermes-loop/work/phase-0/god_dispatch.json`.
- [ ] Record the active goal exactly in `baseline_case_matrix.md`, `result.md`, and `execute_review.md`.
- [ ] Seed the matrix with the dispatch RED evidence:
  - LongMemEval evidence-hit answer fails: `e47becba`, `118b2229`, `51a45a95`.
  - LongMemEval retrieval miss: `58bf7951`.
  - LongMemEval pass: `1e043500`.
  - LoCoMo evidence-hit answer fail: `conv-26_qa_001`.
  - LoCoMo retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- [ ] Inspect data and existing report inputs:
  - `benchmarks/longmemeval/longmemeval.json`
  - `benchmarks/locomo/locomo10.json`
  - `.memoryos/evals/v3_lme_5case_longmemeval.json`
  - `.memoryos/evals/v3_locomo_5case_locomo.json`
  - `.memoryos/evals/v3_kernel_lme_5case_llmjudge_longmemeval.json`
  - `.memoryos/evals/v3_kernel_locomo_5case_llmjudge_locomo.json`

Acceptance: the current weak baseline is visible before any command rerun; no aggregate-only summary is used.

## Step 2: GREEN Verification Or Failing Test Branch

- [ ] Run the focused verification command exactly:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_public_benchmarks.py tests/test_context_composer.py tests/test_evals.py -q
```

- [ ] If this passes and existing/public reports expose required fields, continue without code changes.
- [ ] If required diagnostics are missing, do not patch production code first. Add one focused failing test that proves the missing field or unstable case ID, run it to confirm failure, and stop with `adjust` unless a later dispatch authorizes implementation.

Required diagnostic fields:

- `memory_arch`
- `v3_context`
- `v3_layer_counts`
- `v3_budget_decisions`
- `v3_diagnostics`
- `kernel_trace_events`

Acceptance: GREEN is either no-code verification of existing diagnostics or a confirmed failing test that explains why Phase 0 cannot ACK.

## Step 3: REFACTOR / No-Op

- [ ] Make no refactor if focused tests and diagnostics are usable.
- [ ] Confirm no behavior files were touched:
  - `src/`
  - `tests/`
  - `docs/`
  - `.hermes-loop/state.json`
  - `.hermes-loop/blueprint.md`
- [ ] If any unrelated worktree changes already exist, leave them untouched and do not attribute them to Phase 0.

Acceptance: refactor step is explicitly recorded as no-op unless the failing-test branch was required.

## Step 4: Smoke Commands

Run the dispatch commands exactly.

5-case LongMemEval v3 smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 5 --run-id phase0_v3_lme_5case --no-llm-answer --no-llm-judge
```

Inspect:

- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.partial.json` only if the command fails

5-case LoCoMo v3 smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --run-id phase0_v3_locomo_5case --no-llm-answer --no-llm-judge
```

Inspect:

- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.partial.json` only if the command fails

1-case opt-in kernel smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 1 --run-id phase0_v3_kernel_locomo_1case --no-llm-answer --no-llm-judge
```

Inspect:

- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json`
- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.partial.json` only if the command fails

Full checks before usable ACK:

```bash
uv run pytest -q
```

```bash
uv run ruff check .
```

Acceptance: each successful report has stable case IDs, separated benchmark rows, v3 diagnostics, and expected kernel trace absence/presence.

## Step 5: Baseline Matrix

- [ ] Create `.hermes-loop/work/phase-0/baseline_case_matrix.md`.
- [ ] Quote the active goal exactly.
- [ ] Cite `.hermes-loop/work/phase-0/context_bundle.md`, `.hermes-loop/work/phase-0/brainstorm.md`, and `.hermes-loop/work/phase-0/god_dispatch.json`.
- [ ] Add separate LongMemEval and LoCoMo tables.
- [ ] Classify every case with one taxonomy value from `spec.md`.
- [ ] Record command status, run ID, report path, `memory_arch`, v3 diagnostic field presence, and kernel trace status.
- [ ] Keep old RED evidence visible when refreshed results differ; label it as prior evidence, not current result.

Acceptance: later phases can diff the matrix case-by-case without re-reading aggregate reports.

## Step 6: Result Requirements

`result.md` must include:

- first line `# phase: phase-0`;
- the active goal quoted exactly;
- context bundle citation;
- commands run and pass/fail status;
- report paths inspected;
- baseline matrix path;
- default checks for v3, v1 fallback, and kernel opt-in;
- decision: `advance`, `repeat`, or `adjust`;
- if not `advance`, exact blockers and next repeat/adjust condition.

Do not write `result.md` until the execute lane actually runs the verification and smoke steps.

## Step 7: Execute Review Requirements

`execute_review.md` must include:

- first line `# phase: phase-0`;
- the active goal quoted exactly;
- context bundle citation;
- review against the usable ACK checklist in dispatch;
- explicit checks that LoCoMo failures are not hidden by LongMemEval results;
- explicit check that `source_hit` is not conflated with evidence localization;
- explicit check that no benchmark leakage or expected-answer shortcut was introduced;
- explicit check that `.hermes-loop/state.json` and `.hermes-loop/blueprint.md` were not modified by execution;
- explicit check that kernel traces are absent by default and present only under `MEMORYOS_AGENT_KERNEL=v1`;
- final review decision: `approve_ack`, `repeat`, or `adjust`.

Do not write ACK artifacts unless this review approves ACK.

## Step 8: Conditions For Repeat Or Adjust Instead Of ACK

Force `repeat` or `adjust` instead of ACK when any condition is true:

- focused tests fail without a recorded root cause;
- full `uv run pytest -q` or `uv run ruff check .` fails before usable ACK;
- any required report is missing or only a `.partial.json` exists;
- case IDs are unstable or absent;
- LongMemEval and LoCoMo are combined into aggregate-only reporting;
- any case lacks a taxonomy classification;
- `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, or `kernel_trace_events` cannot be inspected;
- kernel trace events appear without explicit `MEMORYOS_AGENT_KERNEL=v1`;
- v1 fallback or v3 default constraints are not verified;
- LoCoMo regressions are summarized away by LongMemEval pass/fail counts;
- optional 30-case LLM judge is skipped but the result claims full-chain milestone completion;
- any source, docs, blueprint, state, review, or ACK file is changed outside the allowed boundary;
- result or review does not quote the active goal exactly or does not cite the context bundle.

## Step 9: Review And ACK Gate

- [ ] Compare `baseline_case_matrix.md`, `result.md`, and `execute_review.md` against this plan and `spec.md`.
- [ ] Confirm the final decision matches the evidence.
- [ ] ACK only after review approves; otherwise repeat the smoke or adjust the diagnostics plan.
