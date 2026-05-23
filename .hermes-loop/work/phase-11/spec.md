# phase: phase-11

# Phase 11 Spec: Evidence Handoff And Context Selection

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope Decision

Use the brainstorm recommendation from `.hermes-loop/work/phase-11/brainstorm.md`: implement Approach A first, an append-only handoff ledger and diagnostic split, with a narrow Approach C answer-evidence projection fix only if a RED test proves rendered evidence is not faithfully handed to the answerer. Do not start with Approach B selection retuning unless a failing test proves selected evidence is dropped before rendering or source refs are projected incorrectly.

The phase target is the real public benchmark path:

```text
indexed -> retrieved -> selected -> rendered -> answer_evidence -> cited -> judged
```

The target cases are the Phase 10 LoCoMo evidence-hit-answer-fail cases:

- `conv-26_qa_006`
- `conv-26_qa_016`
- `conv-26_qa_024`
- `conv-26_qa_027`

The remaining retrieval misses stay visible and are not converted into answer failures:

- `conv-26_qa_003`
- `conv-26_qa_004`
- `conv-26_qa_008`
- `conv-26_qa_019`
- `conv-26_qa_020`
- `conv-26_qa_025`

## Behavior To Add Or Verify

Phase 11 adds or verifies append-only diagnostics that make each boundary auditable. Existing report fields must remain compatible.

### Selected Handoff

For each public benchmark row, `case_diagnostics` must expose a structured field named `evidence_handoff` with these keys:

- `expected_source_ids`: expected benchmark source ids after de-duplication.
- `retrieved_ids`: candidate message ids from retrieval, episode candidates, and planned evidence.
- `retrieved_overlap_ids`: expected ids found in retrieved ids.
- `selected_ids`: v3 selected ids from included diagnostics, v3 items, and final trace source refs. For non-v3 fallback, use existing fallback behavior.
- `selected_overlap_ids`: expected ids found in selected ids.
- `rendered_ids`: final source ids actually projected into the answer/report.
- `rendered_overlap_ids`: expected ids found in rendered ids.
- `answer_evidence_ids`: ids handed to `PublicAnswerer`; for projected/no-LLM mode this may equal `rendered_ids`.
- `answer_evidence_overlap_ids`: expected ids found in answer evidence.
- `cited_source_ids`: source ids cited by the answer text.
- `cited_overlap_ids`: expected ids found in citations.
- `stage_status`: mapping with statuses for `retrieved`, `selected`, `rendered`, `answer_evidence`, and `cited`.
- `failure_boundary`: first lossy boundary for expected evidence, or `none` when expected evidence survives through answer evidence.

The selected stage must use only included v3 rows. Dropped `v3_diagnostics` or dropped `final_context_trace` rows cannot count as selected.

### Rendered Handoff

If expected evidence is retrieved and selected but absent from final rendered `source_ids`, diagnostics must classify the boundary as render loss. This must be distinguishable from evidence that was never selected.

Exact required values:

- `stage_status["selected"] == "evidence_selected"` when expected ids appear in `selected_ids`.
- `stage_status["rendered"] == "evidence_missing"` when expected ids do not appear in `rendered_ids`.
- `failure_boundary == "render_drop"`.
- `failure_class == "evidence_selected_not_rendered"` or an equivalent stable class documented in the same test and replay matrix.

### Answer-Evidence Handoff

When `llm_answer=True`, the report must preserve the exact ids and metadata handed to `PublicAnswerer`. For each `AnswerEvidence`, diagnostics must expose:

- `evidence_id`
- `source_ids`
- `component`
- `session_id`
- `date`
- `rendered_index`
- `estimated_tokens`

If expected evidence is rendered but missing from answer evidence, diagnostics must classify the boundary as answer-evidence loss.

Exact required values:

- `stage_status["rendered"] == "evidence_rendered"`.
- `stage_status["answer_evidence"] == "evidence_missing"`.
- `failure_boundary == "answer_evidence_drop"`.
- `failure_class == "evidence_rendered_not_answer_evidence"` or an equivalent stable class documented in the same test and replay matrix.

If expected evidence survives to answer evidence but the answer fails, the failure must remain an answer-use/judge failure, not a retrieval or context failure.

Exact required values:

- `stage_status["answer_evidence"] == "evidence_in_answer_evidence"`.
- `failure_boundary == "none"`.
- `failure_class == "evidence_hit_answer_fail"` unless citation support proves `unsupported_answer`, `refusal_despite_evidence`, or `judge_questionable`.

### Movement Diagnostics

When `--comparison-report` is supplied, public rows must be self-contained for same-case diagnosis:

- row-level `movement_status`;
- `case_diagnostics.baseline_verdict`;
- `case_diagnostics.movement_baseline_source`;
- separate fail-to-pass, pass-to-fail, unchanged-pass, and unchanged-fail summaries in phase artifacts;
- source/retrieval movement kept separate from judged-answer movement.

When no comparison report is supplied, `new_case_no_baseline` remains allowed, but it is not promotion-grade movement evidence.

## Letta Semantics Used

Letta is a design reference only. Do not add it as a runtime dependency.

Borrow only these semantics:

- component-level context accounting, similar to Letta context-window overview;
- passage/evidence provenance, similar to Letta passage ids, archive ids, metadata, and source associations;
- context-window accounting that preserves what was included, dropped, rendered, and handed to the answerer.

## Non-Goals

- Do not retune broad retrieval unless a RED handoff test proves a narrow metadata/projection change is required.
- Do not change benchmark scoring semantics, judge criteria, or expected-answer handling.
- Do not add Letta as a dependency or port Letta internals.
- Do not change `MEMORYOS_MEMORY_ARCH=v1` fallback behavior.
- Do not change the default memory architecture away from v3.
- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not claim production readiness.
- Do not claim aggregate-only benchmark improvement.
- Do not edit `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, repository docs outside phase-11 artifacts, or unrelated user/controller changes during the plan draft lane.

## Anti-Overfitting Constraints

- No case-id branches for `conv-26`, `qa_*`, LongMemEval ids, or any known failed case.
- No expected-answer leaks.
- No expected-source-id specific logic.
- No benchmark-specific lexical rules that only match the Phase 11 focus cases.
- No scoring or judge changes to manufacture pass rate.
- No prompt-only answerer tweak may be called an architecture improvement unless diagnostics prove answer-evidence projection is the bottleneck.
- No hiding retrieval misses by relabeling them as answer failures.
- No projected/no-LLM evidence may be promoted as full-chain LLM judged quality.

## Acceptance Criteria

### Real v3/public benchmark path

- At least one RED test fails before production changes.
- The fix is exercised by `run_public_benchmark()` and `memoryos eval public`, not by a phase-only sidecar script.
- Public report rows include append-only evidence handoff diagnostics for selected, rendered, answer-evidence, cited, and judged stages.
- The Phase 11 case matrix lists fail-to-pass, pass-to-fail, unchanged-fail, retrieval miss, selected-drop, render-drop, answer-evidence-drop, citation/answer-fail, and judge-questionable cases separately.

### v1 fallback

- Explicit `MEMORYOS_MEMORY_ARCH=v1` public benchmark behavior stays compatible.
- v1 rows do not gain misleading v3-only selected/rendered provenance.
- Existing v1 fallback tests remain green.

### v3 default

- Default settings still resolve `memoryos_memory_arch` to `v3`.
- The public benchmark default path still emits v3 diagnostics without extra flags.
- Existing v3 component accounting and final context trace fields remain append-only and compatible.

### Kernel opt-in

- Default public benchmark rows keep `kernel_trace_events == []`.
- `case_diagnostics.kernel_trace_present` remains `False` by default.
- Opt-in kernel tests still require `MEMORYOS_AGENT_KERNEL=v1`.

### Benchmark evidence

- Focused tests and `ruff` pass.
- Full `uv run pytest -q` and `uv run ruff check .` pass unless an execute artifact records a concrete blocker.
- LongMemEval 30 and LoCoMo 30 full-chain LLM judge gates run through `MEMORYOS_MEMORY_ARCH=v3`.
- Milestone evals use comparison reports so movement is same-case and self-contained.
- LongMemEval has no material collapse.
- LoCoMo movement, if any, is explainable per case and not aggregate-only.
