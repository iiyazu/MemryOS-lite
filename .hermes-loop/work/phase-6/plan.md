# phase: phase-6

# Plan: Answer Projection And Citation Contract

Context source: `.hermes-loop/work/phase-6/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Files

- Modify: `tests/test_public_benchmarks.py`
- Modify: `tests/test_agent_answer_eval.py`
- Modify: `src/memoryos_lite/evals.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`
- Modify: `src/memoryos_lite/public_case_diagnostics.py`
- Modify: `src/memoryos_lite/agent_answer_eval.py`

Do not modify store, retrieval, v3 kernel defaults, blueprint, state, or docs in this phase unless a focused RED test proves the answer contract cannot be wired otherwise.

## RED

1. Add `test_public_benchmark_projected_answer_cites_selected_evidence` in `tests/test_public_benchmarks.py`.
   - Build a one-case LoCoMo fixture.
   - Run `run_public_benchmark(... baselines=["memoryos_lite"], llm_answer=False, llm_judge=False)`.
   - Assert answer contains the expected source ID as `[sample_id_qa_001:sample_id:D1:1]`.
   - Assert `case_diagnostics["citation_contract_status"] == "supported_cited_answer"`.
   - Assert `unsupported_citation_ids == []`.

2. Add `test_public_case_diagnostics_flags_projected_unretrieved_citation` in `tests/test_public_benchmarks.py`.
   - Call `build_case_diagnostics(...)` with `answer_mode="projected"`, rendered/source IDs `["msg_selected"]`, and answer text citing `[msg_unselected]`.
   - Assert `unsupported_citation_ids == ["msg_unselected"]`.
   - Assert `citation_contract_status == "unsupported_citation"`.
   - Assert `failure_class == "unsupported_answer"`.

3. Add `test_public_answerer_renders_structured_evidence_with_citation_contract` in `tests/test_public_benchmarks.py`.
   - Monkeypatch `ChatOpenAI` with a fake object that records messages.
   - Instantiate `PublicAnswerer` with a dummy API key.
   - Pass structured evidence containing `id`, `text`, `session_id`, `date`, and `component`.
   - Assert the human message includes an evidence list with the allowed ID and text.
   - Assert the system message requires citations from allowed IDs and refusal when insufficient.

Run and record failures before production code edits:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_projected_answer_cites_selected_evidence -q
uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_flags_projected_unretrieved_citation -q
uv run pytest tests/test_public_benchmarks.py::test_public_answerer_renders_structured_evidence_with_citation_contract -q
```

Expected RED: tests fail because projected answers currently omit citations, diagnostics do not expose the new contract status, and `PublicAnswerer` accepts loose `dict[str, str]` context.

## GREEN

1. In `src/memoryos_lite/agent_answer_eval.py`, extend `AgentAnswerEvalResult` append-only with:
   - `missing_citation: bool`
   - `explicit_no_evidence_refusal: bool`
   - `citation_contract_status: str`

2. Preserve current citation extraction and unsupported-citation behavior. Define statuses deterministically:
   - no retrieved evidence plus refusal -> `no_evidence_refusal`;
   - cited IDs all in rendered evidence -> `supported_cited_answer`;
   - retrieved evidence but no citations and no refusal -> `missing_citation`;
   - any unrendered cited ID -> `unsupported_citation`;
   - factual no-evidence answer or other unsupported case -> `unsupported_answer`.

3. In `src/memoryos_lite/evals.py`, update deterministic projection:
   - pass each selected `EvidenceItem` source IDs into projection;
   - append sorted citations as `[id]` after each projected clause;
   - return `Insufficient retrieved evidence to answer with source citations.` when selected evidence is empty.

4. In `src/memoryos_lite/public_benchmarks.py`, add a small structured evidence dataclass or typed dict for public answer input. Build it from `output.sources` plus available v3 final-context metadata. Keep IDs and text mandatory, metadata optional.

5. Change `PublicAnswerer.answer(...)` to accept structured evidence. Render deterministic, inspectable evidence text such as:

```text
Allowed evidence:
- id: sample_qa_001:sample:D1:1
  component: recall
  session_id: D1
  date: 2026-01-01
  text: Alice said the marker is MemoryOS Lite.
```

6. Update the system prompt to require citations exactly as `[id]`, forbid invented IDs, and require an explicit refusal when evidence is insufficient.

7. In `src/memoryos_lite/public_case_diagnostics.py`, mirror the new answer eval fields into `case_diagnostics`, and classify `missing_citation`/`unsupported_citation` as unsupported-answer failures without changing retrieval/context status semantics.

8. Re-run the three required focused tests until they pass.

## REFACTOR

1. Add or update `tests/test_agent_answer_eval.py` for the new status fields without removing existing assertions.
2. Keep evidence rendering helpers small and local to `public_benchmarks.py` unless reuse becomes necessary.
3. Avoid dataset-specific rules: no case ID, expected answer, LongMemEval-only, or LoCoMo-only citation hacks.
4. Verify `MEMORYOS_MEMORY_ARCH=v1` remains explicit by running the existing v1 public benchmark fallback test.

Focused regression:

```bash
uv run pytest tests/test_agent_answer_eval.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context -q
uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py -q
```

## Smoke

Run full local verification:

```bash
uv run pytest -q
uv run ruff check .
```

Run milestone evals in parallel when provider access is available:

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

If LLM provider access is unavailable, record the blocker and run deterministic no-LLM smoke only as fallback evidence. Do not mark the milestone gate satisfied from fallback smoke.

## Review

Review must check:

- the three required RED tests failed before production edits and pass after;
- citations cannot reference unselected/unrendered IDs;
- deterministic/no-LLM diagnostics still split retrieval miss, context missing evidence, unsupported answer, and evidence-hit-answer-fail;
- LongMemEval and LoCoMo movement lists are separate, with pass-to-fail explicit;
- v1 fallback remains explicit and unbroken;
- v3 remains default;
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off;
- no benchmark improvement claim is made without case-level evidence.
