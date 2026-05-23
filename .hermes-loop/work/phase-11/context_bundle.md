# phase: phase-11

# Phase 11 Context Bundle

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory
system for LongMemEval and LoCoMo, without demo-only phase completion, without
hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase: `phase-11`.

Name: Evidence Handoff And Context Selection.

Target state: `evidence-handoff-reliable`.

Target chain components:

- retrieval: verified, not broadly retuned unless a handoff test proves missing
  recall metadata blocks diagnosis;
- context composer: changed or verified;
- answer projection/rendering: changed or verified through structured answer
  evidence and public report diagnostics;
- public eval: verified through focused tests and 30-case gates;
- ingest/store/kernel loop: unchanged unless a failing test proves a narrow
  diagnostic support field is required.

## Why This Phase Exists Now

Phase 10 completed a narrow recall packet improvement. It moved LoCoMo
`conv-26_qa_011` from Phase 9 `session_localization_miss` to a supported pass
and had supporting fail-to-pass movement on `conv-26_qa_012`, without
LongMemEval or LoCoMo pass-to-fail cases on the 30-case gate.

The remaining Phase 10 LoCoMo 30 failures split into:

- retrieval misses: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`,
  `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`;
- evidence-hit-answer-fail cases: `conv-26_qa_006`, `conv-26_qa_016`,
  `conv-26_qa_024`, `conv-26_qa_027`.

Phase 11 exists to make the post-retrieval handoff auditable and reliable:

```text
indexed -> retrieved -> selected -> rendered -> cited -> judged
```

The phase must not hide remaining retrieval misses or claim aggregate-only
improvement. It should focus on selected/rendered/answer-use failures and on
self-contained case-level comparison artifacts.

## Current Hypothesis

Some LoCoMo failures no longer need broader recall first. Expected evidence is
available in selected or rendered context, but public diagnostics and/or answer
evidence handoff are not precise enough to separate selected-drop, render-drop,
citation-support, and judged-answer failure. A narrow context handoff
improvement should reduce or reclassify evidence-hit-answer-fail cases without
changing scoring or enabling the kernel by default.

Disconfirming evidence:

- focused tests show selected/rendered/cited handoff is already correct and the
  remaining failures are purely answer-prompt or judge-quality failures;
- LoCoMo 30 has no same-case explainable improvement or more precise failure
  reclassification;
- source grounding regresses or pass-to-fail appears without explanation;
- any fix changes benchmark scoring, branches on case ids or expected answers,
  or enables `MEMORYOS_AGENT_KERNEL=v1` by default.

## Scope

Allowed:

- improve `V3ContextComposer`, `MemoryOSService._context_package_from_v3`,
  public benchmark answer evidence construction, or public case diagnostics;
- add append-only diagnostic fields that explain selected vs rendered vs cited
  movement;
- add self-contained comparison artifacts or report fields when comparison
  paths are available;
- add failing tests before implementation for selected-drop, render-drop,
  answer-evidence handoff, or source-id projection mismatch.

Non-goals:

- do not retune broad recall unless a Phase 11 RED test proves a handoff field
  requires a narrow recall metadata change;
- do not change benchmark scoring semantics or judge criteria;
- do not change `MEMORYOS_MEMORY_ARCH=v1` fallback behavior;
- do not enable `MEMORYOS_AGENT_KERNEL=v1` by default;
- do not add Letta as a runtime dependency;
- do not claim production readiness or aggregate-only benchmark improvement.

## State Snapshot

From `.hermes-loop/state.json` after Phase 10 advance:

- `current_state`: `GOD_DISPATCH`;
- `execute_lane.phase`: `phase-11`;
- `execute_lane.state`: `GOD_DISPATCH`;
- `plan_lane.phase`: `phase-12`;
- `phase-10.status`: `completed`;
- `phase-11.status`: `in_progress`;
- `last_updated`: `2026-05-23T06:26:28+08:00`.

Pre-existing dirty changes remain outside this phase:

- `.hermes-loop/blueprint.md` has a controller-level parallel eval rule;
- `AGENTS.md` and `CLAUDE.md` have autonomous-mode headers.

Treat those as existing user/controller context. Do not revert them.

## Active Blueprint Sections

Read `.hermes-loop/blueprint.md` first, especially:

- `Current Baseline And Phase 8 Evidence`;
- `Hard Constraints`;
- `Context Bundle Requirement`;
- `30/50-Case Eval Gate Policy`;
- `Phase 10 - Recall Memory Reliability`;
- `Phase 11 - Evidence Handoff And Context Selection`;
- `Phase 12 - Archival/RAG Memory Unification`.

Phase 11 ACK gate:

- no selected expected evidence disappears without a diagnostic reason;
- `context_missing_evidence` or equivalent context failure is split into
  selected-drop vs render-drop;
- public reports expose enough fields for same-case diagnosis;
- LoCoMo movement is same-case and explainable, not aggregate-only;
- LongMemEval has no material collapse;
- no v1 fallback regression, v3 default regression, kernel-default change, or
  benchmark-specific hack.

## Required Read-First Files

MemoryOS:

- `.hermes-loop/work/phase-11/context_bundle.md`;
- `.hermes-loop/work/phase-11/god_dispatch.json`;
- `.hermes-loop/work/phase-10/ack.json`;
- `.hermes-loop/work/phase-10/result.md`;
- `.hermes-loop/work/phase-10/case_matrix.md`;
- `.hermes-loop/work/phase-10/reflect_phase-10.md`;
- `.hermes-loop/work/phase-10/review_verdict.json`;
- `.hermes-loop/work/phase-9/failure_taxonomy.md`;
- `.hermes-loop/work/phase-9/case_matrix.md`;
- `docs/known-issues.md`;
- `docs/public-benchmark-diagnosis.md`;
- `docs/agentic-memory-roadmap-zh.md`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/engine.py`;
- `src/memoryos_lite/public_benchmarks.py`;
- `src/memoryos_lite/public_case_diagnostics.py`;
- `src/memoryos_lite/public_case_movement.py`;
- `src/memoryos_lite/agent_answer_eval.py`;
- `src/memoryos_lite/retrieval/recall_pipeline.py`;
- `tests/test_context_composer.py`;
- `tests/test_public_benchmarks.py`;
- `tests/test_public_failure_replay.py`;
- `tests/test_agent_answer_eval.py`.

Letta reference files, design-only:

- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`;
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`.

Use Letta for semantics such as component-level context accounting,
passage/evidence provenance, and context-window accounting. Do not port Letta
internals or add Letta dependencies.

## Current Implementation Snapshot

Current anchors:

- `V3ContextComposer.build()` builds task, core, recall, archival, and recent
  layers, then writes `component_accounting`, `final_context_trace`,
  `component_drop_counts`, and `locomo_neighbor_diagnostics`.
- `RecallPipeline.build_context()` now emits `recall_evidence_packets`,
  `recall_candidate_session_ids`, and `recall_planned_session_ids`.
- `MemoryOSService._context_package_from_v3()` projects v3 items into legacy
  `ContextPackage.retrieved_evidence` and metadata used by public eval.
- `public_case_diagnostics.build_case_diagnostics()` currently reports
  retrieved, selected, final context trace, rendered, cited, answer support,
  judge status, failure class, and source-hit semantics.
- Public report rows from Phase 10 still have `movement_status:
  new_case_no_baseline`; same-case movement was re-derived in `case_matrix.md`.

Known risks:

- selected and rendered evidence ids can look equivalent in aggregate while
  answer evidence ordering or citation availability still fails;
- source ids can be projected from recall/archival layers differently than the
  final answerer sees them;
- raw report movement fields are not self-contained unless comparison paths are
  passed and preserved;
- prompt or answerer tweaks must not be called architecture improvements unless
  case-level diagnostics prove answer-evidence handoff is the bottleneck.

## Baseline And Case-Level Evidence

Valid Phase 8 reports:

- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`;
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

Valid Phase 10 reports:

- `.memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json`;
- `.memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json`;
- `.memoryos/evals/phase10_locomo30_projected_packets_20260522T202000Z_locomo.json`
  for source/session movement only, not promotion by itself.

Accepted Phase 10 full-chain LLM judge evidence:

- LongMemEval 30: `29 pass / 1 fail`, pass-to-fail `0`;
- LoCoMo 30: `20 pass / 10 fail`, fail-to-pass
  `conv-26_qa_011`, `conv-26_qa_012`, pass-to-fail `0`;
- primary session-localization signal: `conv-26_qa_011`;
- kernel traces remained empty by default.

Phase 11 focus cases:

- evidence-hit-answer-fail: `conv-26_qa_006`, `conv-26_qa_016`,
  `conv-26_qa_024`, `conv-26_qa_027`;
- tracked judge/source-support risk: `conv-26_qa_015`;
- unchanged retrieval misses must remain visible but are not the primary Phase
  11 target unless a handoff diagnostic proves a misclassification.

## Pass-To-Fail Risks

- changing final context ordering can crowd out exact LongMemEval sources;
- broad answerer prompt changes can improve LoCoMo while weakening source
  grounding;
- collapsing selected/rendered/cited diagnostics into one status can hide
  regressions;
- raw report movement fields can be mistaken for same-case evidence when
  comparison paths are absent;
- enabling kernel traces by default would violate the active goal.

## Required Failing Tests Before Implementation

At least one RED test must fail before production code changes. Acceptable RED
targets:

- a public-case diagnostic test where a selected expected source is dropped
  before rendering and the report must classify it as selected-drop rather than
  generic evidence missing;
- a test where rendered expected evidence exists but answer evidence passed to
  `PublicAnswerer` omits source ids, session id, date, or rendered order;
- a test where recall/archival source refs project to the wrong message id in
  `_context_package_from_v3`;
- a movement-report test proving comparison paths produce self-contained
  fail-to-pass/pass-to-fail fields rather than relying on phase-local manual
  tables.

Do not write tests or production logic that branch on `conv-26`, `qa_*`, known
expected answers, expected source ids, or known failed-case lexical terms.

## Expected Commands

Focused tests first:

```bash
uv run pytest tests/test_context_composer.py tests/test_public_benchmarks.py tests/test_public_failure_replay.py tests/test_agent_answer_eval.py -q
uv run ruff check .
```

Baseline checks unless scoped down with evidence:

```bash
uv run pytest -q
uv run ruff check .
```

Milestone gate: run LongMemEval and LoCoMo 30 full-chain commands in parallel,
collect both results, and update heartbeat files while running:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge
```

If LLM provider access is unavailable, record the blocker, run deterministic
no-LLM smoke as fallback evidence, and do not mark the milestone gate satisfied.

## Reliability Requirements

For every long-running public benchmark eval, write and update:

- `.hermes-loop/work/phase-11/eval_heartbeat_longmemeval.json`;
- `.hermes-loop/work/phase-11/eval_heartbeat_locomo.json`.

Judge status by file evidence:

- partial growing: running;
- partial stale for more than 15 minutes and no final: stalled;
- final exists and rows match expected: completed;
- projected/no-judge or `judge_done=0`: invalid for promotion.

## Anti-Demo Completion Criteria

Phase 11 is usable only if:

- behavior is wired into the real v3/public benchmark path;
- tests and diagnostics prove selected/rendered/cited handoff behavior;
- fixed-slice and 30-case reports separate retrieval/source movement from
  judged answer quality;
- pass-to-fail and fail-to-pass lists are explicit;
- review lane confirms no case-id hacks, no v1 fallback regression, v3 default
  preserved, and kernel default unchanged.

If the implementation is plan-only, demo-only, or partial, write
`adjustment.md` or repeat execution. Do not write an advance ACK.

## Required Phase Artifacts

- `brainstorm.md`;
- `spec.md`;
- `plan.md`;
- `plan_review.md`;
- `plan_final.md`;
- `result.md`;
- `execute_review.md`;
- `case_matrix.md`;
- `review_verdict.json`;
- `ack.json` or `adjustment.md`.

Every Markdown artifact must start with `# phase: phase-11`. Every JSON artifact
must include `"phase": "phase-11"`.
