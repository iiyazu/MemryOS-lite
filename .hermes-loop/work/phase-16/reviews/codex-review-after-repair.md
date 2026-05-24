# phase: phase-16

Context bundle cited: `work/phase-16/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Findings

No blocking findings remain after the bounded repair for `phase16-malformed-registered-tool-fail-closed`.

The prior blocker is repaired in the real opt-in kernel path. `SimpleToolExecutionManager.execute()` now contains execution-boundary exception containment for the registered Phase 16 tools and returns `ToolExecutionResult(ok=False, error=...)` instead of raising out of `SimpleAgentStepRunner.run_step()` (`src/memoryos_lite/agent_kernel.py:91`). The runner records that closed result as `tool_executed` and skips verification/tool messages when `ok` is false (`src/memoryos_lite/agent_kernel.py:372`, `src/memoryos_lite/agent_kernel.py:390`). The focused regression covers approved replay through `MemoryOSService` for all registered tools, including invalid `archive_write.memory_type`, missing `archive_attach` target, and non-integer `core_promotion_request.limit_tokens`, and asserts no archival memory, archive attachment, promotion candidate, or tool message is written on the closed result (`tests/test_agent_kernel.py:1430`).

## Evidence Assessment

- Registered tool surface remains bounded to `archive_write`, `archive_attach`, and `core_promotion_request`; Level 2 search, Level 3 core edit, destructive, and unknown tools are not registered (`src/memoryos_lite/agent_tool_registry.py:18`, `tests/test_agent_kernel.py:216`, `tests/test_agent_kernel.py:750`).
- Approval replay binding remains intact: replay checks pending approval id, session id, tool name, requested action, `tool_call_id`, and request fingerprint before execution (`src/memoryos_lite/agent_kernel.py:456`). Covered tamper tests deny before execution/verification for `archive_attach` and `core_promotion_request` (`tests/test_agent_kernel.py:1195`, `tests/test_agent_kernel.py:1292`).
- Source grounding remains enforced by service/store boundaries. `source_refs_for_tool_request()` preserves explicit refs or creates a manual approval source ref when an approved mutating tool has no explicit refs (`src/memoryos_lite/agent_kernel_tools.py:23`). Store writes require source refs for archival memory, archive attachments, and promotion candidates (`src/memoryos_lite/store.py:1361`, `src/memoryos_lite/store.py:1394`, `src/memoryos_lite/store.py:1448`).
- `archive_attach` is service-backed and verifies real `ArchiveAttachment` plus v3 scope eligibility before tool message emission (`src/memoryos_lite/agent_kernel_tools.py:98`, `tests/test_agent_kernel.py:1120`).
- `core_promotion_request` is service-backed through `MemoryLifecycleService`, persists only a pending candidate, and does not mutate or render core memory (`src/memoryos_lite/agent_kernel_tools.py:276`, `tests/test_agent_kernel.py:1239`).
- v3 default, v1 fallback, and kernel default-off constraints are preserved. `MemoryOSService` instantiates `SimpleAgentStepRunner` only when `settings.resolved_agent_kernel == "v1"` (`src/memoryos_lite/engine.py:1494`).
- Public benchmark kernel execution remains opt-in. The default-off LoCoMo repair smoke report has 5 rows with kernel trace lengths `[0, 0, 0, 0, 0]`. The opt-in LoCoMo repair smoke report has 5 rows with trace lengths `[14, 14, 14, 14, 14]` and event order `kernel_step_started -> tool_candidates_generated -> tool_selected -> tool_policy_decision -> approval_pending -> kernel_step_completed -> kernel_step_started -> tool_candidates_generated -> tool_selected -> tool_policy_decision -> approval_granted -> tool_executed -> tool_verified -> kernel_step_completed`.
- I confirmed the opt-in smoke trace payloads do not contain `expected_answer`, `expected_source_ids`, `failure_class`, `case_id`, or judge labels as kernel trace payload keys. The public kernel probe writes the model-visible question only and uses approval provenance as the write source; benchmark gold remains in report sidecars/proposal diagnostics, not executable kernel inputs (`src/memoryos_lite/evals.py:741`, `src/memoryos_lite/public_benchmarks.py:692`, `src/memoryos_lite/public_maintenance_planner.py:55`).

## Verification Facts Confirmed From Artifacts/Diff

- `uv run pytest tests/test_agent_kernel.py::test_memoryos_service_registered_tool_malformed_replay_fails_closed -q` -> `3 passed`.
- `uv run pytest tests/test_agent_kernel.py -q` -> `48 passed`.
- `uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_service.py tests/test_archival_store.py tests/test_context_composer.py -q` -> `30 passed`.
- `uv run pytest tests/test_public_benchmarks.py -q` -> `61 passed`.
- `uv run pytest -q` -> `520 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.

These command results are reported in `work/phase-16/result.md` and `work/phase-16/execute_review.md`; I did not rerun tests in this review lane because the lane was read-only except for this artifact.

## Review Eval Routing

Smoke eval routing is sufficient under the Review Eval Autonomy Policy. Phase 16 and the repair changed the opt-in kernel/tool/store structural path only; default retrieval, answer projection, scoring, and non-kernel public benchmark behavior were not changed. The required gate is focused tests plus LoCoMo 5-case no-LLM default-off and opt-in structural smoke. A 30-case LongMemEval plus LoCoMo full-chain LLM judge would be milestone evidence and is not applicable for this Phase 16 repair.

Final verdict: PASS
