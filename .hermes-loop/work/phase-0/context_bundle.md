# phase: phase-0

# Context Bundle - Phase 0 Baseline Freeze And Case Harness

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Phase Objective

Phase 0 freezes a case-level baseline and makes failures inspectable before any behavior optimization. The target chain component is the public benchmark diagnostic path over MemoryOS Lite v3:

```text
public benchmark -> MemoryOSService.ingest/build_context -> v3 ContextComposer -> PublicBenchmarkResult diagnostics
```

Kernel behavior is only a presence check when explicitly enabled with `MEMORYOS_AGENT_KERNEL=v1`; it must not become default.

## Why This Phase Exists Now

The active blueprint replaced the old phase-8 defer endpoint with a Letta-style benchmark usability loop. The current `state.json` root state is `GOD_DISPATCH` for `execute_lane.phase = phase-0`, so this is an explicit restart signal and supersedes the stale `.hermes-loop/work/next_action_2026-05-22.md` note that was written when the root state was `DONE`.

Recent 5-case smoke is weak and must not be hidden:

- LongMemEval v3 projected 5-case: `1/5`.
- LoCoMo v3 projected 5-case: `0/5`.
- LongMemEval v3 plus opt-in kernel with LLM judge 5-case: `1/5`.
- LoCoMo v3 plus opt-in kernel with LLM judge 5-case: `1/5`.

## Current Hypothesis

The chain is wired enough to expose v3 diagnostics, but answer benchmark failures are not yet classifiable with enough case-level precision. Phase 0 should not optimize behavior. It should freeze the baseline, confirm defaults, and write a stable case matrix that later phases can diff.

Disconfirming evidence:

- v3 diagnostics are missing from real public benchmark reports.
- `MEMORYOS_MEMORY_ARCH=v1` fallback is broken.
- `MEMORYOS_AGENT_KERNEL=v1` is enabled by default or kernel traces appear without explicit opt-in.
- 5-case smoke cannot produce stable case IDs or per-case diagnostic fields.
- Focused tests fail in a way that makes the baseline unusable.

## Scope

In scope:

- Confirm active goal, state, defaults, and current benchmark artifacts.
- Run focused tests for the real v3/public benchmark path.
- Run or refresh 5-case LongMemEval and LoCoMo v3 public smoke with no LLM answer/judge.
- Run kernel smoke only with `MEMORYOS_AGENT_KERNEL=v1`.
- Optionally run 30-case full-chain LLM judge if provider credentials are available and time/cost are acceptable; if unavailable, record the blocker and do not mark the milestone gate satisfied.
- Produce `.hermes-loop/work/phase-0/baseline_case_matrix.md`.
- Produce `result.md`, `execute_review.md`, and review artifacts before ACK.

Non-goals:

- No retrieval, context composer, answer prompt, or kernel behavior optimization.
- No Letta runtime dependency.
- No benchmark case-id hacks or expected-answer leaks.
- No state promotion unless ACK reaches usable level.
- No default kernel enablement.

## State Excerpt

Source: `.hermes-loop/state.json` read at startup.

```json
{
  "current_state": "GOD_DISPATCH",
  "current_phase_idx": 0,
  "execute_lane": {"phase": "phase-0", "state": "GOD_DISPATCH"},
  "plan_lane": {"phase": "phase-1", "state": "PLAN_STORM"},
  "research_lane": {"phases": ["phase-2"]},
  "review_lane": {"active": false, "phase": null}
}
```

Historical phase entries contain ACK evidence through phase-8, but the active blueprint says to use the current repository and latest baseline rather than old phase completion claims.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` sections:

- Purpose and Current Baseline.
- Hard Constraints.
- Completion Levels.
- Required ACK Evidence.
- Context Bundle Requirement.
- Full-Chain LLM Judge Gates.
- Letta Comparison Map.
- Phase 0 - Baseline Freeze And Case Harness.
- Minimum First Dispatch.
- Stop Conditions.

No promoted amendment is active for phase-0.

## Required MemoryOS Read-First Files

- `src/memoryos_lite/config.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/diagnostic_report.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/context_composer.py`
- `tests/test_agent_kernel.py`
- `tests/test_public_benchmarks.py`
- `tests/test_context_composer.py`
- `tests/test_evals.py`
- `docs/memory-v3-architecture.md`
- `docs/agentic-memory-roadmap-zh.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`

## Required Letta Reference Files

Use these as semantic references only; do not add Letta as a dependency.

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

Phase 0 only records which Letta semantics later phases must compare; Phase 1 owns the gap matrix.

## Current Baseline Facts

Verified from code and recent artifacts:

- `Settings.memoryos_memory_arch = "v3"`.
- `Settings.memoryos_agent_kernel = "off"`.
- `Settings.memoryos_recall_pipeline = "v1"`.
- `MemoryOSService._should_route_to_v3_context()` routes to v3 when resolved arch is `v3` and the setting is explicitly present in `model_fields_set`; the public benchmark command must set `MEMORYOS_MEMORY_ARCH=v3`.
- `PublicBenchmarkResult` includes `memory_arch`, `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events`.
- Opt-in kernel public benchmark tests expect the trace sequence `kernel_step_started -> tool_policy_decision -> approval_pending -> kernel_step_completed -> kernel_step_started -> tool_policy_decision -> approval_granted -> tool_executed -> kernel_step_completed`.
- Local benchmark data exists:
  - `benchmarks/longmemeval/longmemeval.json`: 500 cases.
  - `benchmarks/locomo/locomo10.json`: 10 cases.

Recent case-level smoke from `.memoryos/evals`:

| Report | Result | Notable cases |
|---|---:|---|
| `v3_lme_5case_longmemeval.json` | `1/5` projected | `e47becba`, `118b2229`, `51a45a95` had episode/planned evidence hits but failed answer; `58bf7951` was retrieval miss; `1e043500` passed. |
| `v3_locomo_5case_locomo.json` | `0/5` projected | `conv-26_qa_001` had evidence hit but failed exact answer; `conv-26_qa_002` to `conv-26_qa_005` were retrieval misses. |
| `v3_kernel_lme_5case_llmjudge_longmemeval.json` | `1/5` LLM judge | Kernel traces present for all cases; no global improvement claim allowed. |
| `v3_kernel_locomo_5case_llmjudge_locomo.json` | `1/5` LLM judge | `conv-26_qa_001` passed; remaining LoCoMo failures remain unexplained until baseline matrix is refreshed. |

## Known Pass-To-Fail Risks

- Treating `source_hit` as pure retrieval localization. It is mixed final projection and source attribution.
- Treating aggregate pass rate as sufficient evidence.
- Assuming LongMemEval behavior transfers to LoCoMo.
- Losing v1 fallback while instrumenting v3.
- Accidentally enabling kernel by default.
- Calling prompt-only or report-only changes architecture progress.
- Using stale phase artifacts that do not cite this bundle.

## RED Evidence To Start From

Phase 0 is primarily diagnostic. RED evidence is the current weak 5-case public smoke:

- LongMemEval cases with evidence hit but answer fail: `e47becba`, `118b2229`, `51a45a95`.
- LongMemEval retrieval miss: `58bf7951`.
- LoCoMo evidence hit but answer fail: `conv-26_qa_001`.
- LoCoMo retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

If implementation becomes necessary to expose missing diagnostics, write a failing test first. Otherwise, no production code changes are expected in Phase 0.

## Expected Verification Commands

Focused tests:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_public_benchmarks.py tests/test_context_composer.py tests/test_evals.py -q
```

Full baseline checks if the phase reaches ACK:

```bash
uv run pytest -q
uv run ruff check .
```

5-case v3 smoke, no LLM answer/judge:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 5 \
  --run-id phase0_v3_lme_5case \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --run-id phase0_v3_locomo_5case \
  --no-llm-answer \
  --no-llm-judge
```

Opt-in kernel smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 1 \
  --run-id phase0_v3_kernel_locomo_1case \
  --no-llm-answer \
  --no-llm-judge
```

Optional milestone baseline if provider access is available:

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

LoCoMo local cap is 10 cases.

## Anti-Demo Usable ACK Criteria

Phase 0 may ACK only if:

- `baseline_case_matrix.md` exists and lists stable case IDs.
- LongMemEval and LoCoMo are separated.
- Each case is classified at least as pass, retrieval miss, evidence hit but answer fail, context missing evidence, answer unsupported/overconfident, or judge questionable.
- Reports include v3 diagnostic fields and kernel trace presence/absence.
- Focused tests pass, or failures are recorded with root cause and decision is not `advance`.
- v1 fallback, v3 default, and kernel opt-in constraints are verified.
- `result.md`, `execute_review.md`, and review output cite this context bundle and the active goal.

If any required evidence is missing, the decision must be `repeat`, `adjust_blueprint`, or `pause`, not `advance`.

## Constraints To Preserve

- `MEMORYOS_MEMORY_ARCH=v3` remains the default architecture.
- `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback.
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and is never set by default.
- SQLite remains authoritative; filesystem reports are debug/eval artifacts.
- Benchmark language must remain conservative; 5-case smoke is not global improvement evidence.
