# phase: phase-6

# Spec: Answer Projection And Citation Contract

Context source: `.hermes-loop/work/phase-6/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Goal

Wire a testable answer citation contract into the real public benchmark `memoryos_lite` path. The phase must make answer grounding auditable without claiming benchmark improvement until case-level LongMemEval and LoCoMo evidence supports that claim.

## Contract

An answer is contract-compliant when:

- every factual answer span is followed by one or more citations in the form `[evidence_id]`;
- every cited `evidence_id` is present in the structured evidence rendered to the answerer for that case;
- if no rendered evidence is available, or rendered evidence is insufficient, the answer is an explicit refusal and does not cite any ID;
- projected/no-LLM answers use the same citation/refusal contract as LLM answers;
- diagnostics can explain whether failure happened at retrieval, selected context, rendered evidence, citation support, answer quality, or judge status.

Unsupported examples:

- answer contains no citation while rendered evidence exists;
- answer cites `[wrong_id]` when `wrong_id` was not rendered;
- answer gives a factual answer when rendered evidence is empty;
- answer cites dropped v3 diagnostics or retrieval candidates that did not enter rendered evidence.

## Structured Evidence Input

Introduce a small public benchmark evidence payload derived from selected/rendered evidence, not from expected answers:

```python
{
    "id": "stable source or passage id",
    "text": "rendered evidence text",
    "source_type": "message|passage|core|unknown",
    "session_id": "optional benchmark/session id",
    "date": "optional date or timestamp if present in text/metadata",
    "component": "recall|archival|core|recent|unknown",
}
```

Required behavior:

- preserve stable IDs from `output.sources`, `v3_final_context_trace`, and rendered context metadata;
- never include budget-dropped diagnostics as renderable evidence;
- keep the payload append-only in public reports;
- include date/session metadata when available, especially for LoCoMo and temporal LongMemEval cases;
- do not include expected answer text or benchmark case-id rules.

## Public Answerer

`PublicAnswerer` should render structured evidence, not loose context text. The LLM prompt must state:

- answer only from the evidence list;
- cite allowed IDs exactly as `[id]`;
- do not invent IDs;
- refuse when evidence is absent or insufficient;
- for temporal/session questions, use evidence dates/session metadata and cite the supporting IDs.

The method can keep backward-compatible call surfaces only if tests prove `run_public_benchmark` passes structured evidence through the real answerer path.

## Deterministic Projection

Projected/no-LLM answers must preserve deterministic behavior:

- no API calls;
- same retrieval/context diagnostics still populated;
- projected answer text includes selected evidence citations;
- no-evidence output is the same explicit refusal style expected by `agent_answer_eval`;
- answer quality can still fail independently of citation support.

This means a projected answer with rendered evidence and a citation can be `supported_cited_answer` but still fail the judge/substr verdict, which should remain `evidence_hit_answer_fail`.

## Diagnostics

Extend diagnostics append-only. Required fields in `case_diagnostics` and top-level report mirrors where useful:

- `rendered_evidence_ids`
- `cited_source_ids`
- `unsupported_citation_ids`
- `missing_citation`
- `explicit_no_evidence_refusal`
- `citation_contract_status`: one of `supported_cited_answer`, `missing_citation`, `unsupported_citation`, `no_evidence_refusal`, `unsupported_answer`
- existing `retrieval_status`, `selected_context_status`, `rendered_context_status`, `answer_support_status`, `failure_class`, `movement_status`, and `judge_status`

Failure classification must remain ordered:

1. judge questionable;
2. retrieval miss;
3. context missing evidence;
4. citation/unsupported answer;
5. supported cited pass;
6. evidence-hit-answer-fail.

## Compatibility

- `MEMORYOS_MEMORY_ARCH=v3` remains the default architecture.
- `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback and must not receive v3-only context payload requirements.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off and is not required for Phase 6.
- Existing public report fields are append-only; do not rename or remove current fields.
- No Letta runtime dependency is added.

## Required RED Tests

- `tests/test_public_benchmarks.py::test_public_benchmark_projected_answer_cites_selected_evidence`
- `tests/test_public_benchmarks.py::test_public_case_diagnostics_flags_projected_unretrieved_citation`
- `tests/test_public_benchmarks.py::test_public_answerer_renders_structured_evidence_with_citation_contract`

Also add coverage for no-evidence refusal and temporal LoCoMo date/session grounding if the required RED tests do not cover them sufficiently.

## Milestone Evidence

After focused tests and regression pass, run 30-case full-chain LLM judge reports for LongMemEval and LoCoMo using the Phase 5 comparison reports from `.hermes-loop/work/phase-6/context_bundle.md`.

Acceptable language after milestone eval is conservative: report case movement and diagnostics, not broad improvement claims. If provider access is blocked, record the blocker and run deterministic no-LLM smoke only as fallback evidence.
