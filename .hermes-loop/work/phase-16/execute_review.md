# phase: phase-16

# Phase 16 Execute Self-Review

Context bundle: `work/phase-16/context_bundle.md`

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Real Chain Changed

- Store: durable `promotion_candidates` persistence plus Alembic revision `0008_add_promotion_candidates`.
- Kernel loop: explicit Level 1 tool registry, fail-closed selection, service-backed execution for `archive_write`, `archive_attach`, and `core_promotion_request`, approval replay safety, fail-closed malformed replay containment, verification routing, and generic tool result messages.
- Context composer: existing v3 eligibility path is exercised by archive attach tests; pending core promotion candidates remain out of core context.
- Public eval: default-off and opt-in structural trace guards were verified.

## Demo-Only Or Partial Surface

No opened Level 1 tool is demo-only.

Closed by design for Phase 16:

- `recall_search`
- `archive_search`
- `core_memory_append`
- `core_memory_replace`
- destructive archive/core tools
- unknown tools

## Tests That Proved Behavior

- `uv run pytest tests/test_agent_kernel.py::test_memoryos_service_registered_tool_malformed_replay_fails_closed -q` -> `3 passed`.
- `uv run pytest tests/test_agent_kernel.py -q` -> `48 passed`.
- `uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_service.py tests/test_archival_store.py tests/test_context_composer.py -q` -> `30 passed`.
- `uv run pytest tests/test_public_benchmarks.py -q` -> `61 passed`.
- `uv run pytest -q` -> `520 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.

Key behavioral tests:

- registry exposes only `archive_write`, `archive_attach`, `core_promotion_request`;
- unopened tools are denied before policy/execution;
- `archive_attach` requires current session scope, approval/source provenance, durable attachment, verification, and v3 visibility;
- `archive_attach` replay tamper denies before execution;
- `core_promotion_request` persists only pending candidates and does not mutate/render core memory;
- `core_promotion_request` replay tamper denies before execution or candidate persistence;
- malformed approved replays for all registered tools return auditable
  `ok=false` tool execution results instead of raising out of
  `MemoryOSService` opt-in kernel execution;
- opt-in `MemoryOSService` policy requires approval for every opened mutating Phase 16 tool;
- public kernel traces remain default-off unless `MEMORYOS_AGENT_KERNEL=v1`.

## Benchmark Cases

LoCoMo 5-case no-LLM structural smoke was run twice:

- Default-off report `.memoryos/evals/phase16_locomo5_kernel_default_off_repair_locomo.json`: `conv-26_qa_001` to `conv-26_qa_005`, all projected fail, `kernel_trace_events == []`.
- Opt-in kernel report `.memoryos/evals/phase16_locomo5_kernel_tools_structural_repair_locomo.json`: same five cases, all projected fail, 14 kernel trace events per row with `archive_write` approval/execution/verification.

Failure classes were unchanged across the two structural smokes:

- `conv-26_qa_001`, `conv-26_qa_002`: evidence-hit-answer-fail.
- `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`: retrieval-miss.

This phase does not claim pass-rate improvement. These runs validate structural default-off/opt-in behavior only.

## Constraints

- v1 fallback preserved: no change to `MEMORYOS_MEMORY_ARCH=v1`.
- v3 default preserved.
- Kernel default preserved: `MEMORYOS_AGENT_KERNEL` remains `off` unless explicitly set to `v1`.
- Gold leakage avoided: new tool paths use source refs, approvals, selected context/tool metadata, and store provenance; tests and public planner guards keep eval gold sidecars out of executable inputs.

## Concerns

- The task-4 codex subagent timed out at the tool boundary after applying the intended diff. God recovered by independently rerunning RED/GREEN policy evidence and recording `subagents/task4_policy_public_result.md`.
- An existing `.hermes-loop/god_launcher.sh` process is still recorded in `.hermes-loop/active_job.json`. This review does not consume that process as evidence and does not rely on its state.
- The first review found malformed registered tool replay could raise out of
  the real opt-in kernel path. The repair is bounded to
  `SimpleToolExecutionManager.execute()` exception containment and is covered by
  the focused three-case RED/GREEN test plus the fresh full suite.
