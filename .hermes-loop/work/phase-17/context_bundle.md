# phase: phase-17

# Phase 17 Context Bundle

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Every lane must read this file before any other phase-local artifact. A lane
result that ignores this bundle, contradicts it without explicit evidence, or
uses remembered prior chat context is stale.

## Phase Binding

- Execute lane phase: `phase-17`.
- State after Phase 16 GOD_ADVANCE: `.hermes-loop/state.json` has
  `current_state = GOD_DISPATCH`, `current_phase_idx = 17`,
  `execute_lane.phase = phase-17`, `execute_lane.state = GOD_DISPATCH`.
- `phase-16` is completed with usable ACK and commit `f96c611`.
- `phase-17` is `in_progress`; `phase-18` remains `pending`.
- Bootstrap safety: `work/phase-17/` was missing at phase start, so this
  controller turn may generate only phase-local context, dispatch, and planning
  artifacts. Do not implement, run tests, run evals, or modify product code
  until a later bootstrap sees `context_bundle.md`, `god_dispatch.json`, and
  `plan_final.md` already present and promotes to `EXECUTE`.

## Phase Objective

Plan the K4 LoCoMo maintenance repair measurement slice. The implementation
phase must prove whether kernel-created maintenance artifacts can improve or
better explain LoCoMo source localization and answer-quality failures when
consumed through the real MemoryOS v3 public benchmark path, without turning
same-slice repair smoke into promotion evidence.

Target chain components:

- `kernel_loop`: opt-in only; use Phase 16 Level 1 tools through
  `SimpleAgentStepRunner.run_step()` with approval/replay/source grounding.
- `store`: isolated repair-smoke store state for approved maintenance artifacts;
  no writes to benchmark source files and no global persistent repair cache.
- `retrieval`: measured and diagnosed; change only if the chosen plan proves
  maintenance artifacts need a small real-path integration for v3 consumption.
- `context_composer`: verify repair artifacts enter v3 only through eligible
  archive attachments or approved lifecycle artifacts, not direct injection.
- `answer_projection`: measured by full-chain LLM answer/judge where available;
  do not make prompt-only or answer-only changes unless evidence shows answer
  projection is the bottleneck and the plan records that as a narrowed repair.
- `public_eval`: same-slice before/after reports with case-level movement and
  trace evidence; clean held-out or clean-store validation before any quality
  claim.
- `ingest`: not a target except as the existing public benchmark ingestion path.

## Why This Phase Exists Now

Phase 16 made K3 usable for Level 1 mutating tools:

- executable tools are bounded to `archive_write`, `archive_attach`, and
  `core_promotion_request`;
- `recall_search`, `archive_search`, `core_memory_append`,
  `core_memory_replace`, destructive tools, and unknown tools remain closed;
- opened tools are registry-backed, policy-gated, approval-bound, service-backed,
  verified, traced, and tested;
- malformed approved replay now fails closed instead of raising from the opt-in
  kernel path;
- public kernel traces remain default-off and appear only with
  `MEMORYOS_AGENT_KERNEL=v1`.

Phase 17 is the first chance to test whether this real tool surface can produce
useful LoCoMo repair evidence, while maintaining strict anti-overfitting and
source-grounding rules.

## Current Hypothesis

A fixed LoCoMo same-slice repair smoke can be useful if:

- baseline failures are classified before any maintenance writes;
- maintenance proposals are derived only from model-visible retrieval,
  evidence, answer, and v3 context diagnostics;
- approved kernel tool calls create durable maintenance artifacts in an
  isolated repair-smoke store;
- the same fixed LoCoMo slice is rerun and case-level movement is reported;
- any useful movement is validated in a clean held-out or clean-store run before
  claiming benchmark quality.

Disconfirming evidence:

- maintenance arguments include expected answers, expected source ids, judge
  labels, gold-derived failure classes, or benchmark case ids as executable
  inputs;
- default public reports emit kernel traces without `MEMORYOS_AGENT_KERNEL=v1`;
- repair artifacts enter context through direct injection rather than v3
  eligibility/scope/provenance rules;
- same-slice pass rate changes but source grounding regresses or pass-to-fail
  cases are unexplained;
- LoCoMo remains unexplained while only LongMemEval improves;
- evals are no-LLM/projected but are presented as full-chain quality evidence.

## Exact Scope

Plan a smallest usable Phase 17 implementation. It may include:

- fixed LoCoMo 10-case baseline and post-maintenance report comparison;
- a repair-smoke harness that runs approved Phase 16 Level 1 tools against an
  isolated store using model-visible planner artifacts only;
- case-level movement analysis for `fail_to_pass`, `pass_to_fail`,
  `unchanged_fail`, `retrieval_miss`, `evidence_hit_answer_fail`,
  `context_missing_evidence`, unsupported/overconfident answers, and
  questionable judges;
- trace and report checks proving no benchmark gold fields become executable
  tool inputs;
- clean-store or held-out validation setup before any benchmark-quality claim.

The plan may narrow further if LLM provider access is unavailable, but that
fallback cannot satisfy a full-chain quality gate. It may produce diagnostic
or blocking artifacts rather than pretending no-LLM smoke is promotion evidence.

## Explicit Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change the default `v3` memory architecture or remove
  `MEMORYOS_MEMORY_ARCH=v1`.
- Do not add Letta as a runtime dependency.
- Do not open Level 2 search tools or Level 3 core edit tools unless the plan
  explicitly adds RED tests, approval/source/provenance rules, and review
  gates for that narrower slice.
- Do not write benchmark-case-specific rules, case-id hacks, expected-answer
  memories, expected-source sidecars, or judge-label-derived repairs.
- Do not claim global benchmark improvement from same-slice LoCoMo repair smoke
  or from LongMemEval-only evidence.
- Do not overwrite benchmark files or commit runtime eval reports under
  `.memoryos/evals`.
- Do not rewrite `.hermes-loop` orchestration infrastructure.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` sections:

- `Hard Constraints`
- `Superpowers And Goal Discipline`
- `Completion Levels`
- `Required ACK Evidence`
- `Context Bundle Requirement`
- `Execute Goal Contract`
- `Full-Chain LLM Judge Gates`
- `Kernel And Eval Boundary`
- `Kernel Agent Graduation Blueprint`
- `Hybrid Tool Selection Boundary`
- `Phase Mapping For Active Loop`
- `Phase 17 - LoCoMo Maintenance Repair Eval`
- `Phase 18 - Benchmark Governance And Promotion`

Phase 17 blueprint summary:

- Target state: `locomo-maintenance-repair-measured`.
- Required pattern: fixed LoCoMo slice -> model-visible proposals -> approved
  maintenance writes in isolated repair-smoke store -> rerun same slice -> freeze
  generic rules/artifacts -> clean held-out or clean-store validation before any
  quality claim.
- Eval gate: fixed LoCoMo 10-case same-subset full-chain LLM judge; LoCoMo
  30-case full-chain only from clean store or held-out validation after useful
  and explainable source movement; LongMemEval 30-case regression guard if
  maintenance artifacts affect default v3 selection.
- ACK gate: source localization improves or failure classes become more precise;
  no hidden source-grounding regression; LoCoMo reported separately; kernel
  default remains off.

## Required Read-First MemoryOS Files

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/config.json`
- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/work/phase-16/ack.json`
- `.hermes-loop/work/phase-16/result.md`
- `.hermes-loop/work/phase-16/execute_review.md`
- `.hermes-loop/work/phase-16/review_verdict.json`
- `.hermes-loop/work/phase-16/reflect_phase-16.md`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_maintenance_planner.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/agent_kernel_tools.py`
- `src/memoryos_lite/agent_tool_registry.py`
- `src/memoryos_lite/agent_tool_selection.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `src/memoryos_lite/engine.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_kernel.py`
- `tests/test_context_composer.py`
- `tests/test_memory_lifecycle.py`

## Required Letta Reference Files

Use these as design references only. Do not import Letta.

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

Compare for: approval-bound tool calls, archival passage scope, core-memory
candidate semantics, tool return isolation, and context-window accounting.

## Current Baseline And Case Findings

Accepted prior milestone evidence:

- Phase 8 LongMemEval 50 full-chain LLM judge: `47/50`.
- Phase 8 LoCoMo 50 full-chain LLM judge: `30/50`.
- Phase 10 LongMemEval 30 full-chain LLM judge: `29 pass / 1 fail`,
  `pass_to_fail=0`, remaining evidence-hit-answer-fail `51a45a95`.
- Phase 10 LoCoMo 30 full-chain LLM judge: `20 pass / 10 fail`,
  `fail_to_pass=conv-26_qa_011, conv-26_qa_012`, `pass_to_fail=0`,
  remaining retrieval miss `6`, remaining evidence-hit-answer-fail `4`.

Invalid evidence:

- `phase8_lme50_hb_20260522T160637Z` and
  `phase8_locomo50_hb_20260522T160637Z` were killed/partial/projected and
  cannot support promotion.

Most recent Phase 16 structural LoCoMo 5-case no-LLM smoke:

- default-off report: 5 rows, all projected fail, kernel trace lengths
  `[0, 0, 0, 0, 0]`;
- opt-in report: 5 rows, all projected fail, kernel trace lengths
  `[14, 14, 14, 14, 14]`;
- `conv-26_qa_001`, `conv-26_qa_002`: evidence-hit-answer-fail;
- `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`: retrieval-miss.

These Phase 16 reports are structural only and must not be used as quality
evidence.

## Known Pass-To-Fail Risks

- The maintenance harness could accidentally use `eval_gold_sidecar` fields as
  tool inputs.
- Same-slice repair writes could overfit and make held-out or clean-store
  validation worse.
- Kernel-created archive writes could pollute v3 context if scope/attachment
  eligibility is too broad.
- Pending core promotion candidates could be treated as visible core memory
  before approval/application.
- Tool result messages could become answer context pollution if not marked and
  scoped.
- Full-chain LLM answer/judge availability may be missing; no-LLM smoke cannot
  satisfy a quality gate.
- LoCoMo source localization can regress even when judged answer pass rate
  improves.

## Failing Tests Or Concrete Cases To Start From

Use Phase 16 smoke cases as the initial fixed slice for structural planning, but
do not tune rules to their ids:

- `conv-26_qa_001`, `conv-26_qa_002`: evidence-hit-answer-fail.
- `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`: retrieval-miss.

Phase 17 must add RED tests before product changes for:

- maintenance repair harness refuses to execute proposals that contain
  expected answers, expected source ids, judge labels, gold failure classes, or
  case ids as executable tool inputs;
- approved repair-smoke writes use only model-visible planner fields and
  approved Phase 16 tools;
- repair artifacts are stored in an isolated run/store and do not mutate the
  original benchmark data or default public path;
- before/after case comparison reports fail-to-pass, pass-to-fail, unchanged
  failures, retrieval misses, evidence-hit-answer-fail, judge-questionable, and
  source metric movement separately for LoCoMo.

## Expected Commands

Planning should preserve these commands unless it narrows them with evidence.

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

Phase 17 fixed-slice LoCoMo full-chain gate, when LLM provider access is
available:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --run-id phase17_locomo10_baseline
```

Opt-in repair-smoke rerun must remain explicit:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --run-id phase17_locomo10_kernel_repair_smoke
```

LongMemEval regression guard is required if Phase 17 changes default v3 context
selection, retrieval, answer projection, or non-kernel public behavior:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --run-id phase17_lme30_regression_guard
```

LongMemEval and LoCoMo must run in parallel if both are required for a
milestone gate.

## Anti-Demo Completion Criteria

Phase 17 can ACK only at `ack_level = usable` if:

- the result enters the real MemoryOS v3/public benchmark path;
- maintenance artifacts are created through approved Phase 16 kernel/tool
  calls, not direct demo fixtures;
- focused RED/GREEN tests prove gold-field denial, isolation, case movement,
  and source-grounding behavior;
- LoCoMo case-level before/after evidence is recorded without hiding
  pass-to-fail cases;
- review verdict passes and eval routing is explicit under the Review Eval
  Autonomy Policy;
- v1 fallback, v3 default, and kernel opt-in constraints remain intact;
- any quality claim is limited to the evidence actually run, and same-slice
  movement is not promoted as global improvement.
