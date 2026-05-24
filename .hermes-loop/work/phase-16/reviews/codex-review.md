# phase: phase-16

Context bundle cited: `work/phase-16/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Findings

1. HIGH - Registered Phase 16 tools can still crash the real opt-in kernel instead of failing closed on malformed arguments. `SimpleAgentStepRunner.run_step()` calls the execution manager without exception containment at `src/memoryos_lite/agent_kernel.py:360`, then records `tool_executed` only after the call returns at `src/memoryos_lite/agent_kernel.py:367`. The new service code parses untrusted tool arguments directly: `core_promotion_request` does `int(request.arguments.get("limit_tokens") or 200)` and `float(request.arguments.get("confidence") or 1.0)` at `src/memoryos_lite/agent_kernel_tools.py:296` and `src/memoryos_lite/agent_kernel_tools.py:330`; `archive_write` passes unchecked `memory_type` into `ArchivalMemory` at `src/memoryos_lite/agent_kernel_tools.py:62`. The selection boundary accepts these registered tool candidates without type/schema validation at `src/memoryos_lite/agent_tool_selection.py:227` and `src/memoryos_lite/agent_tool_selection.py:260`. I reproduced this on the real `MemoryOSService` opt-in kernel path: initial `core_promotion_request` with `limit_tokens="not-int"` produced `approval_pending`, and the approved replay raised `ValueError: invalid literal for int() with base 10: 'not-int'` instead of a durable `tool_executed ok=false`, `tool_denied`, or closed error trace. A separate probe showed `archive_write` with `memory_type="not-a-type"` raises a Pydantic `ValidationError`. This violates the K2/K3 fail-closed tool surface expectation and is a Phase 17 LoCoMo repair-smoke risk because selector/planner-produced malformed arguments can abort benchmark execution after approval rather than remain auditable.

## Evidence Assessment

The implementation otherwise matches the structural shape required by the phase artifacts:

- `agent_tool_registry.py` registers only `archive_write`, `archive_attach`, and `core_promotion_request`; `recall_search`, `archive_search`, `core_memory_append`, `core_memory_replace`, destructive tools, and unknown tools remain outside the registry.
- `MemoryOSService` still constructs the kernel only when `settings.resolved_agent_kernel == "v1"` at `src/memoryos_lite/engine.py:1494`; v3 default and explicit v1 fallback were not changed.
- The service-backed path is real, not demo-only: `archive_write` and `archive_attach` route through `ArchiveMaintenanceService`, and `core_promotion_request` routes through `PromotionMaintenanceService` and `MemoryLifecycleService`.
- Source grounding is enforced by store/service write paths: archival memories, archive attachments, and promotion candidates require source refs; approved approval ids are converted into manual source refs when no explicit source refs are supplied.
- Replay binding is still strong for covered cases: pending approval lookup checks session id, tool name, requested action, tool call id, and request fingerprint before execution.
- Durable pending promotion candidate persistence is present through `promotion_candidates` and Alembic revision `0008_add_promotion_candidates`.
- The focused tests and result artifacts report `517 passed, 1 warning` and `ruff check .` clean; I did not rerun public evals in this review lane.
- The timed-out task-4 subagent is a documented concern, not an automatic failure: `result.md` and `task4_policy_public_result.md` record independent RED/GREEN verification for the policy/public guard.

The LoCoMo 5-case no-LLM structural smoke is sufficient for this structural K3 phase only: the phase did not change default retrieval, answer projection, scoring, or non-kernel public behavior, and the artifacts do not claim benchmark-quality improvement. A full-chain LLM judge gate is not applicable for Phase 16 under the active blueprint; it belongs to Phase 17/18 repair and governance evidence.

## Review Eval Routing Recommendation

Route this to repair, not milestone eval. Add a focused RED test that approved replays for every registered tool with malformed but selectable arguments return a closed/auditable tool error and never raise out of `run_step()`. After repair, rerun the focused kernel/store/context/public tests plus the default-off and opt-in structural smokes already listed in `plan_final.md`. Do not run a full-chain LongMemEval/LoCoMo judge for this Phase 16 repair unless default retrieval, answer projection, or scoring behavior changes.

Final verdict: FAIL
