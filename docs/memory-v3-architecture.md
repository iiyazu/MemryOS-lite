# MemoryOS v3 — Architecture Design

> Phase 0 baseline freeze. Supersedes the v2 evidence-planner A-H split.
> Target state: legacy-stable. No implementation changes in this phase.

## Current Baseline (2026-05-20)

| Check | Result |
|-------|--------|
| Full pytest | 311 passed, 1 warning |
| Hard eval | 1.00/1.00 |
| LongMemEval v2 smoke | episode_source_hit_at_10 = 8/10 |
| LoCoMo v2 smoke | episode_source_hit_at_10 = 5/10 |
| source_not_indexed (LME) | 0/10 |
| source_not_indexed (LoCoMo) | 0/10 |

## Target Architecture

```text
Message Log → Recall Memory → Archival Memory → Core Memory → Context Composer
                                                                      │
                                                              Agentic Kernel
```

### 1. Message Log
- Stores raw messages. Never summarizes or overwrites source history.
- Serves as audit ledger for all higher layers.
- Compatibility: existing `messages` table + `Message` schema remain.

### 2. Recall Memory
- Evolution of current `Episode` → `RecallMemoryEntry`.
- Searchable history slices with role/temporal/session/neighbor awareness.
- Raw evidence for answering. Exposes source_message_ids, rank features, planner decisions.
- Old `episodes` table kept as adapter during migration.

### 3. Archival Memory
Replaces Page/Item with three concepts:

| Component | Role |
|-----------|------|
| ArchivalDocument | Imported docs, long summaries, consolidation outputs |
| ArchivalPassage | Retrieval unit with passage text/embedding/score/citation |
| ArchivalMemory | Mem0-style add/search/update/delete lifecycle with history |

Old MemoryPage/MemoryItem may serve as migration input or legacy adapter only.

### 4. Core Memory
Letta-style always-in-context blocks:
- Block types: human, persona, project, preferences, task_state, constraints
- APIs: core_memory_append, core_memory_replace, core_memory_update
- Every update must write history. Non-source-backed content blocked.

### 5. Context Composer
Replaces ContextBuilder + RecallPipeline split:
- Layered assembly: task → core → recall → archival passages → recent → fallback
- Budget allocation by layer with explainable drops
- v3 diagnostics in ContextPackage.metadata

### 6. Agentic Kernel
Execution control plane:

| Component | Role |
|-----------|------|
| AgentStepRunner | Refresh messages, build request, execute step |
| ToolPolicyEngine | Resolve valid tools through rules |
| ApprovalGate | Durable approval state, blocking conflicting turns |
| ToolExecutionManager | Execute tool calls through source-backed executors |
| ContinuationController | Continue/stop/pause/compact/escalate decisions |

## Compatibility States

| State | Meaning |
|-------|---------|
| legacy-stable | Freeze old behavior; spec only |
| shadow-write | New schema writes, doesn't affect default context |
| shadow-read | New retrieval tested, doesn't affect default answers |
| opt-in-v3 | New composer/kernel behind flags |
| bench-candidate | v3 can run hard/LME/LoCoMo comparisons |
| default-candidate | v3 may become default if God approves |
| legacy-deprecated | Old paths enter cleanup |

Unless Review and God explicitly approve, no phase enables v3 by default.

## Superseded

The old evidence-planner A-H split (Phase A: QueryAnalyzer Flags through Phase H: Tests) is superseded. Its concepts are absorbed into Recall Memory and Context Composer.
