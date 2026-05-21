# phase: phase-1

# Context Bundle - Phase 1 Letta Gap Matrix And Contract Decisions

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Phase Objective

Phase 1 turns the Letta comparison targets into MemoryOS-specific, benchmark-impact-ranked contracts before code changes.

Target chain components:

```text
Letta reference semantics
  -> MemoryOS current v3 contracts and public benchmark diagnostics
  -> gap matrix
  -> testable contract decisions for later phases
```

This phase is contract and evidence planning work. It must not optimize retrieval, context composition, answer projection, or kernel behavior.

## Why This Phase Exists Now

Phase 0 reached `ack_level=usable` as a no-code baseline freeze and committed the ACK/advance artifacts in commit `1dce733`.

Current state now points to:

```json
{
  "current_state": "GOD_DISPATCH",
  "current_phase_idx": 1,
  "execute_lane": {"phase": "phase-1", "state": "GOD_DISPATCH"},
  "plan_lane": {"phase": "phase-2", "state": "PLAN_STORM"},
  "research_lane": {"phases": ["phase-3"]}
}
```

Phase 0 reflection recommended `no_adjustment`: do not reorder phases yet. Instead, Phase 1 must consume the Phase 0 case taxonomy as priority input:

- LongMemEval visible smoke weakness is mostly `evidence_hit_answer_fail`.
- LoCoMo visible smoke weakness is mostly `retrieval_miss`.
- Kernel smoke is trace-presence evidence only, not answer-quality evidence.

## Current Hypothesis

The useful next move is not to port Letta wholesale. The useful move is to map Letta semantics to small MemoryOS contracts that later phases can test in the real v3/public benchmark path.

Disconfirming evidence:

- The Letta comparison cannot be tied to current MemoryOS files and benchmark failure modes.
- High-priority gaps do not map to future failing tests or benchmark cases.
- The phase proposes broad ports, runtime Letta dependency, or implementation before contract decisions.
- LoCoMo retrieval/scope failures are hidden behind LongMemEval answer-projection failures, or vice versa.
- The v3 kernel is treated as default instead of opt-in.

## Scope

In scope:

- Read the context bundle before any other phase-local artifact.
- Compare the required Letta source files with current MemoryOS v3 files.
- Produce `work/phase-1/research.md` with read-only Letta/MemoryOS observations if using a research lane.
- Produce `work/phase-1/letta_gap_matrix.md` with MemoryOS current behavior, Letta reference behavior, gap, benchmark impact, priority, and proposed contract.
- Produce `brainstorm.md`, `spec.md`, `plan.md`, `plan_review.md`, and `plan_final.md` for testable contract decisions.
- Decide exact contracts for core memory blocks, archive attachment, passage scope, context component accounting, answer citation, and kernel trace/tool result.
- Map every high-priority gap to a future failing test or benchmark case.

Non-goals:

- No `src/`, `tests/`, `alembic/`, benchmark-data, or active docs changes.
- No retrieval, context composer, answer prompt, or kernel behavior optimization.
- No Letta runtime dependency.
- No benchmark case-id hacks or expected-answer leaks.
- No state promotion from plan text alone.
- No default kernel enablement.

## Lane Write Protocol

Follow the lane model:

- `research_lane` may write only `work/phase-1/research.md`.
- `plan_lane` may write only `brainstorm.md`, `spec.md`, `plan.md`, `plan_review.md`, and `plan_final.md`.
- `execute_lane` owns the final phase-1 `letta_gap_matrix.md`, `result.md`, `execute_review.md`, review verdict, and ACK artifacts.

If a research output is needed for `letta_gap_matrix.md`, execute lane must consume it and write the matrix. Do not let a research lane write outside its allowed file.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` sections:

- Purpose and Current Baseline.
- Hard Constraints.
- Completion Levels.
- Context Bundle Requirement.
- Letta Comparison Map.
- Phase 1 - Letta Gap Matrix And Contract Decisions.
- Dynamic Blueprint Amendment Protocol.
- Stop Conditions.

No promoted amendment is active. Phase 0 reflection explicitly recommends no blueprint adjustment before Phase 1.

## Required Letta Reference Files

Use these as design references only. Do not add Letta as a runtime dependency.

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

Observed Letta surface from startup inspection:

- `Block`, `Memory`, `Archive`, and `Passage` schemas exist.
- `BlockManager`, `ArchiveManager`, and `PassageManager` expose CRUD/attach/search-style managers.
- `LettaCoreToolExecutor` exposes core/archival memory tools.
- `ToolExecutionManager` routes tool execution.
- `LettaAgentV3` owns request build, step/stream, tool handling, checkpoint, continuation, and compaction behavior.
- `ContextWindowCalculator` extracts system components and calculates context-window usage.

## Required MemoryOS Read-First Files

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/schemas.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/core_memory.py`
- `src/memoryos_lite/memory_lifecycle.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/tools.py`
- `tests/test_v3_contracts.py`
- `tests/test_core_memory_service.py`
- `tests/test_archival_store.py`
- `tests/test_archival_searcher.py`
- `tests/test_context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_kernel.py`
- `docs/memory-v3-architecture.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`

## Relevant Prior Artifacts

- `work/phase-0/baseline_case_matrix.md`
- `work/phase-0/ack.json`
- `work/phase-0/review_verdict.json`
- `work/phase-0/reviews/codex-review-rerun.md`
- `work/phase-0/reflect_phase-0.md`
- `.memoryos/evals/phase0_v3_lme_5case_longmemeval.json`
- `.memoryos/evals/phase0_v3_locomo_5case_locomo.json`
- `.memoryos/evals/phase0_v3_kernel_locomo_1case_locomo.json`

## Current Benchmark Baseline

Phase 0 deterministic no-LLM smoke:

- LongMemEval limit 5: `1/5` projected.
  - pass: `1e043500`
  - retrieval miss: `58bf7951`
  - evidence hit but answer fail: `e47becba`, `118b2229`, `51a45a95`
- LoCoMo limit 5: `0/5` projected.
  - retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`
  - evidence hit but answer fail: `conv-26_qa_001`
- Opt-in kernel LoCoMo limit 1: trace sequence present only with `MEMORYOS_AGENT_KERNEL=v1`; answer still projected fail.

These are smoke diagnostics, not global benchmark claims.

## Known Pass-To-Fail Risks

- Treating Letta comparison as a broad port instead of a small contract map.
- Letting aggregate priority hide LoCoMo-specific retrieval/scope failures.
- Letting LongMemEval evidence-hit failures hide answer-projection contract needs.
- Treating `source_hit` as pure evidence localization.
- Proposing prompt-only changes as architecture without a testable answer evidence contract.
- Accidentally treating the opt-in kernel as default.
- Producing plan-only artifacts that cannot be consumed by Phase 2+ dispatch.

## Expected Outputs

Minimum phase-1 artifacts:

- `work/phase-1/context_bundle.md`
- `work/phase-1/god_dispatch.json`
- `work/phase-1/research.md`
- `work/phase-1/letta_gap_matrix.md`
- `work/phase-1/brainstorm.md`
- `work/phase-1/spec.md`
- `work/phase-1/plan.md`
- `work/phase-1/plan_review.md`
- `work/phase-1/plan_final.md`
- `work/phase-1/result.md`
- `work/phase-1/execute_review.md`
- `work/phase-1/reviews/*.md`
- `work/phase-1/ack.json` only if usable.

## Verification Commands

Phase 1 is read-only/contract work. Use these checks unless execution narrows the scope with evidence:

```bash
python -m json.tool .hermes-loop/work/phase-1/god_dispatch.json
```

```bash
test "$(sed -n '1p' .hermes-loop/work/phase-1/context_bundle.md)" = "# phase: phase-1"
```

```bash
rg -n "source_hit|LoCoMo|LongMemEval|MEMORYOS_AGENT_KERNEL|Letta|contract" .hermes-loop/work/phase-1
```

No full benchmark run is required for Phase 1 unless the phase changes behavior, which it should not.

## Anti-Demo Usable ACK Criteria

Phase 1 may ACK only if:

- `letta_gap_matrix.md` exists and is explicitly consumed by `result.md`, `execute_review.md`, review, and ACK.
- Every high-priority gap maps to a future failing test or concrete benchmark case.
- LongMemEval and LoCoMo impacts are separated.
- The output contains contract decisions, not just observations.
- No "just port Letta" open-ended task remains.
- No runtime dependency on Letta is introduced.
- No code, benchmark data, state, or blueprint behavior changes are made by the phase.
- The v1 fallback, v3 default, and kernel opt-in constraints remain explicit.
