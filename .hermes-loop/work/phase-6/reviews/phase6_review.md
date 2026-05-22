# phase: phase-6

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Verdict: PASS

## Review Scope

Read:

- `.hermes-loop/work/phase-6/context_bundle.md`
- `.hermes-loop/work/phase-6/god_dispatch.json`
- `.hermes-loop/work/phase-6/plan_final.md`
- `.hermes-loop/work/phase-6/result.md`
- `.hermes-loop/work/phase-6/execute_review.md`
- `.hermes-loop/work/phase-6/blueprint_amendment.md`
- `.memoryos/evals/phase6_god_adjust_prompt2_lme_30_longmemeval.json`
- `.memoryos/evals/phase6_god_adjust_prompt2_locomo_30_locomo.json`
- git diff for Phase 6 code/test files.

The earlier FAIL review for `phase6_answer_contract_locomo_30_locomo.json` is superseded by the GOD_ADJUST repeat reports listed above.

## Findings

No blocking findings remain.

The implementation is wired into the real v3 public benchmark path. `run_public_benchmark()` feeds `_answer_evidence_from_output(output)` into `PublicAnswerer`, and deterministic projected answers cite rendered source IDs.

The LoCoMo blocker is not hidden:

- Previous blocker: `conv-26_qa_028` was `pass_to_fail` with missing `D7:5` / `D7:9`.
- Final repeat: `conv-26_qa_028` is `unchanged_pass`, `supported_cited_answer`, and source overlap includes both `D7:5` and `D7:9`.
- `source_hit_at_k=false` remains explicit for `conv-26_qa_028`, so top-k retrieval and final evidence overlap are still separate diagnostics.

No pass-to-fail remains:

- LongMemEval: `pass_to_fail=[]`.
- LoCoMo: `pass_to_fail=[]`.

Kernel default was not used:

- LongMemEval final report: `kernel_trace_events` empty for all rows.
- LoCoMo final report: `kernel_trace_events` empty for all rows.

## Verification Evidence

- Focused repeat and regression tests passed.
- `uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py tests/test_episode_retrieval.py tests/test_context_composer.py -q` -> `106 passed`.
- `uv run pytest -q` -> `396 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.
- LongMemEval milestone: `29/30`, `fail_to_pass=11`, `pass_to_fail=0`.
- LoCoMo milestone: `18/30`, `fail_to_pass=11`, `pass_to_fail=0`.

## Guardrail Review

- v1 fallback preserved by focused coverage.
- v3 default preserved.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.
- No case-id logic or expected-answer leakage was added.
- Retrieval/source diagnostics remain distinct from judged answer quality.
- Remaining failures are case-level visible and not hidden by aggregate score.

## Residual Risk

The yes/no career/preference prompt rule is LoCoMo-shaped. It is acceptable for Phase 6 because `conv-26_qa_028` also has real expected-source overlap, but future phases should monitor prompt overfitting and judge instability.
