# Spec: Phase 1 — Memory v3 Contracts

## Goal

Define Memory v3 contracts without changing the default runtime path. This phase
creates the precise vocabulary, data shapes, persistence boundaries, adapter
rules, and kernel control-plane contracts needed by later phases.

Target compatibility state: `legacy-stable`.

No phase-1 work may switch recall, context building, memory mutation, CLI, API,
or benchmark behavior to v3 by default.

## Source Inputs

- `.hermes-loop/blueprint.md`: phase-1 task and acceptance criteria.
- `.hermes-loop/brainstorm.md`: recommends "contract module + explicit legacy adapter".
- `.hermes-loop/god_dispatch.json`: phase `phase-1`, target `legacy-stable`.
- Existing code baseline:
  - `src/memoryos_lite/schemas.py` contains legacy `Message`, `Episode`,
    `MemoryPage`, `MemoryItem`, `MemoryPatch`, `ContextPackage`, and `TraceEvent`.
  - `src/memoryos_lite/store.py` persists `sessions`, `messages`, `episodes`,
    `memory_pages`, `memory_items`, `memory_patches`, and `trace_events`.
  - `src/memoryos_lite/retrieval/recall_pipeline.py` is the current opt-in v2
    episode recall path.
  - `src/memoryos_lite/agent_graph.py` is the existing agent demo, not the v3
    kernel contract.

## Non-Goals

- Do not add database migrations in phase 1.
- Do not write to new v3 tables in phase 1.
- Do not change `MemoryOSService`, CLI, API, benchmark defaults, or `v1` recall.
- Do not treat `MemoryPage` or `MemoryItem` as final v3 archival targets.
- Do not add Letta or Mem0 as runtime dependencies.

## Contract Module

Phase 1 should introduce a standalone contract module:

```text
src/memoryos_lite/v3_contracts.py
tests/test_v3_contracts.py
```

This module is allowed to import legacy schemas for adapter helpers, but legacy
runtime modules should not import it until later phases opt in.

The module must expose Pydantic data contracts and `Protocol` interfaces only.
Concrete storage/search/composer/kernel implementations belong to later phases.

## Unified Common Formats

### `SourceRef`

`SourceRef` is the common provenance unit for recall, archival, core, diagnostics,
approval, and kernel trace data.

Required fields:

- `source_type`: one of `message`, `episode`, `document`, `passage`, `memory`,
  `core_block`, `tool_call`, `approval`, `manual`.
- `source_id`: stable identifier in the source system.
- `session_id`: optional session boundary.
- `identity_scope`: optional `IdentityScope`.
- `span`: optional `{start, end}` character range for document/message citations.
- `quote`: optional short source excerpt.
- `confidence`: float in `[0.0, 1.0]`, default `1.0`.
- `approval_id`: optional approval identifier for manual provenance.
- `metadata`: JSON object for source-specific details.

Validation:

- `source_id` must be non-empty.
- `span.start <= span.end` when `span` exists.
- `manual` source refs are valid only when `approval_id` is set.

### `IdentityScope`

`IdentityScope` scopes memories and policy decisions.

Fields:

- `user_id`
- `agent_id`
- `run_id`
- `session_id`
- `project_id`
- `archive_id`
- `tags`

All fields are optional, but at least one of `user_id`, `agent_id`, `run_id`,
`session_id`, `project_id`, or `archive_id` must be set for persisted v3 memory.

### `MemoryHistoryEvent`

Unified lifecycle event for recall, archival, and core memory.

Fields:

- `id`
- `memory_id`
- `memory_type`: `recall`, `archival_document`, `archival_passage`,
  `archival_memory`, `core_block`.
- `operation`: `add`, `update`, `replace`, `delete`, `promote`, `demote`,
  `attach`, `detach`.
- `source_refs`
- `actor`: `system`, `user`, `agent`, `tool`.
- `reason`
- `before`
- `after`
- `created_at`

Validation:

- `operation != "delete"` requires `after`.
- `replace` requires both `before` and `after`.
- All automatic core-memory writes require at least one `source_refs` entry.

### `DiagnosticEvent`

Layer-scoped diagnostics for explainable recall, archival retrieval, core usage,
context packing, and kernel decisions.

Fields:

- `layer`: `message_log`, `recall`, `archival`, `core`, `composer`, `kernel`.
- `event_type`
- `item_id`
- `reason_code`
- `score`
- `included`
- `dropped`
- `budget_tokens`
- `source_refs`
- `metadata`

Existing `episode_*` benchmark fields remain valid as recall diagnostics, not as
separate global concepts.

### `LayerBudgetDecision`

Budget diagnostics emitted by the future `ContextComposer`.

Fields:

- `layer`
- `requested_tokens`
- `allocated_tokens`
- `used_tokens`
- `dropped_item_ids`
- `reason_code`

## Five Memory Layer Contracts

### Message Log

Contract name: `MessageLogEntry`.

Responsibilities:

- Preserve raw messages as audit ledger.
- Reference existing `messages` rows.
- Never summarize, overwrite, or mutate source text.

Fields:

- `id`
- `session_id`
- `role`
- `content`
- `created_at`
- `token_count`
- `metadata`
- `source_refs`

Adapter:

- `Message` -> `MessageLogEntry`.

### Recall Memory

Contract name: `RecallMemoryEntry`.

Responsibilities:

- Formalize the current `Episode` as searchable raw-history recall.
- Preserve `source_message_ids`.
- Carry rank and benchmark metadata without making benchmark IDs required.

Fields:

- `id`
- `session_id`
- `message_id`
- `role`
- `text`
- `index_text`
- `position`
- `source_refs`
- `source_message_ids`
- `temporal_scope`
- `rank_features`
- `diagnostics`
- `created_at`

Adapter:

- `Episode` -> `RecallMemoryEntry`.
- The physical `episodes` table stays during phase 2 unless God later approves a
  new `recall_memory_entries` table.

### Archival Memory

Final v3 archival targets are:

- `ArchivalDocument`
- `ArchivalPassage`
- `ArchivalMemory`

`MemoryPage` and `MemoryItem` are not final v3 targets.

`ArchivalDocument`:

- Explicit imported docs, long summaries, sleep/consolidation outputs, project
  docs, decisions, and conversation compression.
- Carries document-level source refs, version, tags, and citation metadata.

`ArchivalPassage`:

- Retrieval unit derived from documents or archival memories.
- Carries `document_id`, passage text, passage-level citation span, rank score,
  archive/source/file filters, tags, scope, and source refs.

`ArchivalMemory`:

- Mem0-like durable facts, preferences, events, procedural rules, and entity
  links.
- Supports add/search/update/delete lifecycle and memory history.

Adapters:

- `MemoryPage` -> `ArchivalDocument` as migration input only.
- `MemoryItem` -> `ArchivalMemory` when it represents a fact/preference/event/rule.
- `MemoryItem` -> `ArchivalPassage` only when it is used as a retrieval chunk
  derived from a document/page.

### Core Memory

Contract names:

- `CoreMemoryBlock`
- `CoreMemoryUpdate`

Responsibilities:

- Represent bounded, always-in-context blocks such as `human`, `persona`,
  `project`, `preferences`, `task_state`, and `constraints`.
- Keep every update source-backed or explicitly approved.
- Emit history for append, replace, update, and delete.

Required invariant:

Automatic writes to core memory must include at least one `SourceRef`. A manual
or source-less write is valid only when linked to an approved `ApprovalState`.

Update APIs:

```text
core_memory_append(block, content, source_refs)
core_memory_replace(block, old, new, source_refs)
core_memory_update(block, patch, source_refs)
```

### Context Composer

Contract names:

- `ContextComposer`
- `ContextComposerRequest`
- `ContextPackageV3`
- `ContextLayerItem`

Responsibilities:

- Assemble task, core memory, high-confidence recall evidence, archival passages,
  recent messages, and fallback documents.
- Allocate token budget by layer.
- Emit diagnostics for inclusion, drop, dedupe, and budget decisions.
- Return a payload that can be adapted to the existing `ContextPackage`.

Suggested layer order:

```text
task
core memory
high-confidence recall evidence
archival passages
recent messages
fallback documents
```

## Agentic Kernel Contracts

The kernel is a control plane, not a memory layer.

### `ToolPolicyRule`

Fields:

- `id`
- `tool_name`
- `scope`
- `effect`: `allow`, `deny`, `require_approval`
- `reason`
- `priority`
- `source_refs`

### `ToolPolicyDecision`

Fields:

- `tool_name`
- `effect`
- `matched_rule_ids`
- `requires_approval`
- `reason`
- `diagnostics`

Default rule:

- Unknown tools must resolve to `require_approval` or `deny`, never implicit
  `allow`.

### `ApprovalState`

Fields:

- `id`
- `session_id`
- `tool_name`
- `requested_action`
- `status`: `pending`, `approved`, `rejected`, `expired`, `cancelled`
- `requested_by`
- `approved_by`
- `source_refs`
- `created_at`
- `resolved_at`
- `metadata`

Rules:

- `approved` requires `approved_by` and `resolved_at`.
- `rejected`, `expired`, and `cancelled` require `resolved_at`.
- Pending approvals block conflicting normal turns until resolved.

### `KernelTraceEvent`

Fields:

- `id`
- `step_id`
- `session_id`
- `sequence`
- `event_type`
- `payload`
- `source_refs`
- `approval_id`
- `created_at`

Trace events must be replayable in sequence. Legacy `trace_events` may mirror
kernel events, but `kernel_traces` is the future durable owner.

### Kernel Protocols

- `AgentStepRunner.run_step(request) -> AgentStepResult`
- `ToolPolicyEngine.decide(request) -> ToolPolicyDecision`
- `ApprovalGate.request_or_resume(request) -> ApprovalState`
- `ToolExecutionManager.execute(request) -> ToolExecutionResult`
- `ContinuationController.decide(result) -> ContinuationDecision`

## Persistence Boundary

### Tables Kept

Existing legacy tables remain readable and keep current semantics:

- `sessions`
- `messages`
- `episodes`
- `memory_pages`
- `memory_items`
- `memory_patches`
- `trace_events`
- `alembic_version`

### Tables Added Later

Phase 1 defines, but does not create, these future v3 tables:

- `archival_documents`
- `archival_passages`
- `archival_memories`
- `archival_memory_history`
- `core_memory_blocks`
- `core_memory_history`
- `tool_policy_rules`
- `approval_states`
- `kernel_traces`

`recall_memory_entries` is deferred. The phase-2 default physical owner remains
`episodes` plus an adapter unless God approves a split table.

### Required Adapters

- `Message` -> `MessageLogEntry`
- `Episode` -> `RecallMemoryEntry`
- `MemoryPage` -> `ArchivalDocument` migration input
- `MemoryItem` -> `ArchivalMemory`
- `MemoryItem` -> `ArchivalPassage`
- legacy `ContextPackage` -> `ContextPackageV3` compatibility payload
- `agent_graph` demo state -> future kernel request/result contracts

## Acceptance Criteria

- `spec.md` states kept tables, future v3 tables, and required adapters.
- `plan.md` decomposes implementation into bite-sized TDD tasks with exact files,
  commands, and expected outcomes.
- Core memory contract requires source refs or approved manual provenance.
- Kernel `tool_policy` and `approval_state` are specified before implementation.
- Page/Item ambiguity is removed: they are legacy migration inputs/adapters only,
  never new archival targets.
- Full implementation plan preserves `legacy-stable` by adding contracts without
  changing default runtime behavior.
