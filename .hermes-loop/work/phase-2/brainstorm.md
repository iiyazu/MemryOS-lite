# phase: phase-2

# Brainstorm - Evidence Harness And Failure Taxonomy

## Active Goal Boundary

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

This brainstorm treats Phase 2 as a diagnostics and contract phase only. It should make failures classifiable before retrieval optimization, answer prompt tuning, archive attachment/scope changes, core-memory mutation expansion, or kernel tool expansion.

## Context Read

Consumed phase-local and project context:

- `.hermes-loop/work/phase-2/context_bundle.md`
- `.hermes-loop/work/phase-2/god_dispatch.json`
- `.hermes-loop/work/phase-1/letta_gap_matrix.md`
- `.hermes-loop/work/phase-1/reflect_phase-1.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/agent_answer_eval.py`
- `src/memoryos_lite/context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_answer_eval.py`
- supporting reads from `src/memoryos_lite/evals.py`, `src/memoryos_lite/engine.py`, `src/memoryos_lite/config.py`, `src/memoryos_lite/cli.py`, `tests/test_context_composer.py`, `tests/test_llm_judge.py`, and `tests/test_agent_kernel.py`

Key current shape:

- Public benchmark results already expose legacy fields, v2-style candidate evidence fields, v3 context diagnostics, and opt-in kernel trace events.
- `source_hit` is still a final projection/source-overlap signal, not pure evidence localization.
- `agent_answer_eval.py` has deterministic citation and unsupported-answer diagnostics, but these are not yet bound into the public benchmark case report.
- v3 settings default to `memoryos_memory_arch="v3"`, but service routing currently requires `memoryos_memory_arch` to be present in `settings.model_fields_set`, so the real default public path needs an explicit RED test.
- Kernel trace events are only emitted when `MEMORYOS_AGENT_KERNEL=v1`; this must remain opt-in and diagnostic only.

## Phase 2 Design Pressure

The harness must answer, per case:

- Did expected evidence exist in indexed/stored source IDs?
- Did retrieval candidate IDs include expected evidence?
- Did v3 selected context IDs include expected evidence?
- Did the final answer-rendered context include the selected evidence IDs?
- Did answer projection cite selected evidence, refuse, or hallucinate unsupported content?
- Did judge status pass, fail, error, or look questionable relative to deterministic evidence signals?
- Did kernel trace events appear only when explicitly enabled?
- Did the case move from pass to fail, fail to pass, unchanged pass, or unchanged fail compared with a baseline slice?

The important split is not aggregate score. It is case-level bottleneck class.

## Approaches

### Approach A - Minimal Report Decoration

Add a few diagnostic fields directly to `PublicBenchmarkResult` and compute a simple `failure_class` inside `public_benchmarks.py`.

Likely fields:

- `failure_class`
- `answer_support_status`
- `cited_source_ids`
- `unsupported_citation_ids`
- `retrieved_expected_evidence_ids`

Tradeoffs:

- Pros: smallest diff; fastest to RED/green; low risk to existing CLI report and JSON consumers if fields are append-only.
- Pros: uses existing `episode_candidate_message_ids`, `planned_evidence_message_ids`, `source_overlap_ids`, `v3_diagnostics`, and `kernel_trace_events`.
- Cons: risks another pile of fields without a clear taxonomy boundary.
- Cons: weak at separating selected v3 evidence from rendered answer-context evidence unless the renderer is represented explicitly.
- Cons: case movement and judge-questionable classification may become ad hoc in `public_benchmarks.py`.

Best use:

- Acceptable only if Phase 2 is treated as a very narrow report-hardening phase and later phases add stronger rendered-context accounting.

### Approach B - Dedicated Case Taxonomy Layer

Introduce a small deterministic taxonomy function/module used by the public benchmark runner. It consumes existing result ingredients plus answer-eval output and emits a structured `case_diagnostics` object while leaving legacy top-level fields intact.

Possible object:

```text
case_diagnostics:
  benchmark
  case_id
  retrieval_status
  selected_context_status
  rendered_context_status
  answer_support_status
  judge_status
  movement_status
  failure_class
  expected_source_ids
  retrieved_evidence_ids
  selected_context_ids
  rendered_evidence_ids
  cited_source_ids
  unsupported_citation_ids
  kernel_trace_present
```

Tradeoffs:

- Pros: clear contract for `retrieval_miss`, `evidence_hit_answer_fail`, `unsupported_answer`, `supported_cited_answer`, `judge_questionable`, `pass_to_fail`, and `fail_to_pass`.
- Pros: can be tested with focused fixtures before production changes.
- Pros: preserves existing report compatibility because old fields remain top-level and unchanged.
- Pros: gives later retrieval/scope and answer-projection phases one stable artifact to compare.
- Cons: requires a little more design discipline around status names and precedence.
- Cons: rendered answer-context IDs may initially be equivalent to `source_ids` or `output.sources` until a richer rendering hook exists; this must be labeled honestly.

Best use:

- Recommended route for Phase 2. It is diagnostic-first, backward-compatible, and strong enough to prevent aggregate-only ACK.

### Approach C - Full Letta-Style Trace Ledger

Create a richer event ledger for benchmark cases, with typed steps for retrieval, context selection, answer rendering, answer projection, judge evaluation, and optional kernel trace.

Tradeoffs:

- Pros: closest to Letta-style operational state; easiest to audit later tool/context behavior.
- Pros: gives a durable foundation for archive scope, source-vs-agent passage roles, component token accounting, and kernel trace correlation.
- Cons: too large for Phase 2 if the immediate goal is taxonomy and RED tests.
- Cons: higher compatibility risk if the public report shape becomes nested and large too quickly.
- Cons: may drift into runtime/kernel architecture work, which is explicitly out of scope.

Best use:

- Defer until after Phase 2 proves the smaller taxonomy object is insufficient.

## Recommended Route

Use Approach B.

Phase 2 should add a dedicated case taxonomy layer and append its output to public benchmark reports while keeping legacy report fields unchanged. The first implementation should compute taxonomy from existing signals and deterministic answer-citation evaluation. It should not optimize retrieval, change prompt wording for benchmark gain, alter archive scope, or enable the kernel.

Recommended precedence for `failure_class`:

1. `retrieval_miss`: no expected source appears in retrieved/planned/selected evidence IDs.
2. `context_missing_evidence`: expected source was retrieved or planned but not present in selected/rendered answer-context IDs.
3. `unsupported_answer`: answer contains content without selected evidence support, cites an unretrieved ID, or fails to refuse when no evidence exists.
4. `evidence_hit_answer_fail`: expected evidence reached selected/rendered context but projected answer or judge still fails.
5. `judge_questionable`: deterministic evidence/answer-support signals conflict with LLM judge verdict or judge returned parse/provider error.
6. `supported_cited_answer`: answer passes and cites selected evidence, or deterministic projected mode has expected source/answer support under the available no-LLM contract.
7. `unknown`: insufficient diagnostic data; this should block ACK if it appears in Phase 2 milestone cases without a recorded blocker.

Recommended movement statuses:

- `unchanged_pass`
- `unchanged_fail`
- `fail_to_pass`
- `pass_to_fail`
- `new_case_no_baseline`

Movement should be reported per benchmark and per case, never only as a mean.

## Files Likely Touched

Expected implementation files:

- `src/memoryos_lite/public_benchmarks.py`
  - add append-only report fields or a nested `case_diagnostics` field;
  - invoke deterministic answer-support classification;
  - preserve `PublicBenchmarkResult.to_report()` compatibility.
- `src/memoryos_lite/agent_answer_eval.py`
  - likely reuse as-is, or add a helper that accepts selected/rendered evidence IDs instead of only free-form scripted cases.
- `src/memoryos_lite/evals.py`
  - only if `BaselineOutput` needs explicit selected/rendered evidence ID fields not currently available from `sources`, `retrieved_evidence`, or v3 metadata.
- `src/memoryos_lite/engine.py`
  - only if default v3 route test proves current `model_fields_set` guard prevents the documented default path.
- `src/memoryos_lite/cli.py`
  - optional summary columns only; do not remove or rename current public table columns.
- `tests/test_public_benchmarks.py`
  - primary RED tests for taxonomy, compatibility, v3 default path, and kernel opt-in.
- `tests/test_agent_answer_eval.py`
  - focused tests for answer-support helper behavior if helper changes.
- `tests/test_context_composer.py`
  - only if selected/rendered evidence IDs require composer-level accounting.
- `tests/test_llm_judge.py`
  - only if judge status classification needs deterministic parse/error fixtures.
- `docs/public-benchmark-diagnosis.md`
  - update metric semantics and taxonomy interpretation after tests pass.
- `docs/known-issues.md`
  - update only if a limitation is intentionally left for a later phase.

Avoid touching:

- `.hermes-loop/blueprint.md`, `.hermes-loop/config.json`, `.hermes-loop/god_launcher.sh`, `.hermes-loop/god_loop_prompt.md`, `.hermes-loop/hermes_loop.py`, `.hermes-loop/hermes_reporter.py`, `AGENTS.md`, and `CLAUDE.md` because the phase bundle marks them quarantined.

## RED-Test Anchors

Primary tests should fail before implementation.

### Public Report Taxonomy

Add a public benchmark fixture where:

- Case A retrieves no expected source and must classify as `retrieval_miss`.
- Case B retrieves or selects expected source but answer lacks expected fact or citation and must classify as `evidence_hit_answer_fail` or `unsupported_answer`.
- The test must fail if these collapse into a single `fail` or if only aggregate pass rate is available.

Anchor real Phase 0 case labels in assertions/report examples:

- LongMemEval pass: `1e043500`
- LongMemEval retrieval miss: `58bf7951`
- LongMemEval evidence-hit answer failures: `e47becba`, `118b2229`, `51a45a95`
- LoCoMo evidence-hit answer failure: `conv-26_qa_001`
- LoCoMo retrieval/scope misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`

### Backward Compatibility

Add or harden a test that:

- existing top-level fields remain in `to_report()`;
- `PUBLIC_TABLE_COLUMNS` still render;
- new taxonomy fields are append-only;
- old consumers can ignore `case_diagnostics`.

### Source-Hit Separation

Add a test that proves:

- `source_hit` remains final projection/source overlap;
- retrieved/planned/selected/rendered evidence IDs are separately present;
- a case can have evidence IDs without being counted as answer pass;
- a case can fail answer projection without being relabeled as retrieval miss.

### Default v3 And Explicit v1 Fallback

Add a test using plain `Settings(data_dir=...)` and `memoryos_lite` public eval:

- default report must include `memory_arch == "v3"` and v3 diagnostics;
- explicit `Settings(memoryos_memory_arch="v1")` must preserve v1 fallback and not emit v3 composer diagnostics as if v3 ran.

This should expose whether `_should_route_to_v3_context()` incorrectly requires an explicit env/model field for the documented v3 default.

### Kernel Opt-In

Add or harden a test that:

- default public benchmark report has `kernel_trace_events == []`;
- `Settings(memoryos_agent_kernel="v1")` emits trace events;
- taxonomy treats kernel trace as audit evidence only, not answer-quality evidence.

### Answer Support

Add tests around `agent_answer_eval` or the new helper:

- supported cited answer cites a selected evidence ID;
- unsupported citation is flagged when citation is not in retrieved/selected evidence;
- no-evidence content must refuse to avoid `unsupported_answer`;
- projected/no-LLM mode is labeled separately from full LLM answer/judge mode.

## Benchmark And Eval Plan

Focused test loop:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py tests/test_llm_judge.py -q
```

Regression loop:

```bash
uv run pytest -q
uv run ruff check .
```

Mandatory milestone eval, separately reported:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30
```

If LLM answer/judge cannot run because provider keys, model access, or data are unavailable, record the exact blocker and run deterministic no-LLM smoke only as fallback evidence. Do not mark the mandatory full-chain milestone satisfied from fallback-only evidence.

Reporting must include separate LongMemEval and LoCoMo sections:

- pass/fail counts;
- `retrieval_miss`;
- `context_missing_evidence`;
- `evidence_hit_answer_fail`;
- `unsupported_answer`;
- `supported_cited_answer`;
- `judge_questionable`;
- `fail_to_pass`;
- `pass_to_fail`;
- unchanged fail/pass;
- representative case IDs and source/evidence IDs.

## Risks

- `source_hit` may be accidentally reinterpreted as retrieval localization. Mitigation: keep source/evidence metrics and final answer pass fields separate in tests and docs.
- Default v3 routing may not actually run unless `MEMORYOS_MEMORY_ARCH=v3` is explicitly set. Mitigation: RED test the real public eval path with plain `Settings()`.
- Adding nested diagnostics may break consumers if top-level report fields are renamed or removed. Mitigation: append-only fields and compatibility tests.
- Answer-support classification may overclaim in projected/no-LLM mode. Mitigation: include `answer_mode` and `judge_status`; do not equate deterministic projection with full-chain answer quality.
- Judge errors may be hidden as ordinary failures. Mitigation: explicit `judge_status` values such as `not_run`, `pass`, `fail`, `error`, and `questionable`.
- LoCoMo retrieval/scope misses may be hidden behind LongMemEval movement. Mitigation: separate benchmark reports and ACK gates.
- Kernel traces may be mistaken for answer improvement. Mitigation: kernel events remain opt-in audit signals and do not affect answer pass.

## Demo-Only Or Partial Work

This would count as demo-only or partial and should not ACK Phase 2:

- only adding a markdown taxonomy without wiring it to real public benchmark reports;
- only improving aggregate pass rate or table columns without per-case diagnostic objects;
- only running LongMemEval and skipping LoCoMo;
- only running deterministic no-LLM smoke while claiming full-chain LLM milestone completion;
- using `source_hit` as proof of evidence localization;
- collapsing retrieval misses and evidence-hit answer failures into one generic failure;
- hiding pass-to-fail regressions behind a better aggregate mean;
- changing answer prompts or retrieval ranking before taxonomy RED tests exist;
- enabling `MEMORYOS_AGENT_KERNEL=v1` by default;
- making benchmark case-id or expected-answer hacks;
- removing or breaking v1 fallback;
- changing quarantined control files as implementation evidence.

## Preservation Requirements

Must preserve explicitly:

- v1 fallback: `MEMORYOS_MEMORY_ARCH=v1` remains available and tested.
- v3 default: public benchmark default path must be verified as v3, not merely documented.
- kernel opt-in: `MEMORYOS_AGENT_KERNEL=v1` remains off by default.
- conservative `source_hit`: final projection/source overlap only, not pure evidence localization.
- separate LongMemEval and LoCoMo treatment: no combined-only aggregate gates.
- no Letta runtime dependency.
- no production-ready framing; MemoryOS Lite remains an eval-driven, source-attributed Agent/RAG memory prototype.

## Recommended Phase 2 Exit Criteria

Phase 2 can be considered usable only when:

- RED tests prove `retrieval_miss` and `evidence_hit_answer_fail` cannot be conflated.
- Public reports include append-only case diagnostics without breaking legacy fields.
- Default v3 route and explicit v1 fallback are both covered.
- Kernel trace default-off behavior is covered.
- Answer support/citation/unsupported status is represented in case diagnostics.
- LongMemEval and LoCoMo limit-30 milestone reports are generated separately, or exact LLM/data blocker is recorded.
- No benchmark improvement is claimed from diagnostics alone.
