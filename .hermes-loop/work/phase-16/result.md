# phase: phase-16

# Phase 16 Result

Context bundle: `work/phase-16/context_bundle.md`

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Summary

Phase 16 implemented the bounded K3 Level 1 maintenance tool surface for the opt-in v3 kernel:

- explicit registry for executable kernel tools: `archive_write`, `archive_attach`, `core_promotion_request`;
- fail-closed selection boundary for unopened tools, including search, core edit, destructive, and unknown tool names;
- named archive maintenance service for `archive_write` and `archive_attach`;
- named promotion maintenance service for durable pending `core_promotion_request`;
- SQLite-backed `promotion_candidates` table and Alembic revision `0008_add_promotion_candidates`;
- real `MemoryOSService` opt-in kernel approval policy for all opened mutating tools;
- generic tool result message bodies with ids and verification payloads in metadata only;
- fail-closed execution containment for registered tools whose approved replay
  contains malformed but selectable arguments.

Default `v3`, explicit `MEMORYOS_MEMORY_ARCH=v1`, and default-off `MEMORYOS_AGENT_KERNEL` were preserved. Phase 16 does not claim LongMemEval or LoCoMo quality improvement.

## Real Chain Components

- Ingest: not applicable.
- Store: changed; added durable pending promotion candidates and migration head `0008_add_promotion_candidates`.
- Retrieval: verified fail-closed for unopened `recall_search` and `archive_search`; no retrieval behavior changed.
- Context composer: verified archive attachments become visible through existing v3 archival eligibility and pending core promotion candidates do not render as core memory.
- Answer projection: not applicable.
- Kernel loop: changed; registry, selection, approval policy, execution, verification, replay safety, and generic tool messages now cover the opened Level 1 tools.
- Public eval: verified default-off public reports and opt-in structural kernel traces.

## RED Evidence

- Registry/selection RED from `subagents/task1_registry_result.md`: missing `agent_tool_registry`, `archive_attach`/`core_promotion_request` candidate support, and fail-closed unopened tool behavior.
- Archive attach RED from `subagents/task2_archive_attach_result.md`: missing `archive_attach` execution/verification and v3 visibility through session attachment.
- Core promotion RED from `subagents/task3_core_promotion_result.md`: missing durable candidate APIs and missing `core_promotion_request` verification.
- Policy integration RED from `subagents/task4_policy_public_result.md`: service-level opt-in kernel policy only required approval for `archive_write`; new guard failed before registry-driven policy was restored.
- Store migration RED: full pytest exposed stale tests asserting old Alembic head `0007_add_core_block_read_only_tags` after the durable candidate migration moved head to `0008_add_promotion_candidates`.
- Review repair RED: `test_memoryos_service_registered_tool_malformed_replay_fails_closed`
  proved approved replays for registered tools could raise out of the real
  opt-in kernel path when `core_promotion_request.limit_tokens` was non-integer
  or `archive_write.memory_type` was invalid.

## Verification Commands

```bash
uv run pytest tests/test_agent_kernel.py::test_memoryos_service_registered_tool_malformed_replay_fails_closed -q
```

Result: `3 passed`.

```bash
uv run pytest tests/test_memory_lifecycle.py::test_lifecycle_create_candidate_persists_pending_candidate tests/test_agent_kernel.py::test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation tests/test_agent_kernel.py::test_kernel_core_promotion_request_replay_tamper_denies_before_execution_or_candidate tests/test_agent_kernel.py::test_memoryos_service_opt_in_kernel_requires_approval_for_all_phase16_mutating_tools -q
```

Result: `4 passed`.

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Result: `48 passed`.

```bash
uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_service.py tests/test_archival_store.py tests/test_context_composer.py -q
```

Result: `30 passed`.

```bash
uv run pytest tests/test_public_benchmarks.py -q
```

Result: `61 passed`.

```bash
uv run pytest tests/test_core_memory_store.py::test_init_db_stamps_current_migration_head tests/test_core_memory_store.py::test_init_db_upgrades_existing_core_memory_schema_before_stamping_head -q
```

Result: `2 passed`.

```bash
uv run pytest -q
```

Result: `520 passed, 1 warning`.

```bash
uv run ruff check .
```

Result: `All checks passed!`.

## Structural Public Smoke

Default-off guard:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --no-llm-answer --no-llm-judge --run-id phase16_locomo5_kernel_default_off_repair
```

Report: `.memoryos/evals/phase16_locomo5_kernel_default_off_repair_locomo.json`.

Rows: 5. Verdicts: `5 fail / 0 pass` projected no-LLM structural smoke. Kernel trace lengths: `[0, 0, 0, 0, 0]`. `kernel_trace_present`: all `false`.

Opt-in kernel structural smoke:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --no-llm-answer --no-llm-judge --run-id phase16_locomo5_kernel_tools_structural_repair
```

Report: `.memoryos/evals/phase16_locomo5_kernel_tools_structural_repair_locomo.json`.

Rows: 5. Verdicts: `5 fail / 0 pass` projected no-LLM structural smoke. Kernel trace lengths: `[14, 14, 14, 14, 14]`. `kernel_trace_present`: all `true`. Event shape per row:

```text
kernel_step_started -> tool_candidates_generated -> tool_selected -> tool_policy_decision -> approval_pending -> kernel_step_completed -> kernel_step_started -> tool_candidates_generated -> tool_selected -> tool_policy_decision -> approval_granted -> tool_executed -> tool_verified -> kernel_step_completed
```

Tool names in structural smoke: `archive_write` only. This smoke intentionally does not prove benchmark quality for `archive_attach` or `core_promotion_request`; those are proven by focused kernel/store/context tests.

Case ids for both LoCoMo smokes:

- `conv-26_qa_001`: evidence-hit-answer-fail.
- `conv-26_qa_002`: evidence-hit-answer-fail.
- `conv-26_qa_003`: retrieval-miss.
- `conv-26_qa_004`: retrieval-miss.
- `conv-26_qa_005`: retrieval-miss.

No pass-to-fail or fail-to-pass claim is made for Phase 16 because these are 5-case projected structural smokes and the phase does not change answer/retrieval quality targets.

## Demo-Only Check

No opened tool remains registry-only:

- `archive_write` is selected, policy-gated, approval-bound, service-backed, verified, traced, persisted, and public-smoked.
- `archive_attach` is selected, policy-gated, approval-bound, service-backed, verified against `ArchiveAttachment` and v3 eligibility, replay-safe, and covered by focused tests.
- `core_promotion_request` is selected, policy-gated, approval-bound, service-backed through `MemoryLifecycleService`, durably persisted as pending, verified as non-core-mutating, replay-safe, and covered by focused tests.
- malformed approved replays for all registered tools are contained at the
  execution boundary and return `ToolExecutionResult(ok=False, error=...)`
  instead of raising out of the real opt-in kernel path.

Remaining closed tools: `core_memory_append`, `core_memory_replace`, `recall_search`, `archive_search`, destructive archive/core tools, and unknown tools.

## Notes

The two post-repair public smoke runs completed as short limit-5 no-LLM
structural checks; no long-running eval heartbeat was required. Benchmark
scores were diagnostic evidence only and were not used as optimization targets.
