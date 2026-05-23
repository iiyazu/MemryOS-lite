# phase: phase-11

# Phase 11 Brainstorm: Evidence Handoff And Context Selection

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Dispatch target: execute lane `phase-11`, target state `evidence-handoff-reliable`.

## Binding Read

The Phase 11 bundle is binding unless newer file evidence supersedes it. I found no newer evidence that changes the bundle's scope. Phase 11 should focus on the real v3/public benchmark path from selected evidence to rendered evidence to answer evidence to judged output:

```text
indexed -> retrieved -> selected -> rendered -> cited -> judged
```

The immediate fixed slice is the LoCoMo evidence-hit-answer-fail group:

- `conv-26_qa_006`
- `conv-26_qa_016`
- `conv-26_qa_024`
- `conv-26_qa_027`

The retrieval misses must stay visible and should not be folded into answer failures:

- `conv-26_qa_003`
- `conv-26_qa_004`
- `conv-26_qa_008`
- `conv-26_qa_019`
- `conv-26_qa_020`
- `conv-26_qa_025`

Phase 10 accepted evidence was narrow but real: LoCoMo 30 moved `conv-26_qa_011` and `conv-26_qa_012` fail-to-pass with no LongMemEval or LoCoMo pass-to-fail cases. Phase 10 also left a review note that raw report rows are not self-contained enough when comparison paths are absent.

## Current Anchors

- `V3ContextComposer.build()` already emits layered items, component accounting, final context trace, component drop counts, and LoCoMo neighbor diagnostics.
- `MemoryOSService._context_package_from_v3()` projects v3 recall/archival items into legacy `ContextPackage.retrieved_evidence` and public-eval metadata.
- `public_case_diagnostics.build_case_diagnostics()` reports retrieved, selected, final trace, rendered, cited, answer support, judge status, movement status, and failure class.
- `PublicAnswerer` consumes structured `AnswerEvidence` with source ids, session id, date, rendered index, token estimate, and metadata.
- Letta reference semantics support this direction: component-level context accounting, explicit passage provenance, and context-window/token accounting. They do not justify adding Letta as a runtime dependency.

## Approaches

### Approach A: Append-only handoff ledger and diagnostic split

Add a structured handoff ledger in the v3/public report path that records expected-source status at each boundary: retrieved, selected, final-trace/rendered, answer-evidence input, cited, judged. Split generic `context_missing_evidence` into more precise classes such as `selected_drop`, `render_drop`, and `answer_evidence_drop`, while keeping existing fields append-only.

Trade-offs:

- Best anti-demo fit because it exercises the real v3 context package, public answer evidence construction, and report diagnostics.
- Gives review lane direct case-level evidence without relying on manual tables.
- Lower behavioral risk because it can start as diagnostics and tests before changing selection.
- May only reclassify failures if answer quality is the true bottleneck.

### Approach B: Context selection guardrail for expected source continuity

Make `V3ContextComposer` or `_context_package_from_v3()` preserve source continuity more aggressively when selected evidence has packet/session metadata and would otherwise lose message id, session id, date, or rendered order before answer construction.

Trade-offs:

- Can produce real improvement if the bottleneck is selected-to-rendered or rendered-to-answer handoff.
- Higher pass-to-fail risk because changing final context ordering can crowd out LongMemEval evidence.
- Must be driven by a RED test that proves a handoff loss, not by broad retuning or case-specific LoCoMo terms.

### Approach C: Public answer evidence rendering and prompt-only correction

Keep context selection unchanged and focus on the `AnswerEvidence` handed to `PublicAnswerer`, including source id projection, session/date metadata, rendered order, and answer-evidence diagnostics.

Trade-offs:

- Useful if the four evidence-hit-answer-fail LoCoMo cases already have expected sources rendered but the answerer sees weak or misordered structured evidence.
- Lower retrieval risk than selection changes.
- Prompt-only changes are a demo-only trap unless diagnostics prove answer projection is the bottleneck and reports separate answer movement from source/retrieval movement.

## Recommendation

Use Approach A first, with a narrow Approach C fix only if a RED test proves rendered evidence is not faithfully handed to answer evidence. Defer Approach B unless the first RED test proves selected evidence is dropped before rendering or source refs are projected incorrectly.

This route satisfies the anti-demo gate because it requires the execute lane to:

- add at least one RED test before production changes;
- wire evidence status through the real v3/public benchmark path, not a sidecar script;
- keep selected, rendered, cited, and judged statuses independently visible;
- preserve same-case movement fields or artifacts so Phase 11 does not rely on manual case tables;
- report fail-to-pass, pass-to-fail, unchanged-fail, retrieval/source movement, and judged answer movement separately;
- leave `MEMORYOS_AGENT_KERNEL=v1` opt-in and kernel traces empty by default.

The first implementation plan should target one or more of these RED tests:

- selected expected source is retrieved but dropped before final rendering, and diagnostics classify selected-drop/render-drop rather than generic `context_missing_evidence`;
- final rendered expected evidence exists, but answer evidence construction loses source id, session id, date, or rendered order;
- v3 recall/archival source refs project to the wrong message id in `_context_package_from_v3()`;
- comparison report paths produce self-contained movement fields and baseline source metadata.

## Demo-only Traps

- Adding a replay script or phase-local analyzer that never touches `memoryos eval public`.
- Reclassifying failures only in `case_matrix.md` while raw report diagnostics remain ambiguous.
- Claiming a LoCoMo aggregate gain without same-case fail-to-pass/pass-to-fail lists.
- Hiding retrieval misses by converting them to answer failures.
- Branching on `conv-26`, `qa_*`, expected source ids, expected answers, or known failed-case lexical terms.
- Treating projected/no-LLM evidence as full-chain quality evidence.
- Prompt-only answerer changes without diagnostics proving the answer evidence input was the bottleneck.
- Enabling the v3 kernel by default or using opt-in kernel traces to justify default-path quality claims.

## Risks And Guards

- v1 fallback: diagnostics must remain compatible with `MEMORYOS_MEMORY_ARCH=v1`; v1 reports should not grow misleading v3 context fields.
- v3 default: default architecture must remain `v3`, and changes must not require extra flags to exercise the public path.
- kernel opt-in: `MEMORYOS_AGENT_KERNEL=v1` must remain off by default; default public reports should keep `kernel_trace_events == []`.
- LoCoMo source grounding: LoCoMo can pass/fail from answer behavior even when source grounding is weak; report source/retrieval movement separately from judged answer movement.
- LongMemEval regression: final context ordering or budget behavior changes can crowd out exact LongMemEval sources; use LongMemEval 30 as a regression guard and add a focused guard if context selection changes.
- benchmark overfitting: no case-id, expected-answer, expected-source, or dataset-string rules; improvements must come from generic provenance, ordering, accounting, or projection behavior.
- movement evidence: raw `movement_status: new_case_no_baseline` is not ACK-grade when comparison paths are absent; Phase 11 should make comparison artifacts self-contained.

## Execute-lane Shape

1. Start with focused RED tests against diagnostics/projection/answer-evidence handoff.
2. Implement append-only report fields or narrow projection fixes.
3. Run focused tests:

```bash
uv run pytest tests/test_context_composer.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py tests/test_agent_answer_eval.py -q
uv run ruff check .
```

4. Run broader tests unless scoped down with evidence:

```bash
uv run pytest -q
uv run ruff check .
```

5. For milestone evidence, run LongMemEval 30 and LoCoMo 30 full-chain LLM gates in parallel with `MEMORYOS_MEMORY_ARCH=v3`, update heartbeat files, and do not mark the gate satisfied from no-LLM/projected evidence.

## Storm Decision

Proceed with a diagnostics-first, append-only evidence handoff route. It is the narrowest path that can improve or precisely reclassify the remaining evidence-hit-answer-fail cases while preserving retrieval misses, v1 fallback, v3 default behavior, kernel opt-in, and same-case benchmark accountability.
