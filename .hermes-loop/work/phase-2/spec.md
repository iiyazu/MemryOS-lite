# phase: phase-2

# Phase 2 Spec - Evidence Harness And Failure Taxonomy

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase 2 builds a diagnostic evidence harness on the real public benchmark path. It must classify each case by where the chain failed: retrieval, v3 context selection, answer-context rendering, answer citation/support, judge behavior, or optional kernel trace. This phase is diagnostic-only. It must not optimize retrieval, tune answer prompts, expand kernel tools, or claim benchmark improvement from added reporting.

The usable outcome is a public report contract that lets later phases prioritize retrieval/scope work and answer-projection work from case-level evidence instead of aggregate pass rate.

## Real v3/Public Benchmark Path To Wire

Diagnostics must be emitted from the existing runtime path:

```text
memoryos eval public
  -> src/memoryos_lite/cli.py::eval_public
  -> src/memoryos_lite/public_benchmarks.py::run_public_benchmark
  -> src/memoryos_lite/evals.py::_run_baseline("memoryos_lite")
  -> src/memoryos_lite/engine.py::MemoryOSService.build_context
  -> v3 ContextComposer by default
  -> src/memoryos_lite/evals.py::BaselineOutput
  -> src/memoryos_lite/public_benchmarks.py::_to_public_result
  -> PublicBenchmarkResult.to_report()
  -> JSON report and partial JSON report
```

For full-chain runs, the same path also includes:

```text
BaselineOutput.sources
  -> PublicAnswerer.answer(...)
  -> LLMJudge.judge(...)
  -> PublicBenchmarkResult
  -> case_diagnostics
```

When `MEMORYOS_AGENT_KERNEL=v1` is explicitly set, the existing kernel probe trace may be recorded as audit evidence. Kernel trace presence must never change answer pass/fail classification.

The default v3 route must be real, not only documented. `Settings(data_dir=...)` must produce `memory_arch == "v3"` and v3 diagnostics in the public benchmark path. Explicit `MEMORYOS_MEMORY_ARCH=v1` must continue to route to the legacy path.

## Diagnostics Contract

Every public benchmark case report for `memoryos_lite` must include a deterministic `case_diagnostics` object. Existing top-level fields remain append-only and backwards-compatible.

Required status values:

- `retrieval_status`: `evidence_retrieved`, `retrieval_miss`, `no_expected_evidence`, `unknown`.
- `selected_context_status`: `evidence_selected`, `context_missing_evidence`, `no_expected_evidence`, `unknown`.
- `rendered_context_status`: `evidence_rendered`, `rendered_context_missing_evidence`, `no_expected_evidence`, `unknown`.
- `answer_support_status`: `supported_cited_answer`, `unsupported_answer`, `refused_no_evidence`, `no_citation`, `projected_unverified`, `unknown`.
- `judge_status`: `pass`, `fail`, `error`, `not_run`, `questionable`.
- `movement_status`: `unchanged_pass`, `unchanged_fail`, `fail_to_pass`, `pass_to_fail`, `new_case_no_baseline`.
- `failure_class`: `retrieval_miss`, `context_missing_evidence`, `unsupported_answer`, `evidence_hit_answer_fail`, `judge_questionable`, `supported_cited_answer`, `unknown`.

## Baseline Comparison And Movement Contract

Movement status must be computed from executable comparison data, not from notes or an optional always-empty argument.

Implementation contract:

- Add a comparison-report loader that accepts one or more previous public benchmark JSON report paths and returns a map keyed by `(benchmark, baseline, case_id)`.
- The accepted source format is the existing public JSON report emitted by `memoryos eval public`; both legacy reports and new phase-2 reports must load.
- A baseline verdict is read from `verdict` when present, otherwise from boolean `pass`; only `pass`, `fail`, and `error` are valid comparison verdicts.
- `run_public_benchmark(...)` must accept an explicit comparison report path/list argument and pass the matching baseline verdict into the case diagnostic builder.
- `memoryos eval public` must expose the same input through an explicit CLI option such as `--comparison-report PATH`, so milestone runs can produce movement fields from a real previous report.
- Comparison keys must include benchmark, baseline, and case id. Do not compare LongMemEval against LoCoMo, `sliding_window` against `memoryos_lite`, or one case id against another.
- Missing comparison data yields `movement_status == "new_case_no_baseline"` and a diagnostic note naming the missing key.
- `new_case_no_baseline` is allowed in reports, but it cannot satisfy anti-demo movement requirements. Usable ACK requires `pass_to_fail`, `fail_to_pass`, `unchanged_pass`, and `unchanged_fail` lists to be generated from non-missing comparison entries, or an exact blocker explaining why comparison data could not be produced.

Failure-class precedence:

1. `retrieval_miss`: expected source ids appear in none of retrieved/planned/selected/rendered evidence ids.
2. `context_missing_evidence`: expected source ids were retrieved or planned but did not survive into selected/rendered context.
3. `unsupported_answer`: the final answer is non-refusal content without selected/rendered evidence support, or cites ids outside selected/rendered evidence.
4. `evidence_hit_answer_fail`: expected evidence reached selected/rendered context but answer projection or judge still failed.
5. `judge_questionable`: deterministic evidence/support signals conflict with judge verdict, or judge returned parse/provider error.
6. `supported_cited_answer`: answer passes and cites selected/rendered evidence, or deterministic projected mode has expected answer and expected rendered evidence under the no-LLM contract.
7. `unknown`: required signals are absent. `unknown` in milestone cases blocks usable ACK unless an exact provider/data/report blocker is recorded.

`source_hit` remains final projection/source overlap. It must not be redefined as retrieval localization.

## Exact New/Changed Public Report Fields

New append-only top-level fields in `PublicBenchmarkResult.to_report()`:

- `case_diagnostics`: nested dict matching the schema below.
- `failure_class`: string mirror of `case_diagnostics.failure_class`.
- `movement_status`: string mirror of `case_diagnostics.movement_status`.
- `answer_support_status`: string mirror of `case_diagnostics.answer_support_status`.
- `judge_status`: string mirror of `case_diagnostics.judge_status`.

New `case_diagnostics` fields:

```text
schema_version: "phase-2.case-diagnostics.v1"
benchmark: str
case_id: str
baseline: str
memory_arch: "v1" | "v3" | null
answer_mode: "projected" | "llm"
expected_source_ids: list[str]
retrieved_evidence_ids: list[str]
retrieved_expected_evidence_ids: list[str]
selected_context_ids: list[str]
selected_expected_evidence_ids: list[str]
rendered_evidence_ids: list[str]
rendered_expected_evidence_ids: list[str]
cited_source_ids: list[str]
unsupported_citation_ids: list[str]
retrieval_status: str
selected_context_status: str
rendered_context_status: str
answer_support_status: str
judge_status: str
movement_status: str
baseline_verdict: "pass" | "fail" | "error" | null
movement_baseline_source: str | null
failure_class: str
source_hit_semantics: "final_projection_source_overlap"
kernel_trace_present: bool
kernel_trace_events: list[str]
diagnostic_notes: list[str]
```

Changed fields:

- No existing field may be removed, renamed, or repurposed.
- `source_hit`, `source_hit_at_k`, `episode_source_hit_at_10`, `planned_evidence_source_hit_at_5`, and v3 diagnostic fields keep their current meanings.
- `PUBLIC_TABLE_COLUMNS` may gain additive columns only if legacy columns still render. The JSON report is the authoritative case-level artifact.

## Compatibility Constraints

- `diagnostic_report.load_results()` must ignore unknown JSON fields and load reports containing the new append-only fields.
- Existing tests that assert public table rendering, v2 recall diagnostics, page diagnostics, and v3 context diagnostics must continue to pass.
- The partial report and final report must have the same diagnostic schema. Tests must read the `.partial.json` and final `.json` files produced by `run_public_benchmark()` and assert both include `case_diagnostics` plus mirror fields: `failure_class`, `movement_status`, `answer_support_status`, and `judge_status`.
- LongMemEval and LoCoMo must be reported separately. Combined-only aggregate reporting is not acceptable.
- Full-chain LLM judge runs must record `judge_status`. If provider/data/model access blocks them, the blocker must be recorded; deterministic no-LLM smoke is fallback evidence only.
- Usable ACK must reject milestone evidence unless every primary full-chain report row has `case_diagnostics.answer_mode == "llm"` and `case_diagnostics.judge_status != "not_run"`, unless an exact provider/data blocker is recorded. Fallback deterministic reports with `answer_mode == "projected"` or `judge_status == "not_run"` may be attached only as fallback evidence.

## v1 Fallback, v3 Default, Kernel Opt-In Constraints

- v3 default: `Settings()` and `Settings(data_dir=...)` resolve to v3 and must route public benchmark `memoryos_lite` through the v3 composer.
- v1 fallback: `Settings(memoryos_memory_arch="v1")` must still use the legacy v1 ContextBuilder path and must not fabricate v3 composer diagnostics.
- v2 recall pipeline: `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in and diagnostic-compatible.
- Kernel opt-in: `MEMORYOS_AGENT_KERNEL=v1` remains off by default. Default reports must have `kernel_trace_events == []` and `case_diagnostics.kernel_trace_present == false`.
- Kernel trace events are audit signals only; they must not promote a case to pass or change `failure_class` except through explicit `diagnostic_notes`.

## Non-Goals

- No retrieval ranking, BM25, archive, attachment-scope, or neighbor-window optimization.
- No answer prompt tuning or answer-quality optimization.
- No core-memory mutation expansion.
- No kernel tool expansion.
- No Letta runtime dependency.
- No benchmark case-id hacks, expected-answer leaks, or hardcoded public-case overrides.
- No aggregate-only success claims.
- No changes to quarantined control files.
- No enabling the v3 kernel by default.

## Acceptance Criteria For Usable ACK

Phase 2 is usable only when all criteria below are true:

- Diagnostics are wired into the real `memoryos eval public` / v3 public benchmark report path.
- RED tests prove `retrieval_miss` and `evidence_hit_answer_fail` cannot collapse into one generic failure. The evidence-hit case must have expected evidence retrieved/selected/rendered while projected or judged answer status fails, and it must assert `failure_class == "evidence_hit_answer_fail"`. A paired missing-evidence case must assert `failure_class == "retrieval_miss"`. `unsupported_answer` must have separate coverage and must not replace the evidence-hit-answer-fail contract.
- RED tests prove movement statuses can be produced from comparison data for `pass_to_fail`, `fail_to_pass`, `unchanged_pass`, and `unchanged_fail`; tests must also prove missing baseline data yields `new_case_no_baseline` and is reported as insufficient for anti-demo movement evidence.
- Public report compatibility is preserved with append-only fields.
- Partial and final JSON report files have schema parity for `case_diagnostics` and top-level mirror fields.
- `source_hit` is documented and tested as final projection/source overlap, separate from retrieved/selected/rendered evidence ids.
- `Settings(data_dir=...)` public eval uses v3 by default; explicit `memoryos_memory_arch="v1"` still falls back to v1.
- Kernel trace default-off and explicit opt-in behavior are covered by tests.
- LongMemEval and LoCoMo limit-30 milestone reports are generated separately, or exact provider/data blocker is recorded.
- Case-level analysis lists `fail_to_pass`, `pass_to_fail`, `unchanged_pass`, `unchanged_fail`, `retrieval_miss`, `context_missing_evidence`, `evidence_hit_answer_fail`, `unsupported_answer`, and `judge_questionable` separately for each benchmark.
- Case-level analysis, `result.md`, and ACK gating use `case_diagnostics.answer_mode` and `case_diagnostics.judge_status` from generated reports. Each benchmark must report answer-mode coverage and judge-status coverage so fallback no-LLM evidence cannot be mistaken for full-chain evidence.
- No benchmark improvement is claimed from diagnostics alone.
