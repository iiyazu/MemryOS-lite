# phase: phase-7

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Controller State

- Current state file: `.hermes-loop/state.json`.
- `current_state`: `GOD_DISPATCH`.
- `execute_lane.phase`: `phase-7`.
- `execute_lane.state`: `GOD_DISPATCH`.
- `research_lane.phases`: `phase-8`.
- Phase 7 name: `Kernel, Tool, Approval, And Memory Mutation Loop`.
- Phase 7 target state: `kernel-opt-in-usable`.
- Phase 7 status: `in_progress`.
- Phase 8 remains pending.

The repository worktree already contains unrelated/unreviewed control-file edits and deleted phase-7/phase-8 artifacts. Treat those as existing workspace state. Do not revert them. Recreate only the Phase 7 artifacts needed for the current controller pass.

## Phase Objective

Harden the opt-in v3 kernel from a minimal trace demo into an auditable control-plane slice that is useful in the real MemoryOS v3 public benchmark path.

Target chain component: `kernel_loop`, with supporting verification of `store`, `context_composer`, and `public_eval`.

This phase exists now because Phase 6 made answer projection and citation behavior usable enough to expose the remaining kernel work without hiding LoCoMo failures. Phase 6 explicitly advanced Phase 7 only as opt-in kernel/tool work and preserved `MEMORYOS_AGENT_KERNEL=v1` as non-default.

## Current Hypothesis

The smallest useful Phase 7 improvement is not a new autonomous agent. It is a durable, testable kernel contract:

- denied tools are represented as trace/control-plane results and are not executed;
- approval pause/resume state is replayable across the boundary used by benchmark/kernel smoke;
- executed tools emit result traces and, where relevant, tool result messages that can enter later context;
- public benchmark reports continue to expose `kernel_trace_events` when `MEMORYOS_AGENT_KERNEL=v1` is explicitly set;
- default v3 benchmark behavior remains kernel-off.

Disconfirming evidence:

- any kernel behavior appears when `MEMORYOS_AGENT_KERNEL` is unset/off;
- `MEMORYOS_MEMORY_ARCH=v1` behavior changes;
- a denied tool writes archival/core memory;
- tool execution succeeds but no durable trace or later-context-visible result exists;
- public benchmark kernel trace fields disappear or become misleading;
- Phase 7 claims usability using only direct unit tests while the real v3/public benchmark path is unverified.

## Scope

In scope:

- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/store.py`
- focused tests in `tests/test_agent_kernel.py`, `tests/test_public_benchmarks.py`, and any existing v3 contract/store test if needed.

Non-goals:

- Do not make `MEMORYOS_AGENT_KERNEL=v1` default.
- Do not add Letta as a dependency.
- Do not rewrite `.hermes-loop` infrastructure.
- Do not implement a broad LangGraph/LLM autonomous loop.
- Do not tune answer prompts as a kernel phase.
- Do not hide or reclassify LoCoMo retrieval misses as kernel success.
- Do not use benchmark case IDs or expected-answer leaks.

## Active Blueprint Section

Phase 7 purpose from `.hermes-loop/blueprint.md`: harden the opt-in kernel from minimal trace demo to auditable control plane.

Required Phase 7 work:

- Keep kernel opt-in with `MEMORYOS_AGENT_KERNEL=v1`.
- Persist assistant/tool/approval events in a durable trace shape.
- Add tool result messages visible to later context if relevant.
- Expand tool execution beyond minimal `archive_write` only when tied to a failing test and real chain need.
- Align approval/tool semantics with Letta agent loop: approval request, grant/deny, tool execution, continuation/stop reason.

Required failing tests:

- approval state survives the step boundary needed by benchmark/kernel smoke;
- denied tool is not executed;
- executed tool has result trace and context visibility;
- kernel trace remains present in public benchmark result when opt-in.

Conditional milestone eval:

- Run 30-case full-chain LLM judge only if kernel behavior affects benchmark answer/context path.
- Otherwise run focused kernel tests and 5/10-case kernel smoke.

Usable ACK gate:

- kernel remains opt-in;
- no default benchmark path is forced through kernel without explicit setting;
- traces explain control-plane decisions.

## Phase 6 Evidence To Preserve

Phase 6 ACK:

- `uv run pytest -q` -> `396 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.
- LongMemEval 30 full-chain LLM judge: `29/30`, `fail_to_pass=11`, `pass_to_fail=0`, `retrieval_miss=[]`, `evidence_hit_answer_fail=["51a45a95"]`.
- LoCoMo 30 full-chain LLM judge: `18/30`, `fail_to_pass=11`, `pass_to_fail=0`, `retrieval_miss=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005","conv-26_qa_008","conv-26_qa_011","conv-26_qa_019","conv-26_qa_020","conv-26_qa_025"]`, `evidence_hit_answer_fail=["conv-26_qa_006","conv-26_qa_012","conv-26_qa_016","conv-26_qa_024","conv-26_qa_027"]`.
- Kernel trace rows stayed empty in those reports because Phase 6 did not enable the opt-in kernel.

Residual risks:

- LoCoMo remains harder and still has 12 unchanged failures.
- A kernel write must not pollute default non-kernel benchmark behavior.
- The yes/no answer rule from Phase 6 has medium overfitting risk and must not be expanded in Phase 7.

## Current Code Facts

- `Settings.memoryos_memory_arch` defaults to `v3`.
- `Settings.memoryos_agent_kernel` defaults to `off`.
- `Settings.resolved_agent_kernel` accepts only `off` or `v1`.
- `MemoryOSService.agent_kernel` is constructed only when `settings.resolved_agent_kernel == "v1"`.
- `SimpleAgentStepRunner.run_step()` currently emits `kernel_step_started`, `tool_policy_decision`, approval events, `tool_executed`, and `kernel_step_completed`, then persists those as store trace events.
- `SimpleToolPolicyEngine` denies unknown tools when no rule matches.
- `ApprovalGateV1` returns `pending` on first request and `approved` when `approval_id` is supplied, but the approval state is not yet a separately durable approval record.
- `SimpleToolExecutionManager` currently supports `archive_write` only.
- `archive_write` writes `ArchivalMemory` with source refs from request or a manual approval source ref.
- In `evals.py`, public benchmark kernel probing runs only when `service.agent_kernel is not None`, v3 context exists, and `settings.resolved_memory_arch == "v3"`.
- `PublicBenchmarkResult` includes `kernel_trace_events`; public diagnostics expose `kernel_trace_present`.
- Existing tests cover pause and resume/execute, but do not fully cover denial non-execution, tool result message visibility in later context, or public benchmark trace detail beyond event names.

## Letta Reference Summary

Use `/home/iiyatu/projects/python/letta` as reference only.

Relevant semantics read for this phase:

- `letta/schemas/block.py`: block label/value/limit/description/read_only/tags shape.
- `letta/schemas/memory.py`: structured memory rendering with metadata and token-visible block sections.
- `letta/schemas/archive.py`: archive identity, metadata, vector provider, embedding config.
- `letta/schemas/passage.py`: passage text plus archive/source/file/tags/metadata and deletion flag.
- `letta/services/block_manager.py`: block CRUD and prompt rebuild/checkpoint semantics.
- `letta/services/archive_manager.py`: archive create/list/attach/detach/default and passage creation.
- `letta/services/passage_manager.py`: agent passage vs source passage operations and invariants.
- `letta/services/tool_executor/tool_execution_manager.py`: executor routing, return truncation, metrics, error result shape.
- `letta/services/tool_executor/core_tool_executor.py`: direct core tools, unknown-tool errors, conversation search, archival insert/search, memory edits.
- `letta/agents/letta_agent_v3.py`: step loop, approval request/response, denials as tool returns, execution, continuation, stop reasons, context compaction.
- `letta/services/context_window_calculator/context_window_calculator.py`: system component extraction and context-window component accounting.

MemoryOS should borrow semantics, not internals. Phase 7 should prefer a small durable trace/message contract over porting Letta's full agent loop.

## Read First

MemoryOS files:

- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/work/phase-6/ack.json`
- `.hermes-loop/work/phase-6/result.md`
- `.hermes-loop/work/phase-6/review_verdict.json`
- `.hermes-loop/work/phase-6/reflect_phase-6.md`
- `.hermes-loop/work/phase-6/blueprint_amendment.md`
- `docs/known-issues.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/agentic-memory-roadmap-zh.md`
- `src/memoryos_lite/config.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/store.py`
- `tests/test_agent_kernel.py`
- `tests/test_public_benchmarks.py`
- `tests/test_context_composer.py`
- `tests/test_evals.py`

Letta reference files:

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

## Previous Artifacts

- Phase 6 artifacts are current and must be preserved as baseline evidence.
- `.hermes-loop/work/phase-7/reviews/codex-review.md` exists but predates this context bundle and does not cite it. Treat it as stale and non-blocking historical residue, not current review evidence.
- Phase 8 research exists but targets old legacy deprecation language and is stale relative to the active blueprint.

## RED Starting Points

Add or update failing tests before production changes:

- A denied `archive_write` or unknown tool request produces a denial trace/result and does not create archival memory.
- A resumed approval executes exactly once and records replayable approval/tool result trace details.
- A successful tool execution produces a tool result message/log entry visible to a later v3 context build when relevant.
- Public benchmark with `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1` reports non-empty `kernel_trace_events`.
- Public benchmark without `MEMORYOS_AGENT_KERNEL=v1` reports empty `kernel_trace_events`.

Do not write implementation first.

## Expected Verification

Focused tests first:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q
```

Full baseline checks unless scope narrows with evidence:

```bash
uv run pytest -q
uv run ruff check .
```

Kernel smoke, no LLM answer/judge:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

If both benchmark smokes are required for the gate, start them in parallel and collect both results. Only run 30-case full-chain LLM judge if Phase 7 changes answer/context behavior, and then run LongMemEval and LoCoMo in parallel.

## Anti-Demo ACK Criteria

Phase 7 can be ACKed as `usable` only if:

- plan, execute, and review artifacts cite this context bundle;
- real code path is wired into `MemoryOSService` and public benchmark output, not only direct unit tests;
- default kernel-off behavior is verified;
- opt-in kernel path is verified with v3 public benchmark smoke;
- denied, approval-pending, approval-resumed, and tool-executed control decisions are traceable;
- tool result visibility is tested or explicitly proven not applicable by current implementation scope;
- no LongMemEval-only success is promoted over LoCoMo failure;
- no kernel default change is made;
- v1 fallback remains preserved.
