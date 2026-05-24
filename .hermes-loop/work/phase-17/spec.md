# phase: phase-17

# Phase 17 Spec: Opt-In LoCoMo Repair-Smoke Harness

Context bundle: `work/phase-17/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Decision

Use the recommended route from `work/phase-17/brainstorm.md`: an explicit opt-in repair-smoke harness around the real public `memoryos_lite` v3 path. The harness must execute approved Phase 16 Level 1 maintenance tools through `SimpleAgentStepRunner.run_step()` in an isolated repair-smoke store, then rerun the same fixed LoCoMo slice through the normal v3 context composer. It must not direct-write fixtures, mutate benchmark JSON, hide pass-to-fail movement, or claim benchmark quality from same-slice repair smoke.

This phase is K4 measurement, not promotion. Same-slice LoCoMo movement can support repair diagnostics only. Clean held-out or clean-store validation is required before any benchmark-quality claim.

## Design References

MemoryOS files inspected:

- `src/memoryos_lite/public_benchmarks.py`: public benchmark runner, report fields, movement comparison, model-visible planner inputs, eval sidecars.
- `src/memoryos_lite/public_maintenance_planner.py`: current proposal-only planner artifact contract.
- `src/memoryos_lite/evals.py`: real `memoryos_lite` baseline path, store reset, v3 context build, opt-in kernel probe.
- `src/memoryos_lite/agent_kernel.py`, `src/memoryos_lite/agent_kernel_tools.py`, `src/memoryos_lite/agent_tool_registry.py`, `src/memoryos_lite/agent_tool_selection.py`: Phase 16 Level 1 tool execution, policy, approval, verification, fail-closed replay.
- `src/memoryos_lite/store.py`, `src/memoryos_lite/context_composer.py`, `src/memoryos_lite/engine.py`: isolated store behavior, archive attachment eligibility, pending promotion candidate visibility, v3 context metadata.
- `tests/test_public_benchmarks.py`, `tests/test_agent_kernel.py`, `tests/test_context_composer.py`, `tests/test_memory_lifecycle.py`: existing guards for public diagnostics, kernel default-off, tool execution, archive scope, lifecycle candidates.

Letta files were used only as design references, not imports. The relevant contracts are durable core blocks, archival passages scoped by archive, manager/executor-routed tool execution, bounded tool returns, and explicit context-window accounting.

## Scope

Implement the smallest real-path repair-smoke loop:

1. Run a fixed LoCoMo baseline through the existing public v3 path and record full-chain LLM answer/judge results when provider access exists.
2. Load each baseline row's `model_visible_planner_input` and `maintenance_proposal`.
3. Validate and sanitize an executable repair request from model-visible fields only.
4. Reject proposals whose executable payload contains expected answers, expected source ids, judge labels, gold failure classes, movement labels, or case ids.
5. Execute approved Level 1 tool calls in an isolated repair-smoke store before the rerun v3 context build.
6. Let v3 consume repair artifacts only through archive attachment or approved lifecycle eligibility.
7. Write a comparison report with case-level movement and source metric movement.
8. Mark no-LLM repair smoke as diagnostic-only, not full-chain quality evidence.

The first implementation should exercise `archive_write` because current planner proposals emit only `archive_write`. The harness may preserve validation support for `archive_attach` and `core_promotion_request` only if a proposal object already supplies those Phase 16 tool names and passes the same source/provenance checks. It must not open Level 2 search tools or Level 3 core edit tools.

## Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change default `v3` architecture or remove `MEMORYOS_MEMORY_ARCH=v1`.
- Do not add Letta as a dependency.
- Do not modify benchmark JSON files.
- Do not persist repair artifacts into a global cache.
- Do not use benchmark score targets.
- Do not treat no-LLM/projected smoke as satisfying a full-chain gate.
- Do not treat same-slice repair-smoke movement as promotion evidence.
- Do not direct-write archive rows, attachments, core blocks, sidecars, or fixture memories as success evidence.

## Proposed Interfaces

Add `src/memoryos_lite/public_repair_smoke.py` with narrow public-eval support types and functions:

- `RepairSmokeMode`: disabled by default; enabled only by explicit CLI/API option.
- `ExecutableRepairProposal`: sanitized tool name, arguments, source refs, provenance summary, denial status.
- `RepairSmokeCaseTrace`: per-case denied/executed proposals, kernel trace events, repair artifact ids, source-id alias evidence, and full-chain gate status.
- `RepairSmokeComparison`: case-level before/after summary and metric movement.
- `build_executable_repair_proposal(row, source_id_aliases)`: validates a baseline report row and returns either an executable tool request or a denial.
- `execute_repair_smoke_requests(service, session_id, context_package, requests)`: executes through `SimpleAgentStepRunner.run_step()` with Phase 16 approval/replay.
- `summarize_repair_smoke(baseline_rows, repair_rows)`: produces movement lists and source metric movement without hiding regressions.

Modify `src/memoryos_lite/evals.py` to add a private insertion point for the real `memoryos_lite` baseline path:

- Before `service.build_context(...)`, optionally call a repair-smoke hook after messages are ingested and paged.
- The hook receives the actual isolated service, source session, context session, case, messages, and available baseline report row.
- The hook returns kernel trace events and repair provenance to be included in `BaselineOutput`.
- Default behavior remains identical when the hook is absent.

Modify `src/memoryos_lite/public_benchmarks.py`:

- Add explicit repair-smoke parameters to `run_public_benchmark`, defaulting off.
- Load baseline report rows only when repair smoke is explicitly enabled.
- Pass the repair hook into `_run_baseline` only for `benchmark == "locomo"`, `baseline == "memoryos_lite"`, `settings.resolved_memory_arch == "v3"`, and `settings.resolved_agent_kernel == "v1"`.
- Include repair-smoke trace/provenance in public report rows.
- Write a separate comparison summary artifact next to the public report.

Modify `src/memoryos_lite/cli.py`:

- Add explicit options, for example `--repair-smoke-baseline-report PATH` and `--repair-smoke-summary/--no-repair-smoke-summary`.
- Do not infer repair-smoke mode from `MEMORYOS_AGENT_KERNEL=v1`; the flag and a baseline report are both required.

## Gold-Leakage Boundary

`EvalGoldSidecar` remains report-only. It may be used by validation code only to deny unsafe execution and to classify reports after the fact. It must not supply tool content, source refs, scope, archive ids, candidate ids, target labels, or repair notes.

Executable repair inputs may use:

- `model_visible_planner_input.question`;
- selected/rendered/final context source ids;
- answer evidence and citations;
- citation contract status;
- v3 archival eligibility diagnostics;
- component drop counts;
- kernel traces from the model-visible path;
- store provenance from the repair-store run.

Executable repair inputs must not use:

- `case_id`;
- `expected_answer`;
- `expected_source_ids`;
- judge verdict or judge labels;
- gold-derived failure classes;
- movement labels;
- benchmark-case-specific ids in arguments, repair notes, archive ids, or promotion candidates.

Source ids are special because current LoCoMo message ids include benchmark labels. The repair harness must not copy sidecar source ids. It must either:

- rewrite model-visible source refs to repair-store-local aliases before execution, while keeping a reverse map for report metrics; or
- prove each source ref came from selected/rendered v3 context rather than the sidecar, then write only a non-gold repair-store source identifier into the tool request.

The first implementation should use an alias map so executable tool requests do not contain LoCoMo case ids even when the original selected context ids do.

## Isolation Boundary

Repair-smoke runs must use the existing public eval isolated run directory and store reset behavior. Repair artifacts must stay under the repair run's `data_dir`. The harness must not write to benchmark files, `.memoryos/evals` reports except the current run outputs, global store state, or a persistent repair cache.

Default public runs must remain maintenance-write-free. Kernel trace events must remain empty unless `MEMORYOS_AGENT_KERNEL=v1` and repair-smoke mode is explicitly requested or the existing opt-in kernel probe runs.

## V3 Visibility Boundary

Repair artifacts may affect rerun context only through:

- archival memories/passages attached to the current session archive;
- existing v3 archive eligibility and scope diagnostics;
- approved lifecycle artifacts after they are applied through the existing lifecycle path.

Pending `core_promotion_request` candidates must not render as core memory. Tool result messages must stay bounded and must not become broad answer context pollution.

## Case-Level Evidence Requirements

The comparison report must include, at minimum:

- baseline and repair run ids;
- whether answer/judge were full-chain LLM or projected/no-LLM;
- full-chain gate status: `satisfied`, `not_satisfied`, or `blocked_provider_unavailable`;
- `fail_to_pass`, `pass_to_fail`, `unchanged_fail`, and `unchanged_pass` case lists;
- `retrieval_miss`, `evidence_hit_answer_fail`, `context_missing_evidence`, `unsupported_answer`, `judge_questionable`, and source-miss judge-pass lists;
- per-case baseline and repair `verdict`, `failure_class`, `answer_support_status`, `judge_status`, `source_hit`, `planned_evidence_source_hit_at_5`, `episode_source_hit_at_10`, `source_ids`, and repair execution status;
- aggregate counts only after the case lists;
- explicit statement that same-slice movement is repair-smoke diagnostic evidence only.

## Missing LLM Provider Handling

If the configured answer or judge LLM provider is unavailable, the execute lane must:

- still run focused RED/GREEN tests and deterministic structural smoke if useful;
- write the repair-smoke summary with `answer_mode = projected` and `full_chain_gate_status = blocked_provider_unavailable`;
- record the provider error in the phase result and review eval decision;
- refuse to claim full-chain quality, benchmark improvement, or promotion readiness.

No-LLM smoke may verify wiring, leakage denial, isolation, and report shape. It cannot satisfy the fixed LoCoMo 10-case full-chain gate.

## Demo-Only Rejection Criteria

Reject the implementation as demo-only or unsafe if any of these occur:

- repair artifacts are inserted by direct store writes instead of approved Phase 16 kernel tool calls;
- success evidence is based on fixture rows written directly into reports or stores;
- executable tool inputs include gold fields, case ids, judge labels, failure classes, movement labels, expected answers, or expected source ids;
- repair artifacts enter v3 context through direct injection rather than archive attachment/scope eligibility or approved lifecycle visibility;
- default public reports emit kernel traces without explicit kernel opt-in;
- the report hides pass-to-fail rows or source-grounding regressions behind aggregate counts;
- no-LLM/projected smoke is described as full-chain quality evidence;
- same-slice repair smoke is promoted as global LoCoMo or LongMemEval improvement.

## Verification Expectations

Focused tests:

```bash
uv run pytest tests/test_public_benchmarks.py -q
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q
```

Baseline checks:

```bash
uv run pytest -q
uv run ruff check .
```

Full-chain LoCoMo fixed-slice gate when LLM provider access exists. Because the
current CLI defaults `llm_answer` and `llm_judge` to `False`, every full-chain
gate command must explicitly pass `--llm-answer` and `--llm-judge`:

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

Explicit opt-in repair-smoke rerun:

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

LongMemEval regression guard is required only if default v3 context selection, retrieval, answer projection, or non-kernel public behavior changes:

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
