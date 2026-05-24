# phase: phase-17

# Phase 17 Brainstorm

Context bundle: `.hermes-loop/work/phase-17/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Constraints Carried Forward

- Phase 17 is K4 repair measurement, not benchmark promotion.
- Kernel behavior remains opt-in with `MEMORYOS_AGENT_KERNEL=v1`; default public reports must keep empty kernel traces.
- Same-slice LoCoMo repair movement is structural smoke only. It can explain movement and risks, but cannot become a quality claim without clean held-out or clean-store validation.
- Executable maintenance inputs must be regenerated from model-visible artifacts only: selected/rendered context, answer evidence, citations, v3 diagnostics, kernel traces, and store provenance.
- Eval-only sidecars stay out of tool calls: `case_id`, `expected_answer`, `expected_source_ids`, verdicts, judge labels, gold failure classes, and movement labels must not appear in executable arguments, source refs, archive attachments, repair notes, or promotion candidates.
- If model-visible source ids contain benchmark labels, the repair harness must execute against repair-store message ids or otherwise prove the source refs came from selected/rendered context rather than eval sidecars.
- No product-code change should begin without RED tests for leakage denial, isolated writes, real Phase 16 tool execution, v3 visibility boundaries, and case-level before/after reporting.

## Current Surface

`public_maintenance_planner.py` already separates `ModelVisiblePlannerInput` from `EvalGoldSidecar`, emits `gold_fields_used=false`, and keeps proposals `proposal_only`.

`public_benchmarks.py` already emits case diagnostics, movement status from comparison reports, model-visible planner inputs, eval sidecars, and proposal-only maintenance artifacts. It also proves public kernel traces remain default-off and opt-in traces use `SimpleAgentStepRunner`.

The kernel/tool surface from Phase 16 is usable for Level 1 writes: `archive_write`, `archive_attach`, and `core_promotion_request` are registry-backed, approval-bound, replay-bound, service-backed, verified, and traced. The v3 composer only sees archive content through archive attachment/scope eligibility, and pending core promotion candidates do not render as core memory.

Letta references support the same shape: durable core blocks, archival passages scoped through archives, tool execution routed through a manager/executor with bounded returns, approval-aware agent steps, and explicit context-window accounting. Phase 17 should borrow those contracts, not import Letta.

## Approach 1 - Explicit Repair-Smoke Harness Around Public v3 Path

Add a narrow, opt-in public benchmark repair-smoke mode in the later implementation phase. The mode would run only for LoCoMo repair measurement and would be disabled unless explicitly requested.

Flow:

1. Run the fixed LoCoMo baseline through the normal public v3 path with full-chain answer/judge when provider access exists. If provider access is missing, record a blocker or diagnostic-only no-LLM smoke, not quality evidence.
2. Build repair candidates from each baseline row's `model_visible_planner_input` and `maintenance_proposal`.
3. Validate a clean executable proposal object that strips the eval sidecar completely and denies any payload containing gold fields, judge labels, movement labels, expected source ids, expected answers, or benchmark case ids.
4. In an isolated repair-smoke store, ingest the benchmark messages through the same public path, then execute approved Phase 16 Level 1 tool calls through `SimpleAgentStepRunner.run_step()` before the rerun context is built.
5. Let the existing v3 composer consume resulting maintenance artifacts only through eligible archive attachments or approved lifecycle artifacts.
6. Rerun the same fixed LoCoMo slice and produce a case-level comparison report: `fail_to_pass`, `pass_to_fail`, `unchanged_fail`, retrieval misses, evidence-hit-answer-fail, judge-questionable, source-miss judge-pass, `source_hit`, `planned_evidence_source_hit_at_5`, and `episode_source_hit_at_10`.
7. Freeze generic repair rules/artifacts and require clean held-out or clean-store validation before any benchmark-quality claim.

Tradeoffs:

- Safest because it leaves default v3, v1 fallback, default public eval behavior, and kernel default untouched.
- Reversible because it can live behind an explicit repair-smoke flag or helper without changing retrieval/composer ranking globally.
- Strong anti-demo posture because maintenance writes go through the real Phase 16 kernel/tool services and are later consumed through the real v3 composer.
- More plumbing than a report-only comparison because current public benchmark execution resets stores per case; the repair pass must be inserted at a precise point after ingestion/page and before rerun `build_context`.
- It may produce no quality gate if LLM provider access is unavailable, but that is the correct outcome.

## Approach 2 - External Preseeded Repair Store Then Normal Rerun

Create a separate script/harness that reads the baseline report, creates an isolated store, executes approved kernel repair writes, then invokes the normal public benchmark runner against that store.

Tradeoffs:

- Conceptually simple and keeps the public benchmark runner smaller.
- Risky with current code because `memoryos_lite` public eval resets store state inside the baseline path, so preseeded artifacts can be erased or require bypass hooks.
- Higher chance of becoming demo-only if the script validates written artifacts directly but does not prove the normal v3 public path consumed them.
- Easier to accidentally drift from the public benchmark ingestion/session semantics.

This is acceptable only as a diagnostic helper if it is paired with tests proving the later rerun consumes artifacts through the same v3 composer path. It is weaker than Approach 1 as the main implementation route.

## Approach 3 - Retrieval/Composer Repair Based On LoCoMo Failure Classes

Use the Phase 16/17 failure classes to adjust retrieval, archival ranking, neighbor handling, answer projection, or context-composer selection directly.

Tradeoffs:

- Could address true bottlenecks if repair artifacts are not enough.
- Broadens blast radius immediately: default v3 context selection or answer behavior may change, requiring LongMemEval regression guard and more pass-to-fail analysis.
- Easier to overfit LoCoMo and harder to separate source-localization movement from answer/judge movement.
- Does not directly prove the K4 question: whether kernel-created maintenance artifacts help when consumed through the real v3 path.

This should be rejected for the first Phase 17 slice. It can become a bounded follow-up only if Approach 1 proves, with traces, that maintenance artifacts are created safely but v3 eligibility/ranking prevents consumption.

## Rejected Alternatives

- Prompt-only or answer-only changes: unsafe unless case evidence narrows the bottleneck to answer projection. They do not prove Letta-style memory maintenance.
- Directly writing archive rows, attachments, core blocks, sidecars, or fixtures: demo-only because it bypasses the Phase 16 kernel/tool approval path.
- Opening Level 2 search tools or Level 3 core edit tools in this slice: too broad without new RED tests, policy rules, provenance rules, and review gates.
- Using `expected_answer`, `expected_source_ids`, judge verdicts, failure classes, movement labels, or case ids to shape tool arguments: benchmark leakage.
- Treating LoCoMo same-slice movement, no-LLM projected smoke, or LongMemEval-only movement as promotion evidence: unsafe and explicitly outside Phase 17.
- Hiding pass-to-fail rows inside aggregate summaries: unsafe because Phase 17 exists to expose regressions and source-grounding movement.

## What Counts As Demo-Only Or Unsafe

- Any repair artifact appears in v3 context without archive attachment/scope eligibility or approved lifecycle provenance.
- Kernel traces appear in default public reports without `MEMORYOS_AGENT_KERNEL=v1`.
- Tool calls execute from eval sidecar fields or contain gold-derived identifiers, labels, answers, or target classes.
- A repair run reports only aggregate pass rate and omits case-level movement and source metrics.
- No-LLM smoke is described as full-chain quality evidence.
- Same-slice repair movement is used to claim benchmark improvement before clean held-out or clean-store validation.

Recommended route: Approach 1, because it is the smallest reversible path that tests the K4 hypothesis through real approved kernel writes and real v3 public consumption while preserving default behavior, blocking gold leakage, and keeping same-slice LoCoMo movement diagnostic only.
