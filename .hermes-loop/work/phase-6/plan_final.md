# phase: phase-6

# Final Plan: Answer Projection And Citation Contract

Context source: `.hermes-loop/work/phase-6/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## GOD_ADJUST Repeat Addendum

This plan was superseded by the documented Phase 6 GOD_ADJUST after the first repeat left `conv-26_qa_028` as a LoCoMo pass-to-fail retrieval/source blocker. The active repeat scope is recorded in:

- `.hermes-loop/work/phase-6/god_adjust_analysis.md`
- `.hermes-loop/work/phase-6/blueprint_amendment.md`
- `.hermes-loop/work/phase-6/result.md`

Additional allowed files for the repeat:

- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`

Additional RED tests for the repeat:

- `tests/test_public_benchmarks.py::test_public_benchmark_v3_preserves_locomo_neighbor_sources_for_answer_evidence`
- `tests/test_public_benchmarks.py::test_public_answerer_guides_yes_no_inference_before_refusal`
- `tests/test_public_benchmarks.py::test_answer_evidence_preserves_final_context_render_order`

The anti-demo gate remains unchanged: ACK requires real v3/public benchmark wiring, tests, case-level milestone evidence for LongMemEval and LoCoMo, no hidden pass-to-fail, and kernel default-off.

## Execution Scope

Implement the answer citation contract only in the real public benchmark answer boundary. Do not edit `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, docs, store, retrieval rewrites, or kernel defaults for this phase.

Allowed code/test files:

- `tests/test_public_benchmarks.py`
- `tests/test_agent_answer_eval.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/agent_answer_eval.py`

## RED

Add and run these tests before production edits:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_projected_answer_cites_selected_evidence -q
uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_flags_projected_unretrieved_citation -q
uv run pytest tests/test_public_benchmarks.py::test_public_answerer_renders_structured_evidence_with_citation_contract -q
```

Required RED test definitions:

- `test_public_benchmark_projected_answer_cites_selected_evidence`: one-case LoCoMo fixture, `memoryos_lite`, no LLM answer/judge, projected answer cites expected selected evidence as `[source_id]`, diagnostics report `supported_cited_answer`, no unsupported citation IDs.
- `test_public_case_diagnostics_flags_projected_unretrieved_citation`: direct diagnostics fixture where answer cites `[msg_unselected]` while rendered evidence is `["msg_selected"]`; diagnostics report `unsupported_citation_ids=["msg_unselected"]`, `citation_contract_status="unsupported_citation"`, and `failure_class="unsupported_answer"`.
- `test_public_answerer_renders_structured_evidence_with_citation_contract`: fake `ChatOpenAI`, structured evidence input with id/text/session/date/component, prompt contains allowed IDs, text, citation rule, and explicit refusal rule.

Add one extra focused test if not already covered:

- temporal LoCoMo/date-session grounding keeps date/session metadata in structured evidence rendering and the answerer prompt.

Expected RED: missing tests fail because projection omits citations, diagnostics lack citation-contract fields, and the answerer renders loose context.

## GREEN

1. Extend `AgentAnswerEvalResult` in `src/memoryos_lite/agent_answer_eval.py` append-only:
   - `missing_citation`
   - `explicit_no_evidence_refusal`
   - `citation_contract_status`

2. Keep existing fields and behavior. Compute status deterministically:
   - `no_evidence_refusal` for no rendered evidence plus refusal;
   - `supported_cited_answer` when all cited IDs are rendered;
   - `missing_citation` when rendered evidence exists but answer has no citation and is not a refusal;
   - `unsupported_citation` when any cited ID is not rendered;
   - `unsupported_answer` for factual no-evidence or remaining unsupported cases.

3. Update deterministic projection in `src/memoryos_lite/evals.py`:
   - projected clauses append sorted selected evidence citations as `[id]`;
   - no selected evidence returns `Insufficient retrieved evidence to answer with source citations.`;
   - retrieval/context metrics remain unchanged.

4. Add structured public evidence rendering in `src/memoryos_lite/public_benchmarks.py`:
   - build evidence from rendered `output.sources`;
   - attach optional component/session/date metadata from v3 final-context trace when available;
   - do not include dropped v3 diagnostics;
   - do not include expected answer text.

5. Change `PublicAnswerer.answer` to consume structured evidence. The system prompt must require exact `[id]` citations, forbid invented IDs, require refusal when insufficient, and preserve temporal/session reasoning from evidence metadata.

6. Extend `src/memoryos_lite/public_case_diagnostics.py` append-only:
   - mirror `missing_citation`, `explicit_no_evidence_refusal`, and `citation_contract_status`;
   - classify `missing_citation` and `unsupported_citation` as unsupported-answer failures;
   - keep retrieval miss, context missing evidence, and evidence-hit-answer-fail distinct.

7. Ensure partial and final public reports expose the same citation fields through `case_diagnostics` and top-level mirrors where already mirrored.

Run required tests after each minimal change until green.

## REFACTOR

Run:

```bash
uv run pytest tests/test_agent_answer_eval.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context -q
uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py -q
```

Refactor only for clarity:

- keep helpers local unless reuse is real;
- keep report fields append-only;
- avoid case-id and expected-answer rules;
- do not alter `MEMORYOS_MEMORY_ARCH` or `MEMORYOS_AGENT_KERNEL` defaults.

## Smoke

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Then run milestone full-chain LLM judge evals in parallel when provider access is available:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_lme_30_longmemeval.json \
  --run-id phase6_answer_contract_lme_30
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json \
  --run-id phase6_answer_contract_locomo_30
```

If provider access is unavailable, record the blocker and run deterministic fallback smoke only:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase6_answer_contract_lme_10_no_llm_fallback
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase6_answer_contract_locomo_10_no_llm_fallback
```

Do not treat fallback smoke as satisfying the milestone gate.

## Review And Result Requirements

The execute lane result must list:

- focused RED commands and failure evidence before production edits;
- GREEN/regression/full verification command outputs;
- LongMemEval and LoCoMo case movement separately;
- fail-to-pass and pass-to-fail lists, even when empty;
- unsupported citation, missing citation, no-evidence refusal, judge-questionable, retrieval miss, context missing evidence, and evidence-hit-answer-fail counts;
- source grounding movement without aggregate-only claims;
- v1 fallback status;
- v3 default status;
- kernel default-off status.

Completion language must stay conservative: this phase proves an answer citation contract is wired and diagnosable; it does not prove benchmark improvement unless the case-level milestone reports support that conclusion.
