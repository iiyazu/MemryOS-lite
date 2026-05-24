# phase: phase-17

# Phase 17 Implementation Plan

Context bundle: `work/phase-17/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Review promotion note:

- Promoted from `work/phase-17/plan.md` after PASS in `work/phase-17/plan_review.md`.
- Treat this reviewed plan and `work/phase-17/spec.md` as authoritative for execution. Older dispatch metadata may contain command summaries that omit `--llm-answer` or `--llm-judge`; those summaries are stale under the current CLI and must not be used for full-chain gates.
- Every full-chain public eval command in this plan intentionally includes both `--llm-answer` and `--llm-judge`, because `memoryos eval public` currently defaults both options to `False`.
- The positive real-path repair-smoke test is structural/no-LLM wiring coverage only. It must execute only the sanitized and aliased `ToolExecutionRequest`; raw baseline report source ids, case ids, expected answers, expected source ids, judge labels, failure classes, and movement labels remain report/validation inputs only and must not enter executable tool arguments.

> For agentic workers: REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task by task. Use `superpowers:test-driven-development` for every source change. Do not edit `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, ACK files, or benchmark fixtures during execution.

**Goal:** Build an explicit opt-in LoCoMo repair-smoke harness that executes approved Phase 16 kernel maintenance tools in an isolated repair store, reruns the real public v3 path, and reports case-level movement without claiming benchmark quality from same-slice or no-LLM evidence.

**Architecture:** Add a narrow `public_repair_smoke` helper module, route it through `run_public_benchmark` only when an explicit repair baseline report is provided, and add a private pre-context hook to the existing `memoryos_lite` baseline path in `evals.py`. Default public v3 behavior, v1 fallback, and kernel default-off behavior remain unchanged.

**Tech Stack:** Python 3.11+, Pydantic models, Typer CLI, SQLite `MemoryStore`, existing v3 context composer, existing Phase 16 `SimpleAgentStepRunner`.

---

## Files To Modify

- Create `src/memoryos_lite/public_repair_smoke.py`: validation, sanitization, kernel execution helper, comparison summary.
- Modify `src/memoryos_lite/evals.py`: add optional pre-context repair hook and carry repair trace/provenance in `BaselineOutput`.
- Modify `src/memoryos_lite/public_benchmarks.py`: add explicit repair-smoke mode, load baseline rows, route hook, emit repair fields and summary.
- Modify `src/memoryos_lite/cli.py`: add explicit repair-smoke CLI option requiring a baseline report.
- Modify `tests/test_public_benchmarks.py`: primary RED/GREEN coverage for gold denial, isolation, real hook routing, comparison movement, no-LLM gate labeling.
- Modify `tests/test_agent_kernel.py`: only if public tests cannot directly prove `SimpleAgentStepRunner.run_step()` is used for approved Level 1 requests.
- Modify `tests/test_context_composer.py`: v3 visibility guards for repair archive attachment and pending core candidates if existing Phase 16 tests do not cover the new repair-smoke provenance fields.
- Modify `tests/test_memory_lifecycle.py`: only if repair-smoke support touches lifecycle candidate behavior.

Do not modify source/test/eval/state/ACK/blueprint files outside execution. This plan draft itself is planning-only.

## RED Sequence

### Task 1: Gold-Leakage Denial Tests

**Files:**
- Create: `src/memoryos_lite/public_repair_smoke.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add RED test `test_repair_smoke_denies_gold_fields_in_executable_tool_request`.

Test intent:

```python
def test_repair_smoke_denies_gold_fields_in_executable_tool_request():
    from memoryos_lite.public_repair_smoke import build_executable_repair_proposal

    row = {
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "case_id": "case_gold_qa_001",
        "model_visible_planner_input": _model_visible_planner_input().model_dump(mode="json"),
        "eval_gold_sidecar": _eval_gold_sidecar().model_dump(mode="json"),
        "maintenance_proposal": {
            "proposal_type": "archive_write",
            "execution_mode": "proposal_only",
            "tool_name": "archive_write",
            "gold_fields_used": False,
            "arguments": {
                "content": "gold answer must not leak",
                "reason": "repair retrieval_miss unchanged_fail case_gold_qa_001",
            },
            "source_refs": [{"source_type": "message", "source_id": "msg_gold"}],
        },
    }

    proposal = build_executable_repair_proposal(
        row,
        source_id_aliases={"msg_selected": "repair_msg_001"},
    )

    assert proposal.executable is False
    assert proposal.denial_reason is not None
    assert "gold" in proposal.denial_reason or "forbidden" in proposal.denial_reason
    assert proposal.tool_request is None
```

- [ ] Add RED test `test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids`.

Test intent:

```python
def test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids():
    from memoryos_lite.public_repair_smoke import build_executable_repair_proposal

    model_visible = _model_visible_planner_input(
        selected_context_ids=["conv-26_qa_001:conv-26:D1:1"],
        rendered_evidence_ids=["conv-26_qa_001:conv-26:D1:1"],
        cited_source_ids=["conv-26_qa_001:conv-26:D1:1"],
        final_context_trace_source_ids=["conv-26_qa_001:conv-26:D1:1"],
        answer_evidence=[{"id": "conv-26_qa_001:conv-26:D1:1", "text": "visible evidence"}],
    )
    row = {
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "case_id": "conv-26_qa_001",
        "model_visible_planner_input": model_visible.model_dump(mode="json"),
        "eval_gold_sidecar": _eval_gold_sidecar().model_dump(mode="json"),
        "maintenance_proposal": {
            "proposal_type": "archive_write",
            "execution_mode": "proposal_only",
            "tool_name": "archive_write",
            "gold_fields_used": False,
            "arguments": {
                "content": "Visible answer from selected context.",
                "reason": "model-visible repair smoke",
            },
            "source_refs": [
                {"source_type": "message", "source_id": "conv-26_qa_001:conv-26:D1:1"}
            ],
        },
    }

    proposal = build_executable_repair_proposal(
        row,
        source_id_aliases={"conv-26_qa_001:conv-26:D1:1": "repair_msg_001"},
    )

    assert proposal.executable is True
    assert proposal.tool_request is not None
    serialized = proposal.tool_request.model_dump_json()
    assert "conv-26_qa_001" not in serialized
    assert "repair_msg_001" in serialized
```

- [ ] Run RED:

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_denies_gold_fields_in_executable_tool_request tests/test_public_benchmarks.py::test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids -q
```

Expected before implementation: import or assertion failure.

### Task 2: Minimal Sanitizer And Proposal Model

**Files:**
- Modify: `src/memoryos_lite/public_repair_smoke.py`

- [ ] Implement:
  - `ExecutableRepairProposal` Pydantic model with `executable`, `denial_reason`, `tool_request`, `provenance`.
  - `build_executable_repair_proposal(row, source_id_aliases)`.
  - Forbidden value scan using `eval_gold_sidecar` only for denial.
  - Allowed source set derived only from `model_visible_planner_input`.
  - Source-ref alias rewrite before constructing `ToolExecutionRequest`.
  - Tool allow-list from `executable_kernel_tool_names()`.

Implementation constraints:

- Do not pass `case_id`, `expected_answer`, `expected_source_ids`, verdict, judge status, failure class, or movement status into `ToolExecutionRequest.arguments`.
- Reject source refs absent from model-visible ids.
- Reject unaliased source refs containing LoCoMo case ids.
- Preserve `gold_fields_used is False`.
- Convert `execution_mode` from `proposal_only` to an executable request only inside this explicit repair-smoke helper.

- [ ] Run GREEN:

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_denies_gold_fields_in_executable_tool_request tests/test_public_benchmarks.py::test_repair_smoke_requires_model_visible_source_refs_and_rewrites_case_ids_to_repair_store_ids -q
```

Expected after implementation: `2 passed`.

## GREEN Sequence

### Task 3: Real Public Path Insertion Point

**Files:**
- Modify: `src/memoryos_lite/evals.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add RED test `test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context`.

Test intent:

```python
def test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_repair",
        text="Alice records the repair marker.",
        question="What marker does Alice record?",
        answer="repair marker",
    )
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps([
            {
                "benchmark": "locomo",
                "baseline": "memoryos_lite",
                "case_id": "sample_repair_qa_001",
                "model_visible_planner_input": {
                    "question": "What marker does Alice record?",
                    "rendered_answer": "Alice records the repair marker.",
                    "selected_context_ids": ["sample_repair_qa_001:sample_repair:D1:1"],
                    "final_context_trace_source_ids": ["sample_repair_qa_001:sample_repair:D1:1"],
                    "rendered_evidence_ids": ["sample_repair_qa_001:sample_repair:D1:1"],
                    "answer_evidence": [{"id": "sample_repair_qa_001:sample_repair:D1:1"}],
                    "cited_source_ids": ["sample_repair_qa_001:sample_repair:D1:1"],
                    "unsupported_citation_ids": [],
                    "citation_contract_status": "supported_cited_answer",
                    "archival_eligibility": {},
                    "component_drop_counts": {},
                    "kernel_trace_events": [],
                },
                "eval_gold_sidecar": {
                    "case_id": "sample_repair_qa_001",
                    "expected_answer": "repair marker",
                    "expected_source_ids": ["sample_repair_qa_001:sample_repair:D1:1"],
                    "verdict": "fail",
                    "judge_status": "judge_fail",
                    "failure_class": "retrieval_miss",
                    "movement_status": "unchanged_fail",
                },
                "maintenance_proposal": {
                    "proposal_type": "archive_write",
                    "execution_mode": "proposal_only",
                    "tool_name": "archive_write",
                    "arguments": {"content": "Alice records a model-visible context note."},
                    "source_refs": [
                        {"source_type": "message", "source_id": "sample_repair_qa_001:sample_repair:D1:1"}
                    ],
                    "gold_fields_used": False,
                },
            }
        ]),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-smoke-real-path",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )

    report = results[0].to_report()
    assert report["repair_smoke"]["enabled"] is True
    assert report["repair_smoke"]["executed_tool_names"] == ["archive_write"]
    serialized_repair = json.dumps(report["repair_smoke"], sort_keys=True)
    assert "repair marker" not in serialized_repair
    assert "sample_repair_qa_001:sample_repair:D1:1" not in serialized_repair
    assert "repair_msg_" in serialized_repair
    assert "tool_executed" in [
        event["event_type"] for event in report["repair_smoke"]["kernel_trace_events"]
    ]
    assert report["v3_context"]["metadata"]["archival_eligibility"]["eligible_archive_ids"]
```

- [ ] Add private hook type in `evals.py`, for example:
  - `PreContextHook = Callable[[MemoryOSService, EvalCase, list[Message], Any, Any], RepairHookResult]`.
  - Add optional `_run_baseline(..., pre_context_hook=None)`.
  - Invoke only inside `baseline == "memoryos_lite"` after `service.page(source_session.id)` and before `service.build_context(...)`.

- [ ] Keep default behavior byte-for-byte equivalent for callers that omit the hook.

- [ ] Run RED/GREEN:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context -q
```

Expected after implementation: `1 passed`.

### Task 4: Public Runner And CLI Opt-In

**Files:**
- Modify: `src/memoryos_lite/public_benchmarks.py`
- Modify: `src/memoryos_lite/cli.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add RED test `test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report`.

Assertions:

- With `memoryos_agent_kernel="off"` and a repair baseline report path, `run_public_benchmark` raises `ValueError` or writes repair denials without execution.
- With `memoryos_agent_kernel="v1"` but no repair baseline report path, normal opt-in kernel behavior remains the existing probe only; repair-smoke fields show disabled.
- With both explicit kernel and report path, repair smoke is enabled.

- [ ] Add `run_public_benchmark(..., repair_smoke_baseline_report_path: Path | None = None)` defaulting to `None`.

- [ ] Load repair rows keyed by `(benchmark, baseline, case_id)`.

- [ ] Require:
  - benchmark `locomo`;
  - baseline `memoryos_lite`;
  - `settings.resolved_memory_arch == "v3"`;
  - `settings.resolved_agent_kernel == "v1"`;
  - explicit baseline report path.

- [ ] Add CLI option:

```python
repair_smoke_baseline_report: Annotated[
    str | None,
    Option("--repair-smoke-baseline-report", help="Baseline public JSON report for explicit LoCoMo repair smoke"),
] = None
```

- [ ] Pass `Path(repair_smoke_baseline_report)` into `run_public_benchmark` only when provided.

- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report -q
```

Expected after implementation: `1 passed`.

### Task 5: Isolation And No Direct Fixture Writes

**Files:**
- Modify: `tests/test_public_benchmarks.py`
- Modify: `src/memoryos_lite/public_repair_smoke.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`

- [ ] Add RED test `test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run`.

Test must run:

1. Default `memoryos_agent_kernel="off"` public run.
2. Explicit repair-smoke run with `memoryos_agent_kernel="v1"`.
3. Another default run with a fresh run id.

Assertions:

- default reports have empty repair-smoke execution and empty kernel traces unless current existing opt-in probe is explicitly enabled;
- repair run has kernel tool execution through trace events;
- benchmark data file contents are unchanged;
- no repair artifacts from the repair run appear in the second default run.

- [ ] Ensure repair-smoke run uses only the existing isolated public eval `data_dir` for that run.

- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run -q
```

Expected after implementation: `1 passed`.

### Task 6: V3 Visibility And Lifecycle Boundaries

**Files:**
- Modify: `tests/test_context_composer.py`
- Modify: `tests/test_public_benchmarks.py`
- Modify: `src/memoryos_lite/public_repair_smoke.py`

- [ ] Add RED test `test_repair_smoke_archive_artifacts_are_visible_only_when_session_attached`.

Use an explicit repair archive write/attach path if available, or assert that `archive_write` creates same-session archival memory with session attachment through Phase 16 service verification and that v3 sees it only under eligible archive ids.

- [ ] Add RED test `test_repair_smoke_pending_core_candidates_do_not_render_as_core` only if the sanitizer allows `core_promotion_request` proposals. If sanitizer initially allows only `archive_write`, document `core_promotion_request` as denied in this slice and skip this test.

- [ ] Run:

```bash
uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q
```

Expected after implementation: pass with existing and new visibility guards.

## REFACTOR Sequence

### Task 7: Case-Level Repair Comparison Summary

**Files:**
- Modify: `src/memoryos_lite/public_repair_smoke.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add RED test `test_repair_smoke_comparison_report_lists_case_level_movement_and_source_metrics`.

Input: two baseline rows and two repair rows with one `fail_to_pass` and one `pass_to_fail`.

Expected summary keys:

```python
{
    "same_slice_repair_smoke_only": True,
    "full_chain_gate_status": "not_satisfied",
    "fail_to_pass": ["case_fail_to_pass"],
    "pass_to_fail": ["case_pass_to_fail"],
    "unchanged_fail": [],
    "unchanged_pass": [],
    "failure_classes": {
        "retrieval_miss": [...],
        "evidence_hit_answer_fail": [...],
        "context_missing_evidence": [...],
        "unsupported_answer": [...],
        "judge_questionable": [...],
        "source_miss_judge_pass": [...],
    },
    "source_metric_movement": {
        "source_hit": {"improved": [...], "regressed": [...]},
        "planned_evidence_source_hit_at_5": {"improved": [...], "regressed": [...]},
        "episode_source_hit_at_10": {"improved": [...], "regressed": [...]},
    },
}
```

- [ ] Write summary to:

```text
{settings.data_dir}/evals/{run_id}_{benchmark.lower()}_repair_smoke_summary.json
```

- [ ] Keep aggregate counts secondary to case lists.

- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_comparison_report_lists_case_level_movement_and_source_metrics -q
```

Expected after implementation: `1 passed`.

### Task 8: No-LLM Full-Chain Gate Labeling

**Files:**
- Modify: `src/memoryos_lite/public_repair_smoke.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] Add RED test `test_no_llm_repair_smoke_report_is_diagnostic_not_full_chain_gate`.

Assertions:

- when `llm_answer=False` or `llm_judge=False`, summary includes `answer_mode = "projected"` or equivalent;
- `full_chain_gate_status` is `not_satisfied`;
- summary contains a plain reason that no-LLM smoke is diagnostic only;
- no field says promotion or quality gate is satisfied.

- [ ] Add provider-error handling:
  - If answerer or judge construction/invocation fails during full-chain attempt, do not downgrade silently.
  - Record `full_chain_gate_status = "blocked_provider_unavailable"` in summary when provider access blocks answer/judge.
  - Keep no-LLM structural smoke available for wiring only.

- [ ] Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_no_llm_repair_smoke_report_is_diagnostic_not_full_chain_gate -q
```

Expected after implementation: `1 passed`.

### Task 9: Default Behavior Regression Tests

**Files:**
- Modify: `tests/test_public_benchmarks.py`
- Modify: `tests/test_context_composer.py`

- [ ] Run existing default-off and fallback tests:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q
```

Expected: all pass.

- [ ] If any default-off behavior changes, revert the behavior change and keep repair-smoke behind explicit options.

## Smoke Sequence

### Task 10: Focused Test Commands

Run:

```bash
uv run pytest tests/test_public_benchmarks.py -q
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q
```

Expected: all pass. Record exact counts in `result.md` during execution.

### Task 11: Baseline Checks

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: full suite passes and ruff passes. Record exact counts.

### Task 12: Fixed LoCoMo Full-Chain Baseline When Provider Exists

Run:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --run-id phase17_locomo10_baseline \
  --llm-answer \
  --llm-judge
```

Expected evidence:

- report path `.memoryos/evals/phase17_locomo10_baseline_locomo.json`;
- LLM answer and judge are enabled by the explicit `--llm-answer` and `--llm-judge` flags;
- case-level rows include diagnostics and source metrics.

If provider access is unavailable:

- record the exact error;
- set the phase evidence status to `blocked_provider_unavailable` for the full-chain gate;
- continue only with diagnostic structural smoke;
- do not claim quality improvement.

### Task 13: Explicit Opt-In Repair-Smoke Rerun

Run only after Task 12 creates a baseline report, or with blocker status if provider is unavailable:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --run-id phase17_locomo10_kernel_repair_smoke \
  --repair-smoke-baseline-report .memoryos/evals/phase17_locomo10_baseline_locomo.json \
  --llm-answer \
  --llm-judge
```

Expected evidence:

- report path `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_locomo.json`;
- summary path `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_locomo_repair_smoke_summary.json`;
- repair-smoke rows include executed or denied proposal status;
- kernel traces exist only in the opt-in repair-smoke run;
- same-slice movement lists include every case in one of `fail_to_pass`, `pass_to_fail`, `unchanged_fail`, or `unchanged_pass`;
- source metrics are reported separately from judged verdict movement.

### Task 14: LongMemEval Regression Guard If Needed

Run only if implementation changes default v3 context selection, retrieval, answer projection, or non-kernel public behavior:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --run-id phase17_lme30_regression_guard \
  --llm-answer \
  --llm-judge
```

If required alongside LoCoMo milestone evidence, run LongMemEval and LoCoMo in parallel where the execution environment allows.

## Review Sequence

### Task 15: Self-Review Before Lane Review

Check:

- No source/test/eval/state/ACK/blueprint edits outside the implementation scope.
- No benchmark score target appears in code, tests, or result artifacts.
- `MEMORYOS_AGENT_KERNEL` remains default-off.
- `MEMORYOS_MEMORY_ARCH=v1` fallback still works.
- Default public reports do not emit repair-smoke kernel traces.
- Repair writes are created only through `SimpleAgentStepRunner.run_step()` and approved Phase 16 tool services.
- No repair success evidence depends on direct fixture writes.
- No executable tool request contains expected answers, expected source ids, judge labels, failure classes, movement labels, or case ids.
- Same-slice repair-smoke summary is labeled diagnostic only.
- No-LLM smoke is not represented as the full-chain gate.

### Task 16: Required Case-Level Evidence For Result

The execute lane result must report:

- baseline run id and repair-smoke run id;
- LLM provider status;
- full-chain gate status;
- case lists for `fail_to_pass`, `pass_to_fail`, `unchanged_fail`, `unchanged_pass`;
- failure-class lists for `retrieval_miss`, `evidence_hit_answer_fail`, `context_missing_evidence`, `unsupported_answer`, `judge_questionable`, and source-miss judge-pass;
- source metric movement for `source_hit`, `planned_evidence_source_hit_at_5`, and `episode_source_hit_at_10`;
- repair execution counts: executed, denied, and denied reasons;
- trace evidence that repair artifacts were created through approved Level 1 tools;
- explicit statement that same-slice movement is not promotion evidence.

### Task 17: Demo-Only Rejection Gate

Reject or send to repair if any condition is true:

- any repair row is direct-written as success evidence without kernel execution;
- repair artifacts are visible in v3 without archive/session eligibility or approved lifecycle visibility;
- pass-to-fail cases are omitted from the summary;
- source metric regressions are hidden;
- LoCoMo same-slice movement is used as a benchmark quality claim;
- no-LLM/projected smoke is used as a full-chain gate;
- default kernel behavior changes.

## Final Verification Command Set

```bash
uv run pytest tests/test_public_benchmarks.py -q
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q
uv run pytest -q
uv run ruff check .
```

Full-chain, if provider access exists:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --run-id phase17_locomo10_baseline --llm-answer --llm-judge
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --run-id phase17_locomo10_kernel_repair_smoke --repair-smoke-baseline-report .memoryos/evals/phase17_locomo10_baseline_locomo.json --llm-answer --llm-judge
```

Regression guard if default path changed:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --run-id phase17_lme30_regression_guard --llm-answer --llm-judge
```
