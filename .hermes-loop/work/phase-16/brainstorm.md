# phase: phase-16

# Brainstorm: Kernel Maintenance Tool Surface

Context bundle cited: `work/phase-16/context_bundle.md`.

Active goal cited:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Planning Frame

Phase 16 is a K3 structural phase, not a benchmark-promotion phase. The target is the smallest usable Letta-style maintenance tool surface that Phase 17 can consume for a LoCoMo repair smoke. The work must preserve `MEMORYOS_AGENT_KERNEL=v1` as opt-in, keep default public benchmark reports kernel-off, and prevent benchmark gold fields from becoming tool arguments, source refs, archive ids, passage links, promotion candidates, or memory writes.

The current code shape favors a conservative route:

- `ToolSelectionBoundary` is the mandatory entrance to execution, but it currently exposes only `archive_write`.
- `SimpleToolExecutionManager` supports only `archive_write`, and that implementation still performs store writes and session attachment logic directly in the executor.
- Store, lifecycle, and core services already enforce useful invariants: source refs for archival writes and attachments, approval/source provenance for core writes, read-only protection, scope-based archive eligibility, and v3 composer visibility through `ArchiveEligibilityScope`.
- Public eval only runs the kernel when `settings.resolved_agent_kernel == "v1"` and currently uses a hard-coded `archive_write` probe.
- Letta's relevant design lesson is not to import Letta, but to route tool names through a manager/factory into archive, passage, and block services, while binding approvals to exact tool calls and separating context accounting by component.

## Approach 1: Level 1 Only, Service-Backed Tool Registry

Open only `archive_write`, `archive_attach`, and `core_promotion_request`.

Implementation shape:

- Add an explicit tool registry with metadata for tool name, level, mutating/read-only flag, required args, provenance requirement, policy default, executor service, and verification requirement.
- Replace `ALLOWED_K2_TOOLS = {"archive_write"}` with registry-driven candidate generation for Level 1 tools only.
- Move current `archive_write` body behind a named archive maintenance service, preserving existing behavior but removing ad hoc executor ownership of archive write plus attach logic.
- Add `archive_attach` as a mutating tool routed through that archive maintenance service. It should create an `ArchiveAttachment` only with source refs or approved approval provenance, verify attachment existence, and verify v3 eligibility without broadening scope.
- Add `core_promotion_request` as a pending candidate creation only. It should call `MemoryLifecycleService.create_candidate()` and must not call `apply_candidate()`, mutate core memory, or make a core block visible in v3 during Phase 16.
- Keep `core_memory_append`, `core_memory_replace`, delete, detach, deprecate, and unknown tools fail-closed before policy/execution.
- Keep public eval's current kernel smoke narrow and opt-in; if it is broadened, make it structural only and ensure default-off reports still have `kernel_trace_events == []`.

Tradeoffs:

- Safest and most reversible because it changes only the opt-in kernel/tool/service path.
- Directly supports Phase 17's need for source-backed maintenance artifacts without opening answer/search behavior.
- Forces the needed service boundary first, before adding more tools.
- Does not yet let the kernel inspect memory with `recall_search` or `archive_search`; Phase 17 proposals must be supplied from existing model-visible diagnostics or explicit tool requests.

## Approach 2: Level 1 Plus Bounded Read-Only Search

Open Level 1 tools plus `recall_search` and `archive_search`.

Implementation shape:

- Use the same registry/service route as Approach 1.
- Add read-only search service methods that wrap `RecallMemorySearcher`/`RecallPipeline` and `ArchivalPassageSearcher`.
- Require bounded `query`, `top_k`, and scope args. Clamp top-k, reject empty queries, avoid eval sidecars, and return compact tool result messages.
- Mark read-only tools as no approval required but policy-gated and traced.
- Verify no memory tables, attachment tables, or core history rows change after read-only execution.

Tradeoffs:

- More Letta-like because the agent can inspect recall/archive state before choosing maintenance actions.
- Useful for future repair loops that need to find candidate passages before attaching or requesting promotion.
- Higher risk in Phase 16: search return messages can pollute answer context, gold-derived report fields can accidentally be wired into search args, and public benchmark behavior becomes easier to change unintentionally.
- Requires more tests and clearer result-message scoping to avoid turning structural smoke into a hidden retrieval change.

## Approach 3: Full K3 Surface Including Controlled Core Edits

Open Level 1, Level 2, and Level 3 tools: `core_memory_append` and `core_memory_replace`.

Implementation shape:

- Extend registry and policy to core edit tools.
- Route edits through `CoreMemoryService.append_block()` and `replace_block()`.
- Add stronger safety gates for block label allowlists, read-only handling, old-content uniqueness, token limits, approved approval state, source refs, and v3 visibility.

Tradeoffs:

- Closest to Letta's interactive core memory editing tools.
- Too large for the current Phase 16 evidence. The context bundle explicitly says Level 3 requires a separate safety gate, and existing `CoreMemoryService` is safe but kernel-level core edits would create direct user-visible context changes.
- Highest pass-to-fail risk because core memory is rendered early in v3 context and could influence every answer after a repair smoke.

## Recommendation

Use Approach 1 as the Phase 16 plan: Level 1 only, registry-backed, service-backed, approval-gated, and verification-first.

This is the safest reversible route because it turns the existing `archive_write` bridge into the intended K3 architecture while opening only two additional mutating semantics that do not directly edit core memory:

- `archive_attach` changes visibility only through existing `ArchiveAttachment` and `ArchiveEligibilityScope` rules.
- `core_promotion_request` creates pending lifecycle intent only and does not alter core blocks.

If time and review capacity remain after Level 1 is fully green, Approach 2 can be recorded as an optional follow-up slice, but it should not be required for Phase 16 ACK. Opening read-only search in the same phase is acceptable only if it remains demonstrably read-only, bounded, traced, and isolated from public eval gold sidecars.

Do not open Approach 3 in Phase 16.

## Concrete Planning Decisions

- Registry is authoritative for candidate generation. The selector may choose only registry-exposed candidates.
- Every opened tool must have a registry entry, policy rule, executor route, named service method, verification payload, trace evidence, and tests before it counts.
- Mutating tools require source refs or approved approval provenance.
- Approval replay must keep binding to `session_id`, `tool_name`, requested action, `tool_call_id`, and request fingerprint.
- `archive_write` should keep current externally visible behavior while moving the implementation behind an archive maintenance service.
- `archive_attach` should be idempotent for an existing same archive/scope attachment, but still verify and trace the already-present attachment rather than creating duplicates.
- `core_promotion_request` must return a pending `PromotionCandidate` id and verification that no core history/core block mutation occurred.
- Tool result messages must be compact, role=`tool`, and metadata-scoped by `tool_name`, `approval_id`, `tool_call_id`, `ok`, result, and verification. They must not become benchmark answer evidence by accident.
- Public reports may show opt-in kernel structural events only under `MEMORYOS_AGENT_KERNEL=v1`; default reports must remain unchanged.

## Rejected Alternatives

- Registry-only implementation: rejected as demo-only. A tool name in a registry without policy, service execution, verification, traces, and integration tests does not satisfy K3.
- Happy-path-only `archive_attach`: rejected because loose attachment scope can make unrelated passages visible to v3 and hide LoCoMo regressions.
- Direct executor/store writes for new tools: rejected because Phase 16 requires named service methods and because direct writes bypass lifecycle/core/archive invariants.
- Executable `core_memory_append` or `core_memory_replace`: rejected for Phase 16 because Level 3 requires a separate safety gate and core changes are immediately rendered by v3.
- Destructive detach/delete/deprecate tools: rejected by the blueprint and context bundle.
- Letta runtime dependency: rejected. Letta is a semantic reference only.
- Public planner auto-execution: rejected. Phase 15 proposals are proposal-only, and Phase 16 should not convert public benchmark sidecars into executable maintenance writes.

## Risks

- Broadening the selection boundary could let unsupported or malformed tools reach policy/execution.
- New tool arguments could weaken approval replay if the fingerprint omits archive id, scope id, candidate content, or source refs.
- `archive_attach` could over-broaden v3 visibility if it accepts an unsafe `scope_type`, wrong `scope_id`, or unverified archive id.
- `core_promotion_request` could accidentally apply a candidate or create visible core memory instead of remaining pending.
- Read-only search, if opened, could create side effects through tool result messages or leak eval-only expected source ids into query arguments.
- Verification may be too shallow if it checks only that a row exists, not that the row is eligible under the same session/scope that the tool call requested.
- Public benchmark smoke can become misleading if it emits kernel events by default or presents structural events as quality improvement.

## Demo-Only Boundary

The following would count as demo-only and must not satisfy Phase 16:

- Tool names appear in constants or docs but cannot execute through the real opt-in kernel.
- Candidate generation accepts new tools, but policy/approval/execution/verification tests are missing.
- Tools write memory by directly calling store methods from `SimpleToolExecutionManager` with no named service boundary.
- `core_promotion_request` returns a fake candidate id or creates an in-memory object without durable service/store evidence.
- `archive_attach` reports success without an `ArchiveAttachment` row and a v3 eligibility check.
- Search tools return canned results or use benchmark expected answer/source fields.
- Public benchmark output shows maintenance events without `MEMORYOS_AGENT_KERNEL=v1`.
- Phase result claims LongMemEval or LoCoMo quality improvement from Phase 16 structural smoke.

## Suggested RED Tests For The Plan

- `archive_attach` candidate generation accepts only valid archive/scope args and rejects unsupported/destructive tools before policy.
- `archive_attach` requires source refs or approval, routes through an archive maintenance service, creates or reuses one `ArchiveAttachment`, emits `tool_verified`, and makes only eligible passages visible through `V3ContextComposer`.
- `archive_attach` replay tampering with archive id, scope id, `tool_call_id`, requested action, or source refs denies before execution and emits no `tool_verified`.
- `core_promotion_request` requires source refs or approval, creates a pending `PromotionCandidate` through `MemoryLifecycleService`, emits verification, and does not change `core_memory_blocks`, `core_memory_history`, or v3 core items.
- `core_memory_append`, `core_memory_replace`, detach/delete/deprecate, and unknown tools remain fail-closed before policy/execution.
- Default public benchmark with v3 and kernel off has empty `kernel_trace_events`.
- Opt-in kernel structural smoke shows registry, selection, policy, approval, execution, verification, and completion events only for allowed tools, with no benchmark gold fields in tool arguments.
