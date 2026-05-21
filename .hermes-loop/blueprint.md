# MemoryOS Lite Memory v3 — God Blueprint

Last updated: 2026-05-21

## Blueprint Status

This blueprint supersedes the previous v2 memory-planning blueprint.

The old evidence-planner direction is not discarded, but it is no longer the
top-level objective. It is now absorbed into:

- `Recall Memory` phase for raw-history recall, source attribution, and neighbors
- `Context Composer` phase for layered packing and diagnostics

God must treat this document as the new top-level plan. Old v2 phase files are
not part of the active dispatch path; `.hermes-loop/phases/README.md` records
that the phase directory is obsolete unless regenerated from this blueprint.

## One-Line Goal

Do not restart the whole project. Rebuild the memory core from scratch inside
the current repo.

The target architecture is:

```text
Message Log
  -> Recall Memory
  -> Archival Memory
  -> Core Memory
  -> Context Composer
```

The legacy implementation remains as baseline, adapter, and regression
reference. The new memory v3 core should take over gradually via opt-in
compatibility states.

## Current Judgment

The main issue is not “SQLite only” by itself. The real issue is that the
current memory abstraction is misplaced:

- `Episode` is only a temporary v2 raw-message retrieval unit, not a full recall layer.
- `Page/Item` currently mix summary, archive, semantic item, and fallback roles.
- The blueprint still lacks a Letta-style archive / passage / attachment RAG route, so the archival layer is storage rather than a scoped evidence layer.
- There is no Letta-style always-in-context `core_memory`.
- There is no Mem0-style add/search/update/delete lifecycle with explicit memory history.
- There is no Letta-style agentic kernel / step loop / approval gate, so tool execution and memory mutation are not yet first-class control-plane events.
- `ContextBuilder` / `RecallPipeline` are thin and do not form a real layered composer.

So this round is a memory-core redesign, not a small patch on the old chain.

## Current Baseline

SQLite remains the authoritative state store. Files are debug mirrors only.

Stable boundaries:

- Default recall path stays `v1`.
- `v2` episode-first recall is enabled only via `MEMORYOS_RECALL_PIPELINE=v2`.
- SQLite stores sessions, messages, episodes, memory_pages, memory_items,
  memory_patches, and trace_events.
- Qdrant is currently an optional ANN index for page embeddings only.
- Episode keeps raw source attribution and becomes the migration base for Recall Memory.
- Page/Item remain legacy archival inputs, not the clean target model.

Known local baseline:

| Check | Result |
|---|---:|
| Full pytest | `352 passed, 1 warning` |
| Hard eval | `1.00/1.00` |
| LongMemEval v2 smoke | `episode_source_hit_at_10 = 8/10` |
| LoCoMo v2 smoke | `episode_source_hit_at_10 = 5/10` |
| LongMemEval source_not_indexed | `0/10` |
| LoCoMo source_not_indexed | `0/10` |

## Design Anchors

### Letta anchors

- Core memory is explicit, bounded, block-named, and rendered into prompt context.
- Core memory updates are tool-mediated and auditable.
- Recall memory, archival memory, and core memory are separate layers.
- Archival memory can come from explicit docs or sleep-time consolidation.
- RAG is passage-centric: archive is the scope, passage is the retrieval unit, and attachment binds an archive to an agent / project / source.
- Retrieval can filter by `archive_id` / `source_id` / `file_id` / `date` / `tags` and support text / vector / hybrid search.
- Context build should consume passages and citations, not treat a whole archive as one context block.
- Agentic control lives in a deterministic step loop, not a single monolithic agent class.
- Tool approval, pause, and continuation are durable state, not transient UI events.
- Memory writes must pass through source-backed, tool-mediated execution.

### Mem0 anchors

- Memory systems need clear add/search/update/delete lifecycle semantics.
- LLMs may extract what is worth remembering from messages.
- Search is scoped by user_id / agent_id / run_id.
- Long-term items can carry metadata, history, and entity links.
- Mem0 is a memory engine, not an always-in-context block system.

### MemoryOS adoption

- Adopt Letta’s archive / passage / attachment / context organization as the main RAG route.
- Adopt Letta’s layered structure and core-memory block model.
- Adopt Letta’s agentic step loop and approval gating as the execution control plane.
- Adopt Mem0’s lifecycle, history, identity scope, and linking ideas as memory-layer reinforcement.
- Keep MemoryOS source-backed as a hard rule.
- Do not add Letta or Mem0 as runtime dependencies.

## Target Architecture

### 1. Message Log

Responsibilities:

- Store raw messages.
- Serve as the audit ledger for all higher memory layers.
- Never summarize or overwrite source history.

Compatibility:

- Existing `messages` table and `Message` schema remain readable.
- CLI/API/benchmark write paths must not break immediately.

### 2. Recall Memory

This is the evolution of the current `Episode`.

Responsibilities:

- Store searchable history slices.
- Support role / temporal / session / neighbor-aware recall.
- Serve as raw evidence for answering.
- Expose `source_message_ids`, rank features, and planner decisions.

Target naming:

```text
Episode -> RecallMemoryEntry
EpisodeSearcher -> RecallMemorySearcher
RecallPipeline -> RecallMemoryPipeline / RecallPlanner
```

Compatibility:

- Keep the `episodes` table or provide an adapter/view during migration.
- Existing `episode_*` benchmark fields may stay, but they become recall diagnostics.
- v1 default behavior stays unchanged.

### 3. Archival Memory

Do not keep Page/Item as the final model. Design a new archival store from scratch.

Archival memory is split into:

```text
ArchivalDocument
ArchivalPassage
ArchivalMemory
```

`ArchivalDocument` is Letta-like:

- Explicit imported docs
- Long summaries
- Sleep/consolidation outputs
- Project docs, long-lived references, conversation compression, decisions
- Chunking, versioning, citation ranges

`ArchivalPassage` is Letta-like:

- Retrieval unit derived from documents or archival memory items
- Carries passage-level text / embedding / score / citation
- Includes `archive_id`, `source_id`, `file_id`, `tags`, `scope`, and `created_at`
- Search returns passages, not whole documents

`ArchivalMemory` is Mem0-like:

- Facts, preferences, events, procedural rules
- add/search/update/delete lifecycle
- memory history
- entity links
- user_id / agent_id / run_id / session_id scope

Compatibility:

- Old `MemoryPage` / `MemoryItem` do not remain the new primary model.
- They may remain as migration input or legacy adapter and backfill documents / passages / memories.

### 4. Core Memory

Add Letta-style always-in-context blocks.

Responsibilities:

- Store short, stable, always-useful facts.
- Inject by default into every context build unless disabled.
- Example blocks:
  - `human`
  - `persona`
  - `project`
  - `preferences`
  - `task_state`
  - `constraints`

Update APIs:

```text
core_memory_append(block, content, source_refs)
core_memory_replace(block, old, new, source_refs)
core_memory_update(block, patch, source_refs)
```

Compatibility:

- Initially opt-in only.
- Every update must write history.
- Non-source-backed content must not enter core memory automatically.

### 5. Context Composer

Replace the current thin `ContextBuilder` / `RecallPipeline` split with a
single layered composer.

Responsibilities:

- Assemble Core / Recall / Archival Passages / Recent Messages.
- Allocate budget by layer.
- Explain why each item was included or dropped.
- Produce a `ContextPackage` compatible payload plus v3 diagnostics.

Suggested order:

```text
task
core memory
high-confidence recall evidence
archival passages
recent messages
fallback documents
```

Compatibility:

- `v1` and `v2` remain available during migration.
- `v3` is opt-in, e.g. `MEMORYOS_MEMORY_ARCH=v3`.
- Benchmark CLI can compare legacy and v3 runs.

### 6. Agentic Kernel

This is not a memory layer. It is the execution control plane that turns a
composed context into an auditable agent step.

Responsibilities:

- Refresh and sanitize incoming messages.
- Resolve valid tools through tool rules and approval state.
- Build the model request from the composed context.
- Execute tool calls through source-backed executors.
- Persist assistant / tool / approval messages and trace events.
- Decide continue / stop / pause / compact / escalate.

Suggested components:

- `AgentStepRunner`
- `ToolPolicyEngine`
- `ApprovalGate`
- `ToolExecutionManager`
- `ContinuationController`

Compatibility:

- Kernel starts opt-in only, e.g. `MEMORYOS_AGENT_KERNEL=v1`.
- Existing direct memory APIs remain callable outside the kernel.
- Any core / archival mutation must pass source-backed validation or explicit approval.
- Pending approval blocks conflicting normal turns until resolved.

## Compatibility States

| State | Meaning | Default user impact |
|---|---|---|
| `legacy-stable` | Freeze old behavior; spec only | none |
| `shadow-write` | New schema may write, but does not affect default context | none |
| `shadow-read` | New retrieval may read and be tested, but does not affect default answers | none |
| `opt-in-v3` | New composer / kernel path available behind flags | opt-in only |
| `bench-candidate` | v3 can run hard/LME/LoCoMo comparisons | none |
| `default-candidate` | v3 may become default only if God approves | pending approval |
| `legacy-deprecated` | Old paths enter cleanup/deprecation | migration required |

Unless Review and God explicitly approve, no phase may switch v3 on by default.

## Global Success Criteria

The first memory-v3 round is complete when:

- Full pytest remains green, or any failures are clearly documented migration items accepted by God.
- Hard eval stays at least `1.00/1.00`, unless God explicitly changes the evaluation interpretation.
- Legacy v1/v2 CLI/API keep working during migration.
- v3 can opt in and run:
  - create session
  - ingest messages
  - create recall entries
  - create/update core blocks
  - create/search archival documents, passages, and archival memories
  - build a layered context package
  - execute one auditable kernel step with tool approval and continuation state
- All core memory, archival documents, archival passages, and archival memories are source-backed or explicitly document-backed.
- All kernel mutations and approvals are persisted and replayable.
- Context Composer emits explainable diagnostics.
- Agentic Kernel emits explainable step traces and tool policy decisions.
- LME/LoCoMo reports can separate recall hit, archival passage hit, archival document hit, core usage, budget drop, and answer quality.

## Phase Order

God must dispatch one phase at a time.

### Phase 0 — Baseline Freeze + Architecture Decision

Target state: `legacy-stable`

Tasks:

- Freeze the legacy baseline.
- Record that the old evidence-planner A-H split is superseded.
- Define what stays as adapter/reference.
- Write the migration glossary.

Outputs:

- Memory-v3 architecture design doc
- baseline commands and results
- old-to-new term map

Acceptance:

- No direct implementation change yet.
- Baseline remains reproducible or divergences are recorded.
- Future dispatches no longer treat the old A-H evidence-planner split as the top-level goal.

### Phase 1 — Memory v3 Contracts

Target state: `legacy-stable`

Tasks:

- Define the v3 data contracts.
- Specify interfaces for the five memory layers:
  - Message Log
  - Recall Memory
  - Archival Memory
  - Core Memory
  - Context Composer
- Specify the execution-kernel contracts:
  - `AgentStepRunner`
  - `ToolPolicyEngine`
  - `ApprovalGate`
  - `ToolExecutionManager`
  - `ContinuationController`
- Define unified formats for `source_refs`, `identity_scope`, `memory_history`, `diagnostics`, `tool_policy`, `approval_state`, and `kernel_trace`.

Acceptance:

- The spec clearly states what tables are kept, what tables are added, and what adapters are required.
- Core memory must be source-backed.
- Kernel tool policy and approval state must be specified before implementation.
- No ambiguity remains about Page/Item as the new archive target.

### Phase 2 — Recall Memory Layer

Target state: `shadow-read`

Tasks:

- Evolve `Episode` into `RecallMemoryEntry`.
- Preserve raw source attribution.
- Add role / temporal / session / neighbor-aware recall.
- Move the old evidence-planner structured ranking, neighbor, budget, and drop diagnostics into the recall layer.

Compatibility:

- Keep the old `episodes` table for now.
- Old `episode_*` benchmark fields continue to work as mapped diagnostics.
- v1 default remains unchanged.

Acceptance:

- Recall entries can be backfilled from messages.
- Recall search does not rely on benchmark case IDs.
- Recall diagnostics can explain direct hit, neighbor, drop, dedupe, and rank.
- LME/LoCoMo recall hit stays at or above the current smoke baseline.

### Phase 3 — Core Memory Blocks

Target state: `shadow-write`

Tasks:

- Add Letta-style core memory blocks.
- Add core memory history.
- Implement append / replace / update semantics.
- Implement render format without making it the default legacy context.

Compatibility:

- Start with opt-in APIs or internal interfaces only.
- No automatic source-less writes into core memory.
- Every update requires source refs or explicit manual provenance.

Acceptance:

- Blocks can be created, read, updated, and deleted.
- Update history is traceable.
- Blocks have limit, label, description, value, and source refs.
- Source-backed enforcement is tested.

### Phase 4 — Archival Memory Store

Target state: `shadow-write`

Tasks:

- Design the archival schema from scratch.
- Add:
  - `ArchivalDocument`
  - `ArchivalChunk`
  - `ArchivalPassage`
  - `ArchivalMemory`
  - `ArchivalMemoryHistory`
  - `ArchiveAttachment`
  - optional `ArchivalEntityLink`
- Keep old Page/Item as migration input or adapter only.
- Add Letta-style archive attachment so agents / projects / sources can retrieve scoped attached archives.
- Add a passage-level retrieval path that supports `archive_id` / `source_id` / `file_id` / `tags` / `date` / text / vector / hybrid queries.

Acceptance:

- Explicit docs can enter archive.
- Message / sleep / retrieval consolidation jobs can produce archival documents, passages, or archival memories.
- Archival memory supports add/search/update/delete/history.
- Archive search returns passage-level evidence with source refs, scope, created/updated metadata, score, and citation.

### Phase 5 — Memory Lifecycle + Promotion Policy

Target state: `shadow-read`

Tasks:

- Implement memory writers.
- Support three write sources:
  - explicit user/system instruction
  - Mem0-style message extraction
  - Letta-style sleep/consolidation job
- Define promotion policy:
  - recall -> core
  - recall -> archival
  - archival -> core
  - document -> passage -> archival memory

Acceptance:

- Promotion candidates carry reason, source refs, and confidence.
- Automatic promotion only produces candidates at first.
- Core promotion requires explicit approval or high-confidence policy.
- Add/update/delete events are tracked in memory history.

### Phase 6 — Context Composer + Agentic Kernel

Target state: `opt-in-v3`

Tasks:

- Build the layered composer.
- Wrap it in an agentic step runner that:
  - refreshes and sanitizes messages
  - resolves valid tools with tool rules and approval state
  - builds the model request
  - executes tool calls
  - persists assistant / tool / approval messages
  - decides continue / stop / pause / compact
- Compose:
  - task
  - core memory
  - recall evidence
  - archival passages / archival documents
  - recent messages
  - fallback docs
- Replace the current thin split while keeping adapters.
- Use a Letta-style archive access order: fetch attached archives first, then pass passage-level results into the composer.

Compatibility:

- v3 composer is enabled through feature flags.
- Kernel execution is opt-in and can be toggled independently during migration.
- Output is still compatible with `ContextPackage`, plus v3 metadata.
- Legacy v1/v2 build_context still runs.

Acceptance:

- The v3 context package explains layer, reason, score, tokens, and source refs.
- Budget drops are explainable.
- Core / recall / archival passage / archival document hits are counted separately.
- Tool calls, approval pauses, and resume points are durable and auditable.
- Pending approval blocks conflicting normal turns.
- Opt-in v3 hard eval can run.

### Phase 7 — Benchmark + Evaluation Compatibility

Target state: `bench-candidate`

Tasks:

- Make hard eval, LongMemEval, and LoCoMo runnable in v3 mode.
- Report legacy and v3 side by side.
- Separate answer quality from retrieval/memory diagnostics.

Acceptance:

- Legacy metrics remain available.
- New v3 metrics do not change old field meanings.
- Reports include recall hit, archival passage hit, archival document hit, core usage, budget drop, and answer quality.
- Reports include kernel approval / pause diagnostics when the kernel is enabled.

### Phase 8 — Legacy Adapter + Deprecation Decision

Target state: `default-candidate` or remain `opt-in-v3`

Tasks:

- Decide whether v3 is ready to become default.
- Shrink adapters around the old Episode/Page/Item/ContextBuilder paths.
- Remove or mark obsolete docs.
- Update README, source guide, store interface, and roadmap.

Acceptance:

- God issues a default/defer/deprecate decision.
- If v3 is not ready, keep it opt-in and return to the relevant phase.
- Documentation keeps only the readable current baseline and migration state.

## God Adjustment Rules

God must adjust the blueprint based on outcomes.

### Must split a phase when

- Review fails 3 times in a row.
- One phase changes schema, retrieval, context, and benchmark all at once.
- A failure cannot be localized cleanly.

### Must keep shadow/rollback when

- v1/v2 legacy default behavior changes unexpectedly.
- hard eval regresses from `1.00/1.00` without an accepted reason.
- v3 composer or kernel makes benchmark diagnostics ambiguous.
- automatic promotion writes source-less core memory.
- pending approval can be bypassed or is not resumable after restart.

### Must update the blueprint when

- SQLite schema is no longer expressive enough for the new lifecycle.
- Archival memory compresses away source attribution.
- Core memory injection causes overfitting or evidence pollution.
- Recall hit falls below the legacy episode smoke baseline.
- Letta/Mem0 behavior conflicts with MemoryOS source-backed rules.

### Allowed adjustment actions

- Split phases into schema / store / retrieval / context / benchmark slices.
- Downgrade automatic write features to candidate-only.
- Keep v3 opt-in longer.
- Add migration adapter phases.
- Add rollback cleanup phases.
- Tighten source-backed or identity-scope requirements.

Every `GOD_ADJUST` must record:

- date
- triggering phase
- triggering evidence
- previous target
- new target
- compatibility-state change
- effect on later phases

## Anti-Overfitting Rules

- Do not branch on benchmark case IDs.
- Do not encode expected answers.
- Do not special-case LongMemEval or LoCoMo strings.
- Do not claim answer-quality improvement from retrieval-only smoke metrics.
- Keep retrieval, memory-layer, and answer-quality metrics separate.
- Preserve failing examples as diagnostics.

## Completion Definition

Memory v3 is not finished when legacy code is deleted. It is finished when:

- v3 can run opt-in end to end.
- message log / core / recall / archival / composer / kernel responsibilities are clear.
- legacy baseline remains comparable.
- benchmark reports show where v3 helps or fails.
- God can decide whether to continue, keep opt-in, or move to default-candidate.

Final report must include:

- phase completion list
- compatibility state per phase
- schema/store/API changes
- kernel/tool policy status
- legacy adapter status
- test commands and outputs
- hard eval result
- LongMemEval / LoCoMo comparison
- fail-to-pass / pass-to-fail
- God’s next-route decision
