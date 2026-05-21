# phase: phase-2

# Phase 2 Evidence Harness Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a diagnostic-only, append-only case taxonomy to the real v3 public benchmark path for LongMemEval and LoCoMo.

**Architecture:** Add a small taxonomy layer that consumes existing `PublicBenchmarkResult` ingredients, deterministic citation support from `agent_answer_eval`, v3 context diagnostics, and judge status. Wire its output into `PublicBenchmarkResult.to_report()` without removing legacy fields. Keep v3 default, explicit v1 fallback, and kernel opt-in verified by tests.

**Tech Stack:** Python 3.11+, dataclasses/Pydantic-adjacent dict reports, pytest, ruff, existing `uv run memoryos eval public` CLI.

---

## Files

- Create: `src/memoryos_lite/public_case_diagnostics.py`
  - Owns deterministic status enums, id extraction, failure-class precedence, and movement calculation.
- Create: `src/memoryos_lite/public_case_movement.py`
  - Loads previous public JSON reports and returns baseline verdicts keyed by `(benchmark, baseline, case_id)`.
- Modify: `src/memoryos_lite/public_benchmarks.py`
  - Add append-only fields to `PublicBenchmarkResult`.
  - Call the taxonomy builder inside `_to_public_result`.
  - Accept comparison report paths and pass baseline verdict/source into the taxonomy builder.
  - Preserve partial/final JSON report compatibility.
- Modify: `src/memoryos_lite/engine.py`
  - Fix default v3 routing so `resolved_memory_arch == "v3"` is sufficient.
  - Preserve explicit `memoryos_memory_arch="v1"` fallback.
- Modify: `src/memoryos_lite/diagnostic_report.py`
  - Prefer `case_diagnostics.failure_class` when present.
  - Keep loading older JSON reports by ignoring unknown fields.
- Modify: `src/memoryos_lite/cli.py`
  - Keep existing `PUBLIC_TABLE_COLUMNS`.
  - Add an explicit additive `--comparison-report PATH` option for `memoryos eval public`.
  - Optionally add additive summary columns only after JSON compatibility tests pass.
- Test: `tests/test_public_benchmarks.py`
  - Primary RED tests for taxonomy wiring, compatibility, source-hit separation, v3 default, v1 fallback, and kernel opt-in.
- Test: `tests/test_agent_answer_eval.py`
  - Add focused answer-support tests only if `evaluate_agent_answer()` requires a small helper extension.
- Test: `tests/test_llm_judge.py`
  - Add judge-status classification fixture only if error/questionable handling needs direct judge parsing coverage.

Do not edit quarantined control files: `.hermes-loop/blueprint.md`, `.hermes-loop/config.json`, `.hermes-loop/god_launcher.sh`, `.hermes-loop/god_loop_prompt.md`, `.hermes-loop/hermes_loop.py`, `.hermes-loop/hermes_reporter.py`, `AGENTS.md`, `CLAUDE.md`.

## RED

### Task 1: Add taxonomy RED tests that force evidence-hit answer failure

**Files:**
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add `test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail`.

Test shape:

```python
def test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail(tmp_path):
    data_path = tmp_path / "locomo_taxonomy.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_taxonomy",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The supported marker is MemoryOS Lite.",
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:2",
                                "text": "A distractor says the marker is ArchiveBox.",
                            },
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the supported marker?",
                            "answer": "NeverReturnedExpectedToken",
                            "evidence": ["D1:1"],
                        },
                        {
                            "question": "What is the absent marker?",
                            "answer": "Not in memory",
                            "evidence": ["D9:9"],
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")
    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase2-taxonomy-red",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )
    reports = {result.case_id: result.to_report() for result in results}

    hit = reports["sample_taxonomy_qa_001"]["case_diagnostics"]
    miss = reports["sample_taxonomy_qa_002"]["case_diagnostics"]

    assert hit["retrieval_status"] == "evidence_retrieved"
    assert hit["selected_context_status"] == "evidence_selected"
    assert hit["rendered_context_status"] == "evidence_rendered"
    assert reports["sample_taxonomy_qa_001"]["verdict"] == "fail"
    assert hit["failure_class"] == "evidence_hit_answer_fail"
    assert miss["failure_class"] == "retrieval_miss"
    assert hit["failure_class"] != miss["failure_class"]
```

Do not allow this test to pass with `supported_cited_answer`, `unsupported_answer`, or any generic non-retrieval failure for the evidence-hit case. If the fixture does not retrieve/select/render `D1:1`, adjust only the fixture wording or test helper setup; do not change retrieval ranking, prompts, or case-id logic.

- [ ] Add `test_public_benchmark_case_diagnostics_classifies_unsupported_answer_separately`.

Use a direct diagnostics-builder fixture after the builder exists, or a public-report fixture if answer support is already wired. Required assertions:

```python
diagnostics = build_case_diagnostics(
    benchmark="locomo",
    baseline="memoryos_lite",
    case_id="unsupported-demo",
    memory_arch="v1",
    answer="The answer is unsupported. [source:bad-id]",
    answer_mode="llm",
    verdict="fail",
    reasoning="judge fail",
    expected_source_ids=["good-id"],
    retrieval_candidate_source_ids=["good-id"],
    episode_candidate_message_ids=[],
    planned_evidence_message_ids=[],
    source_ids=["good-id"],
    v3_context={},
    v3_diagnostics=[],
    kernel_trace_events=[],
    baseline_verdict=None,
    movement_baseline_source=None,
)
assert diagnostics["answer_support_status"] == "unsupported_answer"
assert diagnostics["failure_class"] == "unsupported_answer"
```

- [ ] Run RED:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_classifies_unsupported_answer_separately -q
```

Expected: FAIL because `case_diagnostics` and the diagnostics builder are absent.

### Task 2: Add movement, compatibility, partial-report, and source-hit RED tests

**Files:**
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add `test_public_case_movement_from_comparison_report_pairs`.

Use a temp previous public report file with four rows and a current run/report with matching keys. The test may call the movement loader directly before public-run wiring exists.

Previous report fixture:

```python
previous_rows = [
    {"benchmark": "locomo", "baseline": "memoryos_lite", "case_id": "case-pass-to-fail", "verdict": "pass"},
    {"benchmark": "locomo", "baseline": "memoryos_lite", "case_id": "case-fail-to-pass", "verdict": "fail"},
    {"benchmark": "locomo", "baseline": "memoryos_lite", "case_id": "case-unchanged-pass", "verdict": "pass"},
    {"benchmark": "locomo", "baseline": "memoryos_lite", "case_id": "case-unchanged-fail", "verdict": "fail"},
]
```

Required assertions:

```python
comparison = load_public_case_movement([previous_report_path])
assert comparison[("locomo", "memoryos_lite", "case-pass-to-fail")].verdict == "pass"

assert movement_status("pass", "fail") == "pass_to_fail"
assert movement_status("fail", "pass") == "fail_to_pass"
assert movement_status("pass", "pass") == "unchanged_pass"
assert movement_status("fail", "fail") == "unchanged_fail"
assert movement_status("error", "fail") == "unchanged_fail"
```

- [ ] Add `test_public_case_movement_missing_baseline_is_not_anti_demo_evidence`.

Required assertions:

```python
diagnostics = build_case_diagnostics(
    benchmark="locomo",
    baseline="memoryos_lite",
    case_id="missing-baseline",
    memory_arch="v3",
    answer="MemoryOS Lite",
    answer_mode="projected",
    verdict="pass",
    reasoning="exact substring match",
    expected_source_ids=["D1:1"],
    retrieval_candidate_source_ids=["D1:1"],
    episode_candidate_message_ids=[],
    planned_evidence_message_ids=[],
    source_ids=["D1:1"],
    v3_context={},
    v3_diagnostics=[],
    kernel_trace_events=[],
    baseline_verdict=None,
    movement_baseline_source=None,
)
assert diagnostics["movement_status"] == "new_case_no_baseline"
assert diagnostics["baseline_verdict"] is None
assert any("missing baseline" in note for note in diagnostics["diagnostic_notes"])
```

This status may appear in JSON, but the review/ACK checklist must treat it as insufficient for pass-to-fail/fail-to-pass/unchanged movement evidence.

- [ ] Add `test_public_benchmark_movement_status_uses_comparison_report`.

Use a one-case public fixture whose current deterministic result is `fail`, and write a previous report row for the same `(benchmark, baseline, case_id)` with `verdict == "pass"`.

Required assertions:

```python
results = run_public_benchmark(
    settings,
    benchmark="locomo",
    data_path=data_path,
    run_id="phase2-movement-wiring",
    baselines=["memoryos_lite"],
    llm_answer=False,
    llm_judge=False,
    comparison_report_paths=[previous_report_path],
)
report = results[0].to_report()
assert report["verdict"] == "fail"
assert report["movement_status"] == "pass_to_fail"
assert report["case_diagnostics"]["baseline_verdict"] == "pass"
assert report["case_diagnostics"]["movement_baseline_source"] == str(previous_report_path)
```

- [ ] Add `test_public_benchmark_case_diagnostics_are_append_only`.

Required assertions:

```python
report = results[0].to_report()
legacy_fields = {
    "benchmark",
    "baseline",
    "case_id",
    "answer",
    "verdict",
    "source_hit",
    "source_hit_at_k",
    "episode_candidate_message_ids",
    "planned_evidence_message_ids",
    "v3_diagnostics",
    "kernel_trace_events",
    "pass",
}
assert legacy_fields <= set(report)
assert "case_diagnostics" in report
assert report["failure_class"] == report["case_diagnostics"]["failure_class"]
assert report["source_hit"] in {True, False, None}
assert report["case_diagnostics"]["source_hit_semantics"] == "final_projection_source_overlap"
```

- [ ] Add `test_public_benchmark_partial_and_final_reports_have_diagnostic_schema_parity`.

Run `run_public_benchmark(...)`, then read both files:

```python
partial_path = settings.data_dir / "evals" / "phase2-partial-schema_locomo.partial.json"
final_path = settings.data_dir / "evals" / "phase2-partial-schema_locomo.json"
partial_rows = json.loads(partial_path.read_text(encoding="utf-8"))
final_rows = json.loads(final_path.read_text(encoding="utf-8"))

mirror_fields = {"case_diagnostics", "failure_class", "movement_status", "answer_support_status", "judge_status"}
assert mirror_fields <= set(partial_rows[-1])
assert mirror_fields <= set(final_rows[-1])
assert set(partial_rows[-1]["case_diagnostics"]) == set(final_rows[-1]["case_diagnostics"])
for field in mirror_fields - {"case_diagnostics"}:
    assert partial_rows[-1][field] == partial_rows[-1]["case_diagnostics"][field]
    assert final_rows[-1][field] == final_rows[-1]["case_diagnostics"][field]
```

- [ ] Add `test_public_benchmark_source_hit_is_not_retrieval_localization`.

Required assertions:

```python
diagnostics = report["case_diagnostics"]
assert "retrieved_evidence_ids" in diagnostics
assert "selected_context_ids" in diagnostics
assert "rendered_evidence_ids" in diagnostics
assert diagnostics["retrieved_evidence_ids"] != []
assert report["source_hit"] is False or report["verdict"] == "fail"
assert diagnostics["failure_class"] != "retrieval_miss"
```

Use a fixture where expected evidence is retrieved/rendered but the deterministic projected answer does not contain the expected answer. Do not change prompts or retrieval ranking to make the case pass.

- [ ] Run RED:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs tests/test_public_benchmarks.py::test_public_case_movement_missing_baseline_is_not_anti_demo_evidence tests/test_public_benchmarks.py::test_public_benchmark_movement_status_uses_comparison_report tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_partial_and_final_reports_have_diagnostic_schema_parity tests/test_public_benchmarks.py::test_public_benchmark_source_hit_is_not_retrieval_localization -q
```

Expected: FAIL because the movement loader and new diagnostics fields are absent.

### Task 3: Add v3 default, v1 fallback, and kernel opt-in tests

**Files:**
- Modify: `tests/test_public_benchmarks.py`

- [ ] Change or add `test_public_benchmark_reports_v3_context_diagnostics_by_default`.

Use `Settings(data_dir=tmp_path / ".memoryos")` with no explicit `memoryos_memory_arch`. Required assertions:

```python
report = results[0].to_report()
assert report["memory_arch"] == "v3"
assert report["v3_diagnostics"]
assert report["case_diagnostics"]["memory_arch"] == "v3"
```

- [ ] Add `test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context`.

Use `Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")`. Required assertions:

```python
report = results[0].to_report()
assert report["memory_arch"] != "v3"
assert report["v3_diagnostics"] == []
assert report["case_diagnostics"]["memory_arch"] in {None, "v1"}
```

- [ ] Add `test_public_benchmark_kernel_trace_remains_default_off`.

Use default settings. Required assertions:

```python
report = results[0].to_report()
assert report["kernel_trace_events"] == []
assert report["case_diagnostics"]["kernel_trace_present"] is False
```

- [ ] Keep existing explicit kernel test and extend it:

```python
assert report["kernel_trace_events"]
assert report["case_diagnostics"]["kernel_trace_present"] is True
assert report["case_diagnostics"]["failure_class"] in {
    "supported_cited_answer",
    "evidence_hit_answer_fail",
    "unsupported_answer",
    "judge_questionable",
    "retrieval_miss",
    "context_missing_evidence",
}
```

- [ ] Run RED:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics_by_default tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q
```

Expected: at least the default-v3 test fails because `engine._should_route_to_v3_context()` currently requires `memoryos_memory_arch` in `model_fields_set`.

## GREEN

### Task 4: Create the movement and taxonomy modules

**Files:**
- Create: `src/memoryos_lite/public_case_movement.py`
- Create: `src/memoryos_lite/public_case_diagnostics.py`

- [ ] Add `src/memoryos_lite/public_case_movement.py` with this contract:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class BaselineCaseVerdict:
    benchmark: str
    baseline: str
    case_id: str
    verdict: str
    source: str

MovementKey = tuple[str, str, str]

def load_public_case_movement(paths: Iterable[Path]) -> dict[MovementKey, BaselineCaseVerdict]:
    ...

def movement_status(baseline_verdict: str | None, current_verdict: str) -> str:
    ...
```

Rules:

- Read each path as the existing public JSON list format.
- Accept legacy rows with `verdict` or boolean `pass`.
- Normalize benchmark, baseline, and case id to strings; key by `(benchmark, baseline, case_id)`.
- Only `pass`, `fail`, and `error` are valid verdict values. Raise `ValueError` for any other comparison verdict so bad baselines do not silently produce movement fields.
- Later paths override earlier paths for the same key.
- `movement_status(None, current)` returns `new_case_no_baseline`.
- `movement_status("pass", "fail")` returns `pass_to_fail`.
- `movement_status("fail", "pass")` and `movement_status("error", "pass")` return `fail_to_pass`.
- matching `pass` returns `unchanged_pass`.
- all other non-pass current statuses with previous `fail` or `error` return `unchanged_fail`.

- [ ] Add a pure diagnostics builder function with this interface:

```python
def build_case_diagnostics(
    *,
    benchmark: str,
    baseline: str,
    case_id: str,
    memory_arch: str | None,
    answer: str,
    answer_mode: str,
    verdict: str,
    reasoning: str,
    expected_source_ids: list[str],
    retrieval_candidate_source_ids: list[str],
    episode_candidate_message_ids: list[str],
    planned_evidence_message_ids: list[str],
    source_ids: list[str],
    v3_context: dict[str, object],
    v3_diagnostics: list[dict[str, object]],
    kernel_trace_events: list[str],
    baseline_verdict: str | None = None,
    movement_baseline_source: str | None = None,
) -> dict[str, object]:
    ...
```

- [ ] Derive ids deterministically:
  - `retrieved_evidence_ids`: de-duplicated union of `retrieval_candidate_source_ids`, `episode_candidate_message_ids`, and `planned_evidence_message_ids`.
  - `selected_context_ids`: source ids from included v3 diagnostics and v3 context items; fall back to `retrieved_evidence_ids` for v1/v2 where selected ids are not separately represented.
  - `rendered_evidence_ids`: de-duplicated `source_ids` because `BaselineOutput.sources` is what projected answers and LLM answers receive.
  - `cited_source_ids` and `unsupported_citation_ids`: from `memoryos_lite.agent_answer_eval.evaluate_agent_answer(answer, rendered_evidence_ids)`.

- [ ] Implement the status and `failure_class` precedence exactly as specified in `spec.md`.
- [ ] Treat `answer_mode == "projected"` with expected evidence rendered and `verdict == "fail"` as `evidence_hit_answer_fail`, not `unsupported_answer`, when there are no unsupported citation ids. `unsupported_answer` is reserved for unsupported content/citations/refusal failures, not every projected answer miss.

- [ ] Implement movement status by calling `movement_status(baseline_verdict, verdict)` from `public_case_movement.py`.
- [ ] Include `baseline_verdict` and `movement_baseline_source` in `case_diagnostics`.
- [ ] When `baseline_verdict is None`, add a note like `missing baseline comparison for locomo/memoryos_lite/sample_taxonomy_qa_001`; this note is required so missing baseline data cannot masquerade as anti-demo movement evidence.

- [ ] Run focused tests:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs tests/test_public_benchmarks.py::test_public_case_movement_missing_baseline_is_not_anti_demo_evidence tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_classifies_unsupported_answer_separately -q
```

Expected: PASS for direct movement/taxonomy tests; public benchmark wiring tests still fail until Task 5.

### Task 5: Wire diagnostics into public benchmark reports

**Files:**
- Modify: `src/memoryos_lite/public_benchmarks.py`

- [ ] Import `build_case_diagnostics`.
- [ ] Import `load_public_case_movement`; import movement types only if they are used in annotations.
- [ ] Add fields to `PublicBenchmarkResult`:

```python
case_diagnostics: dict[str, Any] = field(default_factory=dict)
failure_class: str = "unknown"
movement_status: str = "new_case_no_baseline"
answer_support_status: str = "unknown"
judge_status: str = "unknown"
```

- [ ] Extend `run_public_benchmark` with an explicit comparison input:

```python
def run_public_benchmark(
    settings: Settings,
    benchmark: str,
    data_path: Path,
    run_id: str,
    baselines: list[str],
    limit: int | None = None,
    llm_answer: bool = False,
    llm_judge: bool = False,
    isolated: bool = True,
    comparison_report_paths: list[Path] | None = None,
) -> list[PublicBenchmarkResult]:
    comparison = load_public_case_movement(comparison_report_paths or [])
    ...
```

- [ ] For each result, lookup baseline comparison before `_to_public_result`:

```python
comparison_key = (public_case.benchmark, baseline, public_case.case.case_id)
baseline_case = comparison.get(comparison_key)
baseline_verdict = baseline_case.verdict if baseline_case is not None else None
movement_baseline_source = baseline_case.source if baseline_case is not None else None
```

- [ ] Extend `_to_public_result(...)` with `baseline_verdict: str | None` and `movement_baseline_source: str | None` parameters.
- [ ] In `_to_public_result`, build diagnostics after current overlap/session calculations and before returning `PublicBenchmarkResult`.
- [ ] Populate the mirror fields from the diagnostics object.
- [ ] Do not remove or rename existing fields.
- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail tests/test_public_benchmarks.py::test_public_benchmark_movement_status_uses_comparison_report tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_partial_and_final_reports_have_diagnostic_schema_parity tests/test_public_benchmarks.py::test_public_benchmark_source_hit_is_not_retrieval_localization -q
```

Expected: PASS except for any v3 default-route test still blocked by engine routing.

### Task 6: Fix real v3 default routing while preserving v1 fallback

**Files:**
- Modify: `src/memoryos_lite/engine.py`

- [ ] Change `_should_route_to_v3_context()` to route whenever `self.settings.resolved_memory_arch == "v3"`.
- [ ] Keep the existing `resolved_memory_arch != "v3"` guard for v1 fallback.
- [ ] Do not enable kernel behavior in this method.
- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics_by_default tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context -q
```

Expected: PASS.

### Task 7: Preserve kernel opt-in diagnostics

**Files:**
- Modify only if tests fail: `src/memoryos_lite/public_case_diagnostics.py`, `src/memoryos_lite/public_benchmarks.py`

- [ ] Ensure default reports keep `kernel_trace_events == []`.
- [ ] Ensure `case_diagnostics.kernel_trace_present` mirrors `bool(kernel_trace_events)`.
- [ ] Ensure `failure_class` never becomes pass because kernel trace exists.
- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected: PASS.

### Task 8: Update diagnostic report loading and breakdown

**Files:**
- Modify: `src/memoryos_lite/diagnostic_report.py`
- Modify: `src/memoryos_lite/cli.py`

- [ ] Update `classify_failure(result)` to return `result.case_diagnostics["failure_class"]` when present.
- [ ] Keep the old source-hit-based fallback for reports without `case_diagnostics`.
- [ ] Keep `load_results()` filtering unknown fields through `PublicBenchmarkResult.__dataclass_fields__`.
- [ ] Add `comparison_report: Annotated[list[str] | None, Option("--comparison-report", help="Previous public JSON report used for case movement status")] = None` to `eval_public`.
- [ ] Pass `comparison_report_paths=[Path(path) for path in comparison_report or []]` into `run_public_benchmark`.
- [ ] Do not require comparison reports for normal public evals; missing data must flow to `new_case_no_baseline`.
- [ ] If CLI table columns change, add only additive columns and keep all current `PUBLIC_TABLE_COLUMNS` names rendering.
- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_cli_public_helpers_import_without_agent_answer_eval tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs -q
```

Expected: PASS.

## REFACTOR

### Task 9: Tighten names and docs inside code

**Files:**
- Modify: `src/memoryos_lite/public_case_diagnostics.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`

- [ ] Keep status string constants in one module.
- [ ] Add one short code comment only where `source_hit` is intentionally separated from retrieval evidence ids.
- [ ] Remove duplicate id-normalization logic.
- [ ] Keep benchmark-specific logic out of the taxonomy builder. Inputs are ids and verdicts, not hardcoded LongMemEval or LoCoMo case ids.
- [ ] Run focused regression:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py tests/test_llm_judge.py -q
```

Expected: PASS.

## Smoke

### Task 10: Full local smoke

- [ ] Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] Run:

```bash
uv run ruff check .
```

Expected: no lint errors.

If either command fails, do not proceed to milestone eval. Fix the failing focused area first.

## Milestone Eval

### Task 11: Run public benchmark milestone commands

- [ ] Run LongMemEval full-chain v3 milestone:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase0_v3_lme_5case_longmemeval.json
```

- [ ] Run LoCoMo full-chain v3 milestone:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase0_v3_locomo_5case_locomo.json
```

These Phase 0 comparison reports provide executable baseline verdicts for the known smoke rows only. Any limit-30 row absent from the comparison report must be listed as `new_case_no_baseline` and cannot be counted as movement evidence. If either comparison report is missing, record the exact missing path and run without `--comparison-report`; the phase may still produce diagnostics, but it cannot claim the anti-demo movement requirement is satisfied.

- [ ] If provider/model/data access blocks full-chain answer or judge, record the exact command, exit/error text, missing variable, and whether fallback no-LLM smoke was run. Fallback commands:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --comparison-report .memoryos/evals/phase0_v3_lme_5case_longmemeval.json \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --comparison-report .memoryos/evals/phase0_v3_locomo_5case_locomo.json \
  --no-llm-answer \
  --no-llm-judge
```

Fallback-only evidence does not satisfy the mandatory full-chain milestone.

Primary full-chain report rows must have `case_diagnostics.answer_mode == "llm"` and `case_diagnostics.judge_status != "not_run"`. If any primary row lacks those values, reject the milestone evidence unless the result artifact records the exact provider/data blocker that prevented LLM answer or judge execution.

### Task 12: Produce case-level analysis from generated JSON

The execute lane may write phase-local result artifacts later, but this planning lane must not write them.

Required analysis sections for each benchmark:

- `pass_rate` and total cases.
- `retrieval_miss` case ids.
- `context_missing_evidence` case ids.
- `evidence_hit_answer_fail` case ids.
- `unsupported_answer` case ids.
- `supported_cited_answer` case ids.
- `judge_questionable` case ids.
- `fail_to_pass` case ids.
- `pass_to_fail` case ids.
- `unchanged_pass` case ids.
- `unchanged_fail` case ids.
- `new_case_no_baseline` case ids, with a note that these do not satisfy movement evidence.
- `movement_baseline_source` coverage: count rows with a non-null source and list missing comparison keys.
- `answer_mode` coverage: count `case_diagnostics.answer_mode` values per benchmark and list any rows that are not `llm` in primary full-chain reports.
- `judge_status` coverage: count `case_diagnostics.judge_status` values per benchmark and list any primary full-chain rows with `judge_status == "not_run"`.
- Representative `expected_source_ids`, `retrieved_evidence_ids`, `selected_context_ids`, `rendered_evidence_ids`, and `cited_source_ids`.

The later `result.md` and ACK gating must read `case_diagnostics.answer_mode` and `case_diagnostics.judge_status` from the generated JSON reports. Deterministic fallback rows with `answer_mode == "projected"` or `judge_status == "not_run"` must be labeled fallback-only and cannot satisfy the full-chain milestone.

Known Phase 0 smoke labels may be used as comparison evidence in analysis, not as runtime classification rules:

```text
LongMemEval pass: 1e043500
LongMemEval retrieval miss: 58bf7951
LongMemEval evidence-hit answer failures: e47becba, 118b2229, 51a45a95
LoCoMo evidence-hit answer failure: conv-26_qa_001
LoCoMo retrieval/scope misses: conv-26_qa_002, conv-26_qa_003, conv-26_qa_004, conv-26_qa_005
```

## Review

### Task 13: Review gates before ACK

Reject the phase as partial or demo-only if any of these are true:

- Diagnostics are only markdown and are not wired into `run_public_benchmark`.
- Public JSON lacks per-case `case_diagnostics`.
- `retrieval_miss` and `evidence_hit_answer_fail` can collapse into one status.
- `source_hit` is used as proof of retrieval localization.
- LongMemEval and LoCoMo are combined without separate case-level lists.
- Pass-to-fail regressions are hidden behind aggregate pass rate.
- Movement fields are all `new_case_no_baseline` or are produced without an executable comparison report source.
- Missing baseline rows are counted as satisfying pass-to-fail/fail-to-pass/unchanged movement evidence.
- Full-chain LLM judge milestone is skipped without an exact blocker.
- Primary full-chain milestone report rows do not have `case_diagnostics.answer_mode == "llm"` or have `case_diagnostics.judge_status == "not_run"`, unless an exact provider/data blocker is recorded.
- `result.md` or ACK evidence does not report answer-mode coverage and judge-status coverage separately for LongMemEval and LoCoMo.
- Any retrieval ranking, answer prompt, archive scope, kernel tool, or case-id hack is introduced.
- `MEMORYOS_AGENT_KERNEL=v1` becomes default or changes answer classification.
- Explicit v1 fallback breaks.
- Quarantined control files are edited.

### Task 14: Final verification command set

Run before requesting review:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py tests/test_llm_judge.py -q
uv run pytest -q
uv run ruff check .
```

Expected: all pass.
