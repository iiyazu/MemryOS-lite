# Brainstorm: Phase 1 — Memory v3 Contracts

## 任务边界

Phase 1 是 `legacy-stable` 合同阶段：定义 Memory v3 的数据契约、接口、表边界和适配边界，不改默认运行路径。当前代码仍以 `messages`、`episodes`、`memory_pages`、`memory_items`、`memory_patches`、`trace_events` 为核心，`v1` 是默认召回路径，`v2` episode recall 是 opt-in。

Phase 1 必须解决的歧义：

- `Page/Item` 不能继续作为新 archival target，只能是 legacy migration input 或 adapter。
- Core memory 必须 source-backed，不能自动写入无来源事实。
- Kernel 的 `tool_policy` 和 `approval_state` 必须在实现前定义清楚。
- `source_refs`、`identity_scope`、`memory_history`、`diagnostics`、`kernel_trace` 必须统一，避免各层各写一套 metadata。

## 方案 A：兼容优先的最小覆盖

把 v3 合同定义为现有 schema 的别名和轻量扩展：

- `Message` 保持为 Message Log。
- `Episode` 直接映射为 `RecallMemoryEntry`。
- `MemoryPage` 暂时映射为 `ArchivalDocument`。
- `MemoryItem` 暂时映射为 `ArchivalPassage` / `ArchivalMemory`。
- `trace_events` 扩展为 kernel trace 的承载。

优点：

- 最快，几乎不改变现有 mental model。
- Phase 2/3 可以少写迁移适配代码。
- 风险低，较容易保持测试和 eval 绿。

缺点：

- 继续保留 Page/Item 的角色混杂，违背 blueprint 对新 archive target 的要求。
- Core memory 与 legacy core page 容易混淆。
- Kernel approval state 没有天然 durable owner，后续会补丁化。

适用场景：如果目标只是快速生成低风险 spec。当前 phase 的验收项要求更强，不推荐作为主方案。

## 方案 B：合同模块 + 显式 legacy adapter（推荐）

定义独立 v3 合同层，legacy 表只通过 adapter 进入 v3 语义：

- Keep tables: `sessions`、`messages`、`episodes`、`memory_pages`、`memory_items`、`memory_patches`、`trace_events` 保持可读，不改默认语义。
- New target tables: `recall_memory_entries` 或 `episodes` adapter view、`archival_documents`、`archival_passages`、`archival_memories`、`archival_memory_history`、`core_memory_blocks`、`core_memory_history`、`tool_policy_rules`、`approval_states`、`kernel_traces`。
- Required adapters:
  - `Episode` -> `RecallMemoryEntry`
  - `MemoryPage` -> `ArchivalDocument` migration input only
  - `MemoryItem` -> `ArchivalPassage` or `ArchivalMemory` based on type/source
  - `ContextBuilder` / `RecallPipeline` -> future `ContextComposer` contract
  - `agent_graph` demo -> future kernel package contract

合同中优先定义 Pydantic-style shapes 和 Protocol-style interfaces，再让后续 phase 决定具体实现文件。这样 Phase 1 可以精确说明接口，而不触碰默认路径。

优点：

- 明确 Page/Item 不再是新 archive target。
- 支持分 phase 实施：Recall、Core、Archival、Composer、Kernel 都能各自落地。
- `source_refs` 和 `identity_scope` 可成为跨层公共类型，避免 metadata 漂移。
- `approval_state` 和 `kernel_trace` 可先定义 durable model，避免后续 kernel 实现反复返工。

缺点：

- spec 和 plan 会更长。
- Phase 2/3 需要多写 adapter 测试。
- 需要非常清楚地声明哪些表是保留、哪些表是新增、哪些只是 adapter。

适用场景：当前 blueprint 的最佳匹配。它既保持 `legacy-stable`，又能给后续 phase 提供干净边界。

## 方案 C：新 v3 schema 一次性完整切分

直接把合同写成最终 v3 目标形态，并要求后续 phase 按新表推进：

- `message_log`
- `recall_memory_entries`
- `archival_documents`
- `archival_passages`
- `archival_memories`
- `core_memory_blocks`
- `context_composer_diagnostics`
- `tool_policy_rules`
- `approval_states`
- `kernel_traces`

旧表全部只作为 migration source，不再参与新合同命名。

优点：

- 语义最干净，最接近长期目标。
- 后续删除 legacy 时成本较低。
- 最容易表达 layered memory + agentic kernel 的完整架构。

缺点：

- 容易超出 `legacy-stable` 阶段的实际风险预算。
- `episodes` 当前已经支撑 v2 benchmark diagnostics，完全切离会让 Phase 2 需要大量兼容映射。
- spec 可能过度理想化，执行计划更难 bite-sized。

适用场景：适合作为远期目标参考，不适合作为 Phase 1 主方案。

## 推荐方案

采用方案 B：合同模块 + 显式 legacy adapter。

Phase 1 的 spec 应按以下结构起草：

1. 公共合同：`SourceRef`、`IdentityScope`、`MemoryHistoryEvent`、`DiagnosticEvent`、`LayerBudgetDecision`。
2. 五层 memory 接口：Message Log、Recall Memory、Archival Memory、Core Memory、Context Composer。
3. Kernel 接口：`AgentStepRunner`、`ToolPolicyEngine`、`ApprovalGate`、`ToolExecutionManager`、`ContinuationController`。
4. 表边界：明确 keep/add/adapter，不把 Page/Item 命名为新目标。
5. 兼容策略：默认 `v1` 不变，`v2` diagnostics 保留映射，v3 后续用 opt-in flag。

## 关键风险

- `MemoryItem` 同时像 passage 和 lifecycle memory，必须在 adapter 规则里按用途拆分。
- `trace_events` 现在是通用事件表；kernel trace 如果复用它，必须规定事件 payload schema，否则审计不可 replay。
- Core memory update API 必须要求 `source_refs` 或 explicit approval，否则会违反 source-backed 硬规则。
- `diagnostics` 必须分层命名，避免旧 `episode_*` 指标和新 recall/composer 指标混在一起。
