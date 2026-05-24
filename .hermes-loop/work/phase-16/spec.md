# phase: phase-16

# Phase 16 Spec: Kernel Maintenance Tool Surface

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `work/phase-16/context_bundle.md`.

God decision: approved for planning under autonomous skill compatibility. This spec narrows Phase 16 to the safest reversible slice from `brainstorm.md`: Level 1 maintenance tools only.

## Objective

Phase 16 will turn the current opt-in kernel's single `archive_write` bridge into a small Letta-style maintenance tool surface that is registry-backed, policy-gated, service-backed, replay-safe, verified, and visible to v3 only through existing scope/provenance rules.

The implementation must preserve:

- default memory architecture `v3`;
- explicit `MEMORYOS_MEMORY_ARCH=v1` fallback;
- opt-in `MEMORYOS_AGENT_KERNEL=v1`;
- default public benchmark reports with no kernel events;
- Phase 15 proposal-only public planner behavior and `gold_fields_used=false`.

## Chosen Scope

Open only these executable kernel maintenance tools:

- `archive_write`: existing behavior, moved behind a named archive maintenance service while preserving public/report behavior.
- `archive_attach`: attach an existing archive to the current session scope only, with source refs or approved approval provenance, idempotent duplicate handling, and v3 eligibility verification.
- `core_promotion_request`: create and persist a pending `PromotionCandidate` through `MemoryLifecycleService`; it must not apply the candidate, mutate core memory, or render a new core block in v3.

Keep these tools closed in Phase 16:

- `core_memory_append`;
- `core_memory_replace`;
- direct core memory update/delete tools;
- archive detach/delete/deprecate tools;
- `recall_search` and `archive_search`.

Read-only search remains a later slice because Phase 16's minimum usable contract is mutation safety and verification, not expanded retrieval behavior.

## Letta Comparison

Letta separates tool dispatch, tool execution, archive/passage managers, core memory managers, approval-bound tool calls, and context-window accounting. MemoryOS Lite should adopt the smaller equivalent contract:

- a registry declares supported kernel tools and their policy/verification requirements;
- the selection boundary exposes only registry-supported candidates;
- execution manager dispatches by tool name into domain services;
- archive attach and passage visibility are handled as a service concern, not inline runner logic;
- core promotion request produces a pending lifecycle object rather than applying core edits;
- approval replay stays bound to the exact `tool_call_id` and request fingerprint.

Letta is a reference only. No Letta runtime dependency will be added.

## Data Contracts

Add a registry entry type, for example in `src/memoryos_lite/agent_tool_registry.py`:

```python
@dataclass(frozen=True)
class KernelToolSpec:
    name: str
    level: int
    mutating: bool
    requires_policy_check: bool
    requires_source_refs_or_approval: bool
    requires_approval_by_default: bool
    verification_required: bool
    description: str
```

The registry for Phase 16 contains exactly `archive_write`, `archive_attach`, and `core_promotion_request`.

Add a durable promotion candidate store contract so `core_promotion_request` is not an in-memory-only demo:

- `MemoryStore.create_promotion_candidate(candidate: PromotionCandidate) -> PromotionCandidate`
- `MemoryStore.get_promotion_candidate(candidate_id: str) -> PromotionCandidate | None`
- `MemoryStore.list_promotion_candidates(status: str | None = None) -> list[PromotionCandidate]`

Add an Alembic migration for the new table because SQLite is the authoritative store.

## Tool Argument Rules

`archive_write`:

- requires non-empty `content`;
- accepts optional `archive_id`, defaulting to `session_id`;
- requires `source_refs` or approved approval provenance before writing;
- verifies archival history, passage creation, session attachment, and v3 eligibility.

`archive_attach`:

- requires non-empty `archive_id`;
- only allows `scope_type == "session"` in Phase 16;
- defaults `scope_id` to `request.session_id`;
- rejects any `scope_id` that differs from `request.session_id`;
- requires source refs or approved approval provenance;
- requires the archive to have at least one existing archival passage;
- creates one attachment or reuses an existing same archive/session attachment;
- verifies the attachment row and eligible passages under `ArchiveEligibilityScope(session_id=request.session_id)`.

`core_promotion_request`:

- requires non-empty `content`;
- requires source refs or approved approval provenance;
- creates a pending candidate with:
  - `source_layer="archival"` unless explicitly provided from an allowed set;
  - `target_layer="core"`;
  - `operation="promote"`;
  - `write_source="explicit_instruction"` unless explicitly provided from the existing enum;
  - `metadata.label`, defaulting to `"promotion"`;
  - `metadata.limit_tokens`, defaulting to `200`;
- persists the pending candidate;
- verifies candidate persistence, `status == "pending"`, zero core block mutation, and zero core history mutation.

## Runner And Trace Rules

`SimpleAgentStepRunner` remains the approval and replay coordinator. It should not contain tool-specific write logic.

Every successful mutating tool must emit:

- `tool_candidates_generated`;
- `tool_selected`;
- `tool_policy_decision`;
- `approval_pending` or direct allow decision;
- `approval_granted` on replay when approval is required;
- `tool_executed`;
- `tool_verified`;
- `kernel_step_completed`.

Replay tampering with `tool_call_id`, `tool_name`, `session_id`, arguments, source refs, or request fingerprint must stop before `tool_executed`.

Tool result messages must be compact `Role.TOOL` messages with metadata containing `tool_name`, `approval_id`, `tool_call_id`, `ok`, `result`, and `verification`. The message body must be generic, for example `tool archive_attach executed`, and must not include benchmark expected answers, expected source ids, judge labels, failure classes, or case ids.

## Public Benchmark Boundary

No Phase 16 implementation may make the kernel run by default. Public benchmark kernel traces remain empty unless `MEMORYOS_AGENT_KERNEL=v1`.

The existing opt-in public benchmark probe may continue to use only `archive_write`. Phase 16 ACK may use a 5-case opt-in structural smoke, but it must be reported as structural evidence only and must not claim benchmark-quality improvement.

## Acceptance Criteria

Phase 16 is usable only if:

- every opened tool is registry-backed, selectable, policy-gated, service-backed, verified, traced, and tested;
- `archive_attach` creates or reuses a real `ArchiveAttachment` and changes v3 archival visibility only for the requested session scope;
- `core_promotion_request` creates a durable pending candidate and does not mutate core memory;
- `core_memory_append`, `core_memory_replace`, destructive tools, and unknown tools fail closed before policy/execution;
- replay tampering denies before side effects;
- focused tests, full tests, ruff, and opt-in structural smoke are recorded in `result.md`;
- case-level smoke evidence is separated from benchmark-quality claims;
- v1 fallback, v3 default, and kernel opt-in remain unchanged.

## Rejected Alternatives

Registry-only tool declarations are rejected as demo-only.

Opening `recall_search` or `archive_search` is rejected for Phase 16 because it introduces answer-context and leakage risks without being required for the Level 1 maintenance contract.

Opening `core_memory_append` or `core_memory_replace` is rejected because direct core edits require a separate safety gate and would immediately affect v3 rendered context.

Direct store writes from `SimpleToolExecutionManager` for new tools are rejected because they bypass the named service boundary required by this phase.
