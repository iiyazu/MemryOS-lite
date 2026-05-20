# Plan: Phase 0 — Baseline Freeze + Architecture Decision

## Task 1: Create architecture design doc
**File:** 创建 `docs/memory-v3-architecture.md`

### Step 1: Write overview section
描述 v3 目标和当前基线。从 blueprint.md 和 CLAUDE.md 提取。

### Step 2: Five-layer architecture
写 Message Log → Recall Memory → Archival Memory → Core Memory → Context Composer 的职责和接口描述。

### Step 3: Agentic Kernel
描述 AgentStepRunner, ToolPolicyEngine, ApprovalGate, ToolExecutionManager, ContinuationController。

### Step 4: Compatibility table
从 blueprint.md 复制兼容状态表。

## Task 2: Create migration glossary
**File:** 创建 `docs/memory-v3-glossary.md`

### Step 1: Old → New term map
| Old | New | Notes |
|---|---|---|
| Message | Message | unchanged |
| Episode | RecallMemoryEntry | temporary v2 unit → formal recall |
| MemoryPage | ArchivalDocument | summary/import role |
| MemoryItem | ArchivalPassage / ArchivalMemory | split by source type |
| ContextBuilder | ContextComposer | thin → layered |
| RecallPipeline | ContextComposer (v3 path) | absorbed into composer |
| agent_graph | AgenticKernel | demo → control plane |

## Task 3: Freeze baseline
### Step 1: Run pytest
`uv run pytest -q` → 记录 passed/failed 数

### Step 2: Run hard eval
`uv run memoryos eval run --case-set hard --baseline memoryos_lite` → 记录分数

### Step 3: Record in architecture doc
在 architecture.md 中记录基线快照。

## 验收
- [ ] docs/memory-v3-architecture.md exists
- [ ] docs/memory-v3-glossary.md exists
- [ ] baseline results recorded
- [ ] No .py files modified
- [ ] Old evidence-planner A-H declared superseded
