# phase: phase-2

# Codex Review - Phase 2

Context bundle cited: `.hermes-loop/work/phase-2/context_bundle.md`. I read it first and reviewed this phase against its active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## 1. Verdict: PASS

The work is wired into the real `run_public_benchmark()` path, adds append-only case diagnostics, keeps LongMemEval and LoCoMo separated in the milestone reports, and preserves v1 fallback, v3 default routing, and kernel opt-in behavior. I do not see a blocking source-grounding regression or benchmark-overfitting issue in the reviewed diff.

## 2. Findings

### Non-blocking: passing rows can carry source-grounding failure classes

`build_case_diagnostics()` intentionally gives source-grounding taxonomy precedence over judge pass/fail: retrieval miss, context missing evidence, and unsupported answer are evaluated before a pass can become `supported_cited_answer` (`src/memoryos_lite/public_case_diagnostics.py:145-158`). The reports therefore include judge-passing rows whose `failure_class` is `unsupported_answer`, `context_missing_evidence`, or, for LoCoMo `conv-26_qa_028`, `retrieval_miss`.

This is acceptable for Phase 2 because `verdict`, `judge_status`, `answer_support_status`, and `failure_class` are separate report fields. It prevents judge-passing but uncited or ungrounded answers from being hidden as fully supported wins. God should not read `failure_class` as the judge outcome; it is a source-grounding diagnostic class.

### Non-blocking: `selected_context_ids` includes non-evidence task ids

`_selected_context_ids()` collects `item_id` from every v3 diagnostic and v3 context item (`src/memoryos_lite/public_case_diagnostics.py:161-176`). Current milestone reports show every row includes a `task_ses_*` id in `selected_context_ids`. This did not affect the current overlap decisions because expected evidence ids are message ids and `rendered_context_status` still catches missing rendered evidence, but future phases should restrict this field to included evidence-bearing items or `source_refs`.

### Non-blocking artifact hygiene

The active artifacts are phase-bound (`# phase: phase-2`) and use the context bundle content. `god_dispatch.json` explicitly points to the bundle (`.hermes-loop/work/phase-2/god_dispatch.json:5-7`). `result.md` cites the active goal and records the real chain, RED evidence, verification, and milestone reports (`.hermes-loop/work/phase-2/result.md:5-34`, `.hermes-loop/work/phase-2/result.md:83-143`), but `plan_final.md`, `result.md`, and `execute_review.md` do not explicitly name `context_bundle.md`. I do not consider this blocking because the scope, non-goals, and evidence match the bundle, but ACK should cite the bundle explicitly.

## 3. Evidence Checked

Fresh reviewer verification:

- `uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py tests/test_llm_judge.py -q` -> `33 passed in 41.27s`
- `uv run ruff check .` -> `All checks passed!`
- `uv run pytest -q` -> `366 passed, 1 warning in 547.28s`

Executor-recorded and reviewer-checked milestone reports:

- LongMemEval: `.memoryos/evals/public_20260521_213550_longmemeval.json`
  - 30 rows, 18 pass, 12 fail.
  - `failure_class`: `context_missing_evidence=12`, `unsupported_answer=15`, `retrieval_miss=3`.
  - Representative ids: `e47becba` as context missing evidence; `51a45a95` as unsupported answer; `58bf7951` as retrieval miss; `37d43f65` as judge pass but unsupported due missing citation.
- LoCoMo: `.memoryos/evals/public_20260521_214906_locomo.json`
  - 30 rows, 7 pass, 23 fail.
  - `failure_class`: `unsupported_answer=9`, `retrieval_miss=11`, `context_missing_evidence=10`.
  - Representative ids: `conv-26_qa_001` as `fail_to_pass` plus unsupported answer; `conv-26_qa_002` as unchanged retrieval miss; `conv-26_qa_028` as judge pass with retrieval miss; `conv-26_qa_030` as context missing evidence.

Code and behavior checks:

- Real public path wiring: `run_public_benchmark()` loads comparison movement and passes diagnostics into `_to_public_result()` (`src/memoryos_lite/public_benchmarks.py:140-153`, `src/memoryos_lite/public_benchmarks.py:245-267`, `src/memoryos_lite/public_benchmarks.py:605-725`).
- Append-only report compatibility: new dataclass fields are defaults and `to_report()` still emits legacy fields plus `pass` (`src/memoryos_lite/public_benchmarks.py:37-121`).
- v3 default preserved: `Settings.memoryos_memory_arch` defaults to `v3` (`src/memoryos_lite/config.py:29`) and `_should_route_to_v3_context()` routes when resolved arch is `v3` (`src/memoryos_lite/engine.py:2107-2108`).
- v1 fallback preserved: explicit `memoryos_memory_arch="v1"` remains valid (`src/memoryos_lite/config.py:67-71`) and is covered by public benchmark tests (`tests/test_public_benchmarks.py:1002-1019`).
- Kernel default unchanged: `Settings.memoryos_agent_kernel` defaults to `off` (`src/memoryos_lite/config.py:30`), `MemoryOSService` only constructs the kernel when resolved kernel is `v1` (`src/memoryos_lite/engine.py:1489-1505`), and default public reports assert no kernel trace (`tests/test_public_benchmarks.py:1022-1038`).
- Prompt-hack risk: no hard-coded public benchmark case ids were found in `src/`; public benchmark ids are loaded generically from `question_id`, `sample_id`, and evidence fields.

## 4. ACK Recommendation

Recommendation: advance.

Suggested ACK level: usable.

Rationale: Phase 2 is diagnostic-only but meets the anti-demo bar for a diagnostic evidence harness: real v3/public benchmark path wiring, RED/GREEN tests, full-chain 30-case LongMemEval and LoCoMo report evidence, separate case-level taxonomy, source-hit semantics separated from evidence localization, and no default kernel enablement. The remaining gaps are future implementation work, not blockers for ACK of this phase.

```json
{
  "review_verdict_payload": {
    "phase": "phase-2",
    "active_goal": "Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.",
    "verdict": "PASS",
    "overfitting_risk": "low",
    "v1_fallback_preserved": true,
    "v3_default_preserved": true,
    "kernel_default_unchanged": true,
    "source_grounding_regressed": false,
    "locomo_regressed_or_unexplained": false,
    "blocking_issues": [],
    "ack_level_recommendation": "advance"
  }
}
```
