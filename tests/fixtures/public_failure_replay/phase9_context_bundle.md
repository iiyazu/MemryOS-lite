# phase: phase-9

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Phase Objective

Phase 9: Evidence Closure And Failure Replay.

Target state: `failure-replay-ready`.

Target chain component: public benchmark diagnostics and replay artifacts for
the real MemoryOS v3 public benchmark path. This phase is diagnostic-first. It
may add diagnostic helpers, replay artifact writers, tests for failure-class
completeness, and phase-local reports. It must not change retrieval or answer
behavior unless a failing diagnostic test proves the current report cannot
classify real cases.

## Why This Phase Exists Now

Phase 8 produced valid 50-case full-chain LLM judge evidence:

- LongMemEval: `47/50`, report
  `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`.
- LoCoMo: `30/50`, report
  `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

LongMemEval is strong but not sufficient for promotion. LoCoMo is the
controlling bottleneck, and its failures split between retrieval/session
localization misses and evidence-hit-answer-fail cases. Phase 9 exists to make
those failures replayable and classified from query through judge result before
Phase 10 attempts recall changes.

Invalid artifacts to ignore for promotion or phase-9 baseline:

- `phase8_lme50_hb_20260522T160637Z`
- `phase8_locomo50_hb_20260522T160637Z`

Those heartbeat retry runs were killed/partial/projected and are invalid for
promotion evidence.

## Current Hypothesis

The next useful improvement depends on separating LoCoMo failures into
path-level causes:

```text
indexed -> retrieved -> selected -> rendered -> cited -> judged
```

Hypothesis: current public benchmark report rows already contain enough fields
to generate a replay matrix for the 20 phase-8 LoCoMo failures, but the project
lacks a durable per-case replay schema and completeness checks.

Disconfirming evidence:

- a phase-8 LoCoMo failure row cannot provide expected source ids, indexed
  source status, retrieved ids, selected ids, rendered ids, answer output,
  citation/source support, judge result, or final failure class;
- current diagnostics collapse session, temporal, speaker/entity, selection,
  render, citation, and judge issues into too few classes;
- replay artifacts cannot distinguish path-level patterns from case-level
  evidence without adding or repairing diagnostic fields.

If disconfirmed, Phase 9 should add the minimal append-only diagnostic fields
and tests needed to classify the real path. It should not patch answer quality
or retrieval ranking during this phase.

## Scope

Allowed:

- read phase-8 public benchmark reports;
- add a replay/taxonomy helper module if needed;
- add CLI or scriptable diagnostics only if wired to existing MemoryOS modules;
- add tests for replay artifact completeness and failure class mapping;
- write:
  - `work/phase-9/failure_taxonomy.md`
  - `work/phase-9/case_matrix.md`
  - `work/phase-9/replay_schema.md`
  - `work/phase-9/replay_cases/<case_id>.json`
  - `work/phase-9/result.md`
  - `work/phase-9/execute_review.md`
  - `work/phase-9/reviews/*.md`
  - `work/phase-9/review_verdict.json`
  - `work/phase-9/ack.json` or `work/phase-9/adjustment.md`

Non-goals:

- no retrieval ranking changes;
- no answer prompt/projection changes;
- no benchmark scoring changes;
- no case-id hacks or expected-answer leaks;
- no kernel default change;
- no Letta runtime dependency;
- no promotion from aggregate score alone.

## State Excerpt

Current state from `.hermes-loop/state.json`:

```json
{
  "current_state": "GOD_DISPATCH",
  "current_phase_idx": 9,
  "execute_lane": {"phase": "phase-9", "state": "GOD_DISPATCH"},
  "plan_lane": {"phase": "phase-10", "state": "PLAN_STORM"},
  "review_lane": {"active": false, "phase": null}
}
```

`state.json.current_state` is not `DONE`; active execution starts at
`phase-9`.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` as the active blueprint. Relevant sections:

- Purpose
- Current Baseline And Phase 8 Evidence
- Hard Constraints
- Context Bundle Requirement
- Full-Chain LLM Judge Gates
- Letta Comparison Map
- Promoted Phase 9-15 Loop
- Phase 9 - Evidence Closure And Failure Replay
- Phase 10 - Recall Memory Reliability
- Minimum Next Dispatch
- Stop Conditions

Promoted phase-8 amendment:

- `.hermes-loop/work/phase-8/blueprint_amendment.md`

The amendment adds the targeted LoCoMo reliability loop and says not to expand
eval or promote the blueprint from aggregate score. It identifies LoCoMo
retrieval/session localization and evidence-hit-answer-fail as the next
targets.

## Read First Files

MemoryOS files:

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/config.json`
- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/work/phase-8/ack.json`
- `.hermes-loop/work/phase-8/promotion_decision.md`
- `.hermes-loop/work/phase-8/blueprint_amendment.md`
- `.hermes-loop/work/phase-8/god_context.md`
- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/diagnostic_report.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_diagnostic_report.py`
- `tests/test_context_composer.py`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`

Letta reference files, for semantics only:

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

Phase 9 should borrow the idea of explicit source-attributed passages,
component accounting, and traceable tool/evidence provenance. It should not add
Letta as a dependency or port internals blindly.

## Phase 8 Baseline Cases

LongMemEval 50 failures:

- retrieval miss: `b86304ba`, `ccb36322`
- evidence-hit-answer-fail: `51a45a95`

LoCoMo 50 failures to replay and classify:

- retrieval/session misses:
  `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`,
  `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`,
  `conv-26_qa_025`, `conv-26_qa_035`, `conv-26_qa_036`,
  `conv-26_qa_039`, `conv-26_qa_044`, `conv-26_qa_050`
- evidence-hit-answer-fail:
  `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`,
  `conv-26_qa_024`, `conv-26_qa_027`, `conv-26_qa_033`,
  `conv-26_qa_041`, `conv-26_qa_048`
- judge/source-support questionable:
  `conv-26_qa_015`

The phase-9 ACK gate is based on the 20 failed LoCoMo cases. The questionable
passing case should be tracked in the taxonomy as judge/source-support risk but
must not be hidden as a failure or used to inflate fail counts.

## Required Failure Classes

The replay matrix must support:

- retrieval miss
- session localization miss
- temporal/date miss
- speaker/entity confusion
- evidence retrieved but not selected
- evidence selected but not rendered
- evidence rendered but answer fails
- unsupported citation
- refusal despite evidence
- judge questionable
- diagnostic gap

Existing report-level classes such as `retrieval_miss`,
`context_missing_evidence`, `unsupported_answer`, `evidence_hit_answer_fail`,
and `judge_questionable` may be retained, but Phase 9 must add path-level
classification or replay fields when needed to distinguish the required
failure classes.

## Expected RED Evidence

Before production changes, add focused failing tests that prove at least one of
these current gaps:

- a real phase-8 LoCoMo failure row cannot be transformed into a complete
  replay row/artifact with all required fields;
- required path-level classes such as session localization, temporal/date,
  selected-but-not-rendered, unsupported citation, or refusal despite evidence
  are not represented by the replay schema;
- generated replay artifacts do not keep retrieval/source metrics separate
  from judged answer metrics.

If no production code is needed because existing reports are sufficient, this
phase may write phase-local artifacts and tests for the artifact generator, but
the ACK must explicitly mark behavior changes as not applicable and prove
real-path report rows were consumed.

## Smoke And Verification Commands

Focused tests first, then baseline checks:

```bash
uv run pytest tests/test_diagnostic_report.py tests/test_public_benchmarks.py -q
uv run pytest -q
uv run ruff check .
```

If a diagnostic helper or CLI is added, also run its focused tests directly.

Phase 9 is not a milestone quality-improvement phase. Full-chain 30-case LLM
judge runs are not required for ACK unless Phase 9 changes the real public
benchmark behavior. If behavior changes are made, run LongMemEval and LoCoMo
30-case full-chain gates in parallel and write heartbeat/partial monitor
artifacts.

No-LLM replay artifact generation from existing phase-8 reports is sufficient
only for diagnostic completeness, not for score-improvement claims.

## Pass-To-Fail Risks

- treating a projected/no-judge heartbeat retry as promotion evidence;
- collapsing LoCoMo session/temporal failures into generic retrieval misses;
- hiding `conv-26_qa_015` judge/source-support risk because it passed;
- changing answer or retrieval behavior during a diagnostic-only phase;
- breaking v1 fallback while adding v3-only diagnostic fields;
- reporting aggregate pass/fail without same-case rows.

## Anti-Demo Completion Criteria

Usable ACK requires:

- all 20 LoCoMo phase-8 failed cases are classified;
- every failed LoCoMo case has a replay row or artifact with:
  case id, question, expected source ids, indexed source status, retrieved ids,
  selected ids, rendered ids, answer output, cited/source support, judge
  result, movement status, report-level failure class, path-level failure
  class, and diagnostic notes;
- replay artifacts distinguish path-level patterns from case-level evidence;
- source metrics remain separate from judged answer metrics;
- `diagnostic_gap` cases are explicit and not hidden;
- artifacts cite this context bundle;
- review verifies no demo-only completion and no kernel default change.

## Invariants

- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and must not become default.
- SQLite remains authoritative; filesystem outputs are debug/eval artifacts.
- Public `source_hit` remains a final projection/source-overlap metric, not
  pure retrieval localization.
