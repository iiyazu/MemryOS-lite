# phase: phase-11
# PLAN_SELF_REVIEW PASS

# Phase 11 Plan: Evidence Handoff And Context Selection

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.
Brainstorm: `.hermes-loop/work/phase-11/brainstorm.md`.
Dispatch: `.hermes-loop/work/phase-11/god_dispatch.json`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

This is a PLAN_DRAFT artifact only. Do not edit source code, tests, `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, or docs outside phase-11 work artifacts in this draft step.

## Execution Rules

- Preserve dirty user/controller changes in `.hermes-loop/blueprint.md`, `AGENTS.md`, and `CLAUDE.md`.
- Require at least one RED test before production changes.
- Use TDD: RED -> GREEN -> REFACTOR -> focused smoke -> full verification -> milestone eval -> review.
- Keep changes append-only unless a RED test proves a narrow projection bug.
- Do not introduce case-id hacks, expected-answer leaks, scoring changes, v1 fallback regression, v3 default regression, or kernel default change.
- Do not add Letta as a runtime dependency.

## Likely Files

Modify only if the RED tests justify the change:

- `src/memoryos_lite/public_case_diagnostics.py`: add the handoff ledger, split selected/rendered/answer-evidence failure boundaries, preserve existing keys.
- `src/memoryos_lite/public_benchmarks.py`: compute answer evidence once, pass answer-evidence ids/details into diagnostics, expose append-only row fields if needed.
- `src/memoryos_lite/public_case_movement.py`: only if comparison report summaries need self-contained helper data.
- `src/memoryos_lite/engine.py`: only if `_context_package_from_v3()` projects recall/archival source refs to the wrong message id.
- `src/memoryos_lite/context_composer.py`: only if a RED test proves final trace accounting loses selected/rendered source refs.
- `src/memoryos_lite/public_failure_replay.py`: update replay/case-matrix fields after report diagnostics gain the handoff ledger.

Likely tests:

- `tests/test_public_benchmarks.py`
- `tests/test_context_composer.py`
- `tests/test_public_failure_replay.py`
- `tests/test_agent_answer_eval.py`

Do not modify documentation outside `.hermes-loop/work/phase-11/*` during execution unless a later dispatch explicitly expands scope.

## RED

### Task 1: Add failing diagnostics test for selected-drop and render-drop split

File: `tests/test_public_benchmarks.py`

Add a test near existing public case diagnostics tests:

```python
def test_public_case_diagnostics_splits_selected_and_render_handoff_drops():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    selected_drop = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="selected-drop-demo",
        memory_arch="v3",
        answer="NeverReturnedExpectedToken",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_expected"],
        retrieval_candidate_source_ids=["msg_expected"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=[],
        v3_context={"metadata": {"final_context_trace": []}},
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict="fail",
        movement_baseline_source="previous.json",
    )

    assert selected_drop["retrieval_status"] == "evidence_retrieved"
    assert selected_drop["evidence_handoff"]["failure_boundary"] == "selected_drop"
    assert selected_drop["failure_class"] == "evidence_retrieved_not_selected"

    render_drop = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="render-drop-demo",
        memory_arch="v3",
        answer="NeverReturnedExpectedToken",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_expected"],
        retrieval_candidate_source_ids=["msg_expected"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=[],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": "msg_expected",
                        "source_ids": ["msg_expected"],
                        "source_refs": [
                            {"source_type": "message", "source_id": "msg_expected"}
                        ],
                        "included": True,
                        "dropped": False,
                    }
                ]
            }
        },
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict="fail",
        movement_baseline_source="previous.json",
    )

    assert render_drop["selected_context_status"] == "evidence_selected"
    assert render_drop["rendered_context_status"] == "evidence_missing"
    assert render_drop["evidence_handoff"]["failure_boundary"] == "render_drop"
    assert render_drop["failure_class"] == "evidence_selected_not_rendered"
```

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_splits_selected_and_render_handoff_drops -q
```

Expected RED: fail because `evidence_handoff` does not exist and `failure_class` is still the coarse `context_missing_evidence`.

Record output in `.hermes-loop/work/phase-11/red_result.md`.

### Task 2: Add failing public-path test for answer-evidence handoff metadata

File: `tests/test_public_benchmarks.py`

Add a test around `_answer_evidence_from_output()` and `_to_public_result()` behavior:

```python
def test_public_result_reports_answer_evidence_handoff_metadata():
    from memoryos_lite.evals import BaselineOutput
    from memoryos_lite.public_benchmarks import (
        PublicBenchmarkCase,
        _answer_evidence_from_output,
        _to_public_result,
    )
    from memoryos_lite.schemas import EvalCase

    output = BaselineOutput(
        answer="NeverReturnedExpectedToken",
        context_tokens=7,
        sources={"msg_expected": "[D5] expected rendered evidence"},
        retrieval_candidate_source_ids=["msg_expected"],
        memory_arch="v3",
        v3_final_context_trace=[
            {
                "component": "recall",
                "item_id": "recall_item",
                "source_ids": ["msg_expected"],
                "rendered_index": 3,
                "estimated_tokens": 7,
                "metadata": {
                    "benchmark_session_id": "D5",
                    "benchmark_date": "2023-05-08",
                },
            }
        ],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": "recall_item",
                        "source_ids": ["msg_expected"],
                        "rendered_index": 3,
                        "estimated_tokens": 7,
                        "metadata": {
                            "benchmark_session_id": "D5",
                            "benchmark_date": "2023-05-08",
                        },
                        "included": True,
                        "dropped": False,
                    }
                ]
            }
        },
    )
    answer_evidence = _answer_evidence_from_output(output)
    public_case = PublicBenchmarkCase(
        benchmark="locomo",
        case=EvalCase(
            case_id="answer-evidence-handoff",
            question="What is the marker?",
            expected_facts=["ExpectedToken"],
        ),
        messages=[],
        expected_answer="ExpectedToken",
        expected_source_ids=["msg_expected"],
        expected_session_ids=["D5"],
        source_sessions_by_id={"msg_expected": "D5"},
    )

    result = _to_public_result(
        public_case,
        "memoryos_lite",
        "NeverReturnedExpectedToken",
        "llm",
        ["msg_expected"],
        "fail",
        "judge fail",
        [],
        ["ExpectedToken"],
        output,
        latency_ms=1,
        answer_evidence=answer_evidence,
        baseline_verdict="fail",
        movement_baseline_source="previous.json",
    )
    report = result.to_report()

    handoff = report["case_diagnostics"]["evidence_handoff"]
    assert handoff["answer_evidence_ids"] == ["msg_expected"]
    assert handoff["answer_evidence_overlap_ids"] == ["msg_expected"]
    assert handoff["stage_status"]["answer_evidence"] == "evidence_in_answer_evidence"
    assert report["answer_evidence"][0]["session_id"] == "D5"
    assert report["answer_evidence"][0]["date"] == "2023-05-08"
    assert report["answer_evidence"][0]["rendered_index"] == 3
```

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_result_reports_answer_evidence_handoff_metadata -q
```

Expected RED: fail because `_to_public_result()` has no `answer_evidence` parameter and reports do not include answer evidence handoff details.

Record output in `.hermes-loop/work/phase-11/red_result.md`.

### Task 3: Add optional RED if source-ref projection looks suspicious

Only do this if Task 1 or Task 2 exposes wrong source ids from `_context_package_from_v3()`.

File: `tests/test_context_composer.py`

Target behavior:

- recall/archival `ContextLayerItem.source_refs` with `source_type == "message"` must project `ContextEvidence.message_id` from `source_ref.source_id`;
- if there is no message source ref, fallback to `item.item_id`;
- projected metadata must retain `origin`, `v3_item_id`, `benchmark_session_id`, `benchmark_date`, and source-ref-derived ids.

Run:

```bash
uv run pytest tests/test_context_composer.py::test_service_context_package_from_v3_projects_message_source_refs -q
```

Expected RED only if the test is added.

## GREEN

### Task 4: Implement handoff ledger in diagnostics

File: `src/memoryos_lite/public_case_diagnostics.py`

Implement a pure helper, likely:

```python
def _evidence_handoff(
    *,
    expected_ids: list[str],
    retrieved_ids: list[str],
    selected_ids: list[str],
    rendered_ids: list[str],
    answer_evidence_ids: list[str],
    cited_source_ids: list[str],
) -> dict[str, object]:
    ...
```

Rules:

- de-duplicate all id lists in input order;
- compute overlap ids per stage;
- set `stage_status` to:
  - `no_expected_evidence` when no expected ids exist;
  - `evidence_retrieved` or `evidence_missing`;
  - `evidence_selected` or `evidence_missing`;
  - `evidence_rendered` or `evidence_missing`;
  - `evidence_in_answer_evidence` or `evidence_missing`;
  - `evidence_cited` or `evidence_missing`;
- set `failure_boundary` to the first missing stage after an earlier hit:
  - `retrieval_miss`;
  - `selected_drop`;
  - `render_drop`;
  - `answer_evidence_drop`;
  - `citation_drop`;
  - `none`.

Extend `build_case_diagnostics()` with optional parameters:

```python
answer_evidence_ids: list[str] | None = None
answer_evidence: list[dict[str, object]] | None = None
```

Default `answer_evidence_ids` to `source_ids` so existing callers and v1 fallback stay compatible.

Return append-only fields:

- `answer_evidence_ids`
- `answer_evidence_overlap_ids`
- `answer_evidence`
- `evidence_handoff`

Update `_failure_class()` to split context loss:

- if retrieval missing: `retrieval_miss`;
- if selected missing after retrieval: `evidence_retrieved_not_selected`;
- if rendered missing after selected: `evidence_selected_not_rendered`;
- if answer evidence missing after rendered: `evidence_rendered_not_answer_evidence`;
- if answer evidence survives and verdict fails: keep `evidence_hit_answer_fail` unless answer support/judge logic already returns `unsupported_answer`, `refusal_despite_evidence`, or `judge_questionable`.

Run Task 1 RED command. Expected GREEN: pass.

### Task 5: Wire answer-evidence details through the public benchmark path

File: `src/memoryos_lite/public_benchmarks.py`

Change `run_public_benchmark()` to compute answer evidence once:

```python
answer_evidence = _answer_evidence_from_output(output)
...
answer = answerer.answer(public_case.case.question, answer_evidence)
...
_to_public_result(..., answer_evidence=answer_evidence, ...)
```

Extend `PublicBenchmarkResult` with append-only field:

```python
answer_evidence: list[dict[str, Any]] = field(default_factory=list)
```

Extend `_to_public_result()` with:

```python
answer_evidence: list[AnswerEvidence] | None = None
```

Serialize answer evidence with a helper:

```python
def _answer_evidence_payload(items: list[AnswerEvidence]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": item.evidence_id,
            "source_ids": item.source_ids,
            "component": item.component,
            "session_id": item.session_id,
            "date": item.date,
            "rendered_index": item.rendered_index,
            "estimated_tokens": item.estimated_tokens,
            "metadata": item.metadata,
        }
        for item in items
    ]
```

Pass `answer_evidence_ids` and `answer_evidence` to `build_case_diagnostics()`.

Run Task 2 RED command. Expected GREEN: pass.

### Task 6: Update replay/case-matrix diagnostics

File: `src/memoryos_lite/public_failure_replay.py`

Append report-derived fields in `build_replay_row()`:

- `answer_evidence_ids`
- `answer_evidence_overlap_ids`
- `evidence_handoff`
- `failure_boundary`

Update `REQUIRED_REPLAY_FIELDS` in `tests/test_public_failure_replay.py` accordingly.

Run:

```bash
uv run pytest tests/test_public_failure_replay.py -q
```

Expected: pass.

## REFACTOR

### Task 7: Keep helpers small and backward compatible

Refactor only after GREEN:

- keep id extraction helpers pure in `public_case_diagnostics.py`;
- keep `AnswerEvidence` serialization in `public_benchmarks.py`;
- avoid changing public scoring or judge code;
- keep old diagnostic keys available:
  - `retrieved_evidence_ids`
  - `selected_context_ids`
  - `rendered_evidence_ids`
  - `cited_source_ids`
  - `failure_class`
  - `movement_status`

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_diagnostics_splits_selected_and_render_handoff_drops tests/test_public_benchmarks.py::test_public_result_reports_answer_evidence_handoff_metadata tests/test_public_failure_replay.py -q
```

Expected: all selected tests pass.

## Focused Smoke

Run focused verification:

```bash
uv run pytest tests/test_context_composer.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py tests/test_agent_answer_eval.py -q
uv run ruff check .
```

Expected:

- all focused tests pass;
- ruff reports `All checks passed!`;
- v1 fallback tests still pass;
- default v3 diagnostics tests still pass;
- kernel default-off test still passes.

Record commands and summarized outputs in `.hermes-loop/work/phase-11/result.md`.

## Full Verification

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected:

- full pytest passes;
- ruff passes;
- mypy passes, or any pre-existing mypy blocker is recorded with exact output and no completion claim based on mypy.

## Parallel Milestone Evals

Use full-chain LLM judge. Do not pass `--no-llm-answer` or `--no-llm-judge`. Run in parallel and keep heartbeat/log artifacts.

Heartbeat files must be valid single JSON objects, not JSONL:

- `.hermes-loop/work/phase-11/eval_heartbeat_longmemeval.json`
- `.hermes-loop/work/phase-11/eval_heartbeat_locomo.json`

Each heartbeat object must include at minimum:

- `phase: "phase-11"`;
- `benchmark: "longmemeval"` or `"locomo"`;
- `status: "started"`, `"running"`, `"finished"`, `"failed"`, or `"stalled"`;
- `updated_at`;
- `command`;
- `log_path`;
- `run_id` once known;
- `report_path` once the final report exists.

Update each heartbeat at least every 2 minutes while the eval process is alive. Stale heartbeat detection must be meaningful: if the heartbeat or partial/final report evidence has not changed for more than 15 minutes and no final report exists, mark `status: "stalled"` and do not treat the run as promotion evidence. A final heartbeat with `status: "finished"` is valid only when the expected final report exists and has 30 rows for the benchmark.

```bash
mkdir -p .hermes-loop/work/phase-11
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LME_RUN_ID="phase11_lme30_handoff_${RUN_TS}"
LOCOMO_RUN_ID="phase11_locomo30_handoff_${RUN_TS}"
LME_HEARTBEAT=".hermes-loop/work/phase-11/eval_heartbeat_longmemeval.json"
LOCOMO_HEARTBEAT=".hermes-loop/work/phase-11/eval_heartbeat_locomo.json"
LME_LOG=".hermes-loop/work/phase-11/eval_longmemeval30.log"
LOCOMO_LOG=".hermes-loop/work/phase-11/eval_locomo30.log"
LME_REPORT=".memoryos/evals/${LME_RUN_ID}_longmemeval.json"
LOCOMO_REPORT=".memoryos/evals/${LOCOMO_RUN_ID}_locomo.json"
LME_CMD="MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json --run-id ${LME_RUN_ID}"
LOCOMO_CMD="MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json --run-id ${LOCOMO_RUN_ID}"

write_heartbeat() {
  heartbeat_path="$1"
  benchmark="$2"
  status="$3"
  command="$4"
  log_path="$5"
  run_id="$6"
  report_path="$7"
  cat > "$heartbeat_path" <<EOF
{"phase":"phase-11","benchmark":"$benchmark","status":"$status","updated_at":"$(date -Is)","command":"$command","log_path":"$log_path","run_id":"$run_id","report_path":"$report_path"}
EOF
}

(
  write_heartbeat "$LME_HEARTBEAT" longmemeval started "$LME_CMD" "$LME_LOG" "$LME_RUN_ID" "$LME_REPORT"
  (
    while true; do
      sleep 120
      write_heartbeat "$LME_HEARTBEAT" longmemeval running "$LME_CMD" "$LME_LOG" "$LME_RUN_ID" "$LME_REPORT"
    done
  ) &
  heartbeat_pid="$!"
  MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
    --benchmark longmemeval \
    --data-path benchmarks/longmemeval/longmemeval.json \
    --baseline memoryos_lite \
    --limit 30 \
    --llm-answer \
    --llm-judge \
    --comparison-report .memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json \
    --run-id "$LME_RUN_ID" \
    2>&1 | tee "$LME_LOG"
  status="${PIPESTATUS[0]}"
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
  if [ "$status" -eq 0 ] && [ -s "$LME_REPORT" ]; then
    write_heartbeat "$LME_HEARTBEAT" longmemeval finished "$LME_CMD" "$LME_LOG" "$LME_RUN_ID" "$LME_REPORT"
  else
    write_heartbeat "$LME_HEARTBEAT" longmemeval failed "$LME_CMD" "$LME_LOG" "$LME_RUN_ID" "$LME_REPORT"
  fi
  exit "$status"
) &

(
  write_heartbeat "$LOCOMO_HEARTBEAT" locomo started "$LOCOMO_CMD" "$LOCOMO_LOG" "$LOCOMO_RUN_ID" "$LOCOMO_REPORT"
  (
    while true; do
      sleep 120
      write_heartbeat "$LOCOMO_HEARTBEAT" locomo running "$LOCOMO_CMD" "$LOCOMO_LOG" "$LOCOMO_RUN_ID" "$LOCOMO_REPORT"
    done
  ) &
  heartbeat_pid="$!"
  MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
    --benchmark locomo \
    --data-path benchmarks/locomo/locomo10.json \
    --baseline memoryos_lite \
    --limit 30 \
    --llm-answer \
    --llm-judge \
    --comparison-report .memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json \
    --run-id "$LOCOMO_RUN_ID" \
    2>&1 | tee "$LOCOMO_LOG"
  status="${PIPESTATUS[0]}"
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
  if [ "$status" -eq 0 ] && [ -s "$LOCOMO_REPORT" ]; then
    write_heartbeat "$LOCOMO_HEARTBEAT" locomo finished "$LOCOMO_CMD" "$LOCOMO_LOG" "$LOCOMO_RUN_ID" "$LOCOMO_REPORT"
  else
    write_heartbeat "$LOCOMO_HEARTBEAT" locomo failed "$LOCOMO_CMD" "$LOCOMO_LOG" "$LOCOMO_RUN_ID" "$LOCOMO_REPORT"
  fi
  exit "$status"
) &

wait
```

Expected eval evidence:

- LongMemEval 30 has no material collapse versus Phase 10 `29 pass / 1 fail`.
- LoCoMo 30 reports same-case `movement_status` values against Phase 10.
- Default rows keep `kernel_trace_events == []`.
- Reports include `case_diagnostics.evidence_handoff`.
- Retrieval misses remain visible and are not hidden as answer failures.

## Artifact Requirements

### `.hermes-loop/work/phase-11/result.md`

Must include:

- first line `# phase: phase-11`;
- active goal;
- context bundle path;
- source/test files modified;
- RED command and failing output summary;
- GREEN and REFACTOR command summaries;
- focused and full verification summaries;
- exact eval report paths;
- whether real v3/public benchmark path was exercised;
- v1 fallback, v3 default, and kernel opt-in status.

### `.hermes-loop/work/phase-11/case_matrix.md`

Must include:

- first line `# phase: phase-11`;
- context bundle path;
- Phase 10 comparison report paths;
- Phase 11 report paths;
- separate sections for LongMemEval and LoCoMo;
- fail-to-pass list;
- pass-to-fail list;
- unchanged-fail list;
- retrieval-miss list;
- selected-drop list;
- render-drop list;
- answer-evidence-drop list;
- evidence-hit-answer-fail list;
- unsupported/refusal/judge-questionable list;
- tracked risk case `conv-26_qa_015`;
- explicit statement that source/retrieval movement is separate from judged answer movement.

### `.hermes-loop/work/phase-11/execute_review.md`

Must include:

- first line `# phase: phase-11`;
- context bundle path;
- confirmation at least one RED test failed before production changes;
- review of overfitting constraints;
- review of v1 fallback, v3 default, and kernel default-off;
- review of same-case movement and pass-to-fail;
- review of whether remaining retrieval misses stayed visible;
- review of whether diagnostics are append-only and self-contained;
- any residual risks or required follow-up.

## Review Gate

The execute lane can request review only after:

- RED evidence is recorded;
- focused tests pass;
- full verification is attempted;
- milestone evals either complete or have a concrete external blocker recorded;
- `.hermes-loop/work/phase-11/eval_heartbeat_longmemeval.json` and `.hermes-loop/work/phase-11/eval_heartbeat_locomo.json` exist as valid single JSON objects, not `.jsonl` substitutes;
- heartbeat files show `status: "finished"` with final report paths and expected row counts, or a concrete `failed`/`stalled` status that blocks promotion evidence;
- `result.md`, `case_matrix.md`, and `execute_review.md` exist with phase binding.

The phase is not ACK-eligible from tests alone. It needs real public benchmark path evidence and case-level artifacts.
