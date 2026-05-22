# phase: phase-10

# Phase 10 Context Bundle

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory
system for LongMemEval and LoCoMo, without demo-only phase completion, without
hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase: `phase-10`.

Name: Recall Memory Reliability.

Target state: `recall-evidence-reliable`.

Target chain components:

- retrieval: changed or verified;
- context composer: verified through v3/public benchmark path;
- public eval: verified through fixed failure slices and 30-case gates;
- ingest/store/answer projection/kernel loop: unchanged unless a failing test
  proves a recall-path diagnostic gap requires narrow support code.

## Why This Phase Exists Now

Phase 8 accepted full-chain LLM judge evidence showed LongMemEval at `47/50`
and LoCoMo at `30/50`. Phase 9 then replayed and classified all 20 LoCoMo
failures without changing answer or retrieval behavior. The dominant actionable
class is LoCoMo recall/session localization: 9 `session_localization_miss`
cases plus 3 broader `retrieval_miss` cases. Phase 10 must target that repeated
recall failure class before expanding to evidence handoff or answer projection.

Invalid heartbeat retry run ids remain invalid for promotion evidence:

- `phase8_lme50_hb_20260522T160637Z`
- `phase8_locomo50_hb_20260522T160637Z`

## Current Hypothesis

The current recall path overweights local lexical overlap and weak same-session
anchors. For LoCoMo, this causes retrieved evidence to cluster around plausible
but wrong sessions while indexed expected sources remain absent from retrieved,
selected, and rendered evidence. A conservative evidence-packet improvement
should improve or precisely reclassify repeated LoCoMo session-localization
misses without materially collapsing LongMemEval.

Disconfirming evidence:

- focused tests show the expected LoCoMo-like source is already retrieved and
  the bottleneck is downstream selection/rendering;
- LoCoMo 30 has no same-case explainable improvement and does not convert a
  repeated retrieval/session miss into a more precise downstream class;
- LongMemEval 30 materially regresses;
- any change relies on case ids, expected answers, benchmark-specific constants,
  or enables the opt-in kernel by default.

## Scope

Allowed:

- improve `RecallMemorySearcher`, `RecallPipeline`, query analysis, or recall
  diagnostics;
- add an evidence-packet style structure in metadata if it is populated from
  real recall features and consumed by the real v3/public benchmark path;
- add failing tests before implementation for at least one real repeated
  LoCoMo failure class;
- write phase-local fixed-slice reports and case movement tables.

Non-goals:

- do not change answer prompts/projection unless a recall diagnostic test proves
  a missing handoff field blocks Phase 10 evidence;
- do not change scoring semantics;
- do not change `MEMORYOS_MEMORY_ARCH=v1` fallback behavior;
- do not enable `MEMORYOS_AGENT_KERNEL=v1` by default;
- do not add Letta as a runtime dependency;
- do not claim production readiness or aggregate-only benchmark improvement.

## State Snapshot

From `.hermes-loop/state.json`:

- `current_state`: `GOD_DISPATCH`;
- `execute_lane.phase`: `phase-10`;
- `execute_lane.state`: `GOD_DISPATCH`;
- `plan_lane.phase`: `phase-11`;
- `phase-9.status`: `completed`;
- `phase-10.status`: `in_progress`;
- `last_updated`: `2026-05-22T17:40:48.878261+00:00`.

The worktree already had pre-existing dirty changes in:

- `.hermes-loop/blueprint.md` adding the parallel LongMemEval/LoCoMo milestone
  eval rule;
- `AGENTS.md` and `CLAUDE.md` adding an autonomous-mode header.

Treat these as existing user/controller context. Do not revert them.

## Active Blueprint Sections

Read `.hermes-loop/blueprint.md` first, especially:

- `Current Baseline And Phase 8 Evidence`;
- `Hard Constraints`;
- `Superpowers And Goal Discipline`;
- `Context Bundle Requirement`;
- `Full-Chain LLM Judge Gates`;
- `Letta Comparison Map`;
- `Promoted Phase 9-15 Loop`;
- `Phase 10 - Recall Memory Reliability`.

Phase 10 ACK gate:

- at least one repeated LoCoMo retrieval/session failure class improves or is
  converted into a more precise downstream failure class;
- LoCoMo 30 has same-case explainable signal;
- every pass-to-fail is listed with cause and disposition;
- no material LongMemEval collapse;
- all new behavior is explained in `case_matrix.md`.

## Required Read-First Files

MemoryOS:

- `.hermes-loop/work/phase-10/context_bundle.md`;
- `.hermes-loop/work/phase-10/god_dispatch.json`;
- `.hermes-loop/work/phase-9/ack.json`;
- `.hermes-loop/work/phase-9/result.md`;
- `.hermes-loop/work/phase-9/case_matrix.md`;
- `.hermes-loop/work/phase-9/failure_taxonomy.md`;
- `.hermes-loop/work/phase-9/replay_cases/*.json`;
- `docs/known-issues.md`;
- `docs/public-benchmark-diagnosis.md`;
- `docs/agentic-memory-roadmap-zh.md`;
- `src/memoryos_lite/retrieval/episode_searcher.py`;
- `src/memoryos_lite/retrieval/recall_pipeline.py`;
- `src/memoryos_lite/retrieval/query_analyzer.py`;
- `src/memoryos_lite/public_benchmarks.py`;
- `src/memoryos_lite/public_case_diagnostics.py`;
- `src/memoryos_lite/public_failure_replay.py`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/engine.py`;
- `tests/test_episode_retrieval.py`;
- `tests/test_recall_pipeline.py`;
- `tests/test_public_benchmarks.py`.

Letta reference files, design-only:

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`;
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`;
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`;
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`.

Use Letta for semantics such as passage-level evidence, scope, provenance, and
component accounting. Do not port Letta internals blindly.

## Current Recall Implementation Snapshot

Current anchors:

- `RecallPipeline.build_context()` ensures episodes, converts them to
  `RecallMemoryEntry`, runs `QueryAnalyzer`, calls `RecallMemorySearcher`, then
  projects hits into `ContextPackage.retrieved_evidence`.
- `RecallMemorySearcher.search()` uses BM25 plus token overlap, optional role,
  temporal, and multi-session boosts, then adds neighbors.
- Neighbor expansion respects `benchmark_session_id` when both hit and neighbor
  have one. With `preserve_neighbors=True`, it expands only when direct hits
  leave space or at least two selected direct hits share the same benchmark
  session.
- Recall metadata already exposes candidate/planned ids, indexed source ids,
  `rank_features`, `neighbor_of`, `neighbor_offset`, `benchmark_session_id`,
  `benchmark_date`, and recall diagnostics.

Known risk:

- Direct-hit selection can fill candidate space with wrong-session anchors
  before weak but useful same-session evidence is pulled in.
- LoCoMo question text often contains broad terms such as Caroline/Melanie,
  education, relationship, support, counseling, research, and dates. Lexical
  overlap alone can prefer wrong sessions that share topical words.

## Baseline And Case-Level Evidence

Valid Phase 8 reports:

- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`;
- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`.

Accepted Phase 8 full-chain LLM judge baseline:

- LongMemEval: `47 pass / 3 fail`;
- LoCoMo: `30 pass / 20 fail`;
- no same-subset pass-to-fail recorded;
- kernel default off.

Phase 9 LoCoMo failed-case path distribution:

- `session_localization_miss`: 9;
- `retrieval_miss`: 3;
- `temporal_date_miss`: 4;
- `evidence_rendered_answer_fails`: 3;
- `refusal_despite_evidence`: 1.

Session-localization cases:

- `conv-26_qa_003`;
- `conv-26_qa_004`;
- `conv-26_qa_008`;
- `conv-26_qa_011`;
- `conv-26_qa_019`;
- `conv-26_qa_020`;
- `conv-26_qa_035`;
- `conv-26_qa_036`;
- `conv-26_qa_050`.

Broader retrieval miss cases:

- `conv-26_qa_025`;
- `conv-26_qa_039`;
- `conv-26_qa_044`.

Answer-layer cases are out of Phase 10 scope unless converted by improved
recall diagnostics:

- `conv-26_qa_006`;
- `conv-26_qa_012`;
- `conv-26_qa_016`;
- `conv-26_qa_024`;
- `conv-26_qa_027`;
- `conv-26_qa_033`;
- `conv-26_qa_041`;
- `conv-26_qa_048`.

Example RED evidence from Phase 9:

- `conv-26_qa_003` asks: "What fields would Caroline be likely to pursue in
  her educaton?"
- expected sources: `D1:9`, `D1:11`;
- expected session: `D1`;
- retrieved candidate sessions: `D10`, `D13`, `D18`, `D19`, `D4`, `D7`;
- expected session absent from retrieval candidate sessions;
- benchmark data shows `D1:9` says Caroline will continue education and check
  career options; `D1:11` says counseling or mental health.

Another RED candidate:

- `conv-26_qa_004` asks: "What did Caroline research?"
- expected source: `D2:8`;
- expected session: `D2`;
- retrieved candidate sessions: `D1`, `D10`, `D17`, `D19`;
- expected session absent.

## Pass-To-Fail Risks

- Expanding neighbors too aggressively can pull unrelated sessions into LoCoMo
  evidence and degrade source grounding.
- Increasing recall top-k or preserving too many neighbors can consume context
  budget and turn retrieval misses into render drops.
- Query boosts tied to names or case ids are benchmark hacks and invalid.
- Temporal/date boosts can help `when` questions but hurt general entity
  questions if dates dominate text.
- LongMemEval already has high pass rate, so the regression guard must be read
  case by case, not only by aggregate score.

## Required Failing Tests Before Implementation

At least one RED test must fail before production code changes. Acceptable RED
targets:

- a `RecallMemorySearcher` or `RecallPipeline` test proving a LoCoMo-like weak
  same-session anchor is lost to wrong-session lexical hits;
- a public benchmark fixed-slice diagnostic test proving an expected source
  from a repeated Phase 9 class is absent from retrieved ids;
- a regression test proving unrelated session neighbors are not pulled in after
  the fix;
- a LongMemEval-style guard where a high-quality direct hit remains ahead of
  added neighbors.

Do not write a test that depends on a hard-coded benchmark case id or expected
answer string to change retrieval behavior.

## Expected Commands

Focused tests first:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
uv run pytest tests/test_public_benchmarks.py -q
uv run ruff check .
```

Baseline checks unless scoped down with evidence:

```bash
uv run pytest -q
uv run ruff check .
```

Fixed failure-slice full-chain smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --llm-answer \
  --llm-judge
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

- `.hermes-loop/work/phase-10/eval_heartbeat_longmemeval.json`;
- `.hermes-loop/work/phase-10/eval_heartbeat_locomo.json`.

Judge status by file evidence:

- partial growing: running;
- partial stale for more than 15 minutes and no final: stalled;
- final exists and rows match expected: completed;
- projected/no-judge or `judge_done=0`: invalid for promotion.

If a 50-case eval is needed and stalls, split into 10-case shards under
`.hermes-loop/work/phase-10/shards/`; never modify original benchmark files.

## Anti-Demo Completion Criteria

Phase 10 is usable only if:

- behavior is wired into the real v3/public benchmark path;
- tests and diagnostics prove the claimed repeated LoCoMo failure class;
- fixed-slice and 30-case case-level reports separate retrieval/source metrics
  from judged answer quality;
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

Every Markdown artifact must start with `# phase: phase-10`. Every JSON artifact
must include `"phase": "phase-10"`.

