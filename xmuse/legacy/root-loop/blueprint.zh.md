# MemoryOS Lite Memory v3 — God 中文蓝图

最后更新：2026-05-21

## 蓝图状态

本蓝图取代上一版 v2 记忆规划 / context packing 蓝图。

旧 evidence-planner 方向不废弃，但不再作为顶层目标独立推进；它被并入：

- `Recall Memory` 阶段：负责 raw history / episode recall / neighbor / source attribution。
- `Context Composer` 阶段：负责分层预算、证据编排、planner diagnostics。

God 必须以本蓝图为新的顶级计划。旧 v2 phase 文件不再属于当前 dispatch path；
`xmuse/phases/README.md` 记录该目录已废弃，除非后续从本蓝图重新生成。

## 一句话目标

不要从 0 重开项目；在当前 repo 内从 0 设计并实现新的 memory core。

目标是把 memoryOS 从当前薄链路：

```text
Message -> Episode -> Page/Item -> ContextPackage
```

重构为分层记忆系统：

```text
Message Log
  -> Recall Memory
  -> Archival Memory
  -> Core Memory
  -> Context Composer
```

旧实现保留为 baseline、adapter 和 regression reference；新内核以 opt-in 方式逐步接管。

## 当前判断

当前实现的主要问题不是“只有 SQLite”本身，而是 memory abstraction 错位：

- `Episode` 只是 v2 的临时 raw-message 检索单元，还不是正式 recall memory。
- `Page/Item` 同时承担 summary、archive、semantic item、fallback evidence 等职责，边界混乱。
- 缺少 Letta-style 的 archive / passage / attachment RAG 路线，导致 archival 层只是“存储”，还不是“可按范围检索的证据层”。
- 缺少 Letta-style always-in-context `core_memory`。
- 缺少 Mem0-style add/search/update/delete 生命周期和 memory history。
- 缺少 Letta-style 的 agentic kernel / step loop / approval gate，因此 tool 执行与 memory mutation 还不是一等控制平面事件。
- `ContextBuilder` / `RecallPipeline` 分叉较薄，没有统一的分层 context composer。

因此本轮不是在旧链路上小修小补，而是做 Memory v3 内核重构。

## 当前基线

当前项目仍以 SQLite 为权威状态源，文件系统只作为 debug mirror。

已知稳定边界：

- 默认 recall path 是 `v1`。
- `v2` episode-first recall 通过 `MEMORYOS_RECALL_PIPELINE=v2` 显式启用。
- SQLite 保存 sessions、messages、episodes、memory_pages、memory_items、patches、traces。
- Qdrant 目前只是 page embedding 的可选 ANN 索引，不是主状态层。
- Episode 保留 raw source attribution，是后续 Recall Memory 的迁移基础。
- Page/Item 保留为 legacy archival input，但不再作为新架构的清晰目标形态。

已知本地基线：

| 检查项 | 当前结果 |
|---|---:|
| Full pytest | `311 passed, 1 warning` |
| Hard eval | `1.00/1.00` |
| LongMemEval v2 smoke | `episode_source_hit_at_10 = 8/10` |
| LoCoMo v2 smoke | `episode_source_hit_at_10 = 5/10` |
| LongMemEval source_not_indexed | `0/10` |
| LoCoMo source_not_indexed | `0/10` |

## 设计锚点

### Letta 参考点

- Core memory 是显式、有限、按 block 命名，并渲染进 prompt context 的。
- Core memory 更新通过工具完成，必须可审计。
- Recall memory、archival memory、core memory 是不同层，不互相替代。
- Archival memory 可以来自显式文档，也可以来自 sleep-time / 后台 consolidation。
- RAG 是 passage-centric 的：archive 是范围，passage 是检索单元，attachment 负责把 archive 绑定到 agent / project / source。
- 检索可以按 `archive_id` / `source_id` / `file_id` / `date` / `tags` 过滤，并支持 text / vector / hybrid。
- Context build 只消费返回的 passages 和 citations，不把整份 archive 当成一个上下文块。
- Agentic control 不是单一 monolithic agent，而是 deterministic step loop。
- tool approval、pause、continuation 都是可持久化状态，不是一次性的 UI 提示。
- memory writes 必须经过 source-backed、tool-mediated execution。

### Mem0 参考点

- 记忆系统应有明确的 add/search/update/delete 生命周期。
- 写入时可以由 LLM 从消息中抽取值得记住的 memory。
- 检索必须支持 user_id / agent_id / run_id 等 scope filter。
- 长期 memory item 有 vector payload、metadata、history、entity links。
- Mem0 更像 memory engine，不是 Letta 那种 always-in-context block system。

### MemoryOS 采用方式

- 采用 Letta 的 archive / passage / attachment / context 组织方式作为 RAG 主路线。
- 采用 Letta 的分层结构和 core memory block 思路。
- 采用 Letta 的 agentic step loop 和 approval gating 作为执行控制平面。
- 采用 Mem0 的 lifecycle、history、identity scope、entity/memory linking 思路作为记忆层补强。
- 保留 memoryOS 自己的强约束：所有可长期使用的 memory 必须 source-backed。
- 不直接引入 Letta 或 Mem0 作为 runtime dependency。

## 目标架构

### 1. Message Log

职责：

- 保存原始消息。
- 作为所有上层记忆的审计账本。
- 不做智能总结，不做事实覆盖。
- 所有 memory promotion 都必须能追溯到 message 或外部 source。

兼容要求：

- 现有 `messages` 表和 `Message` schema 保持可读。
- benchmark loader、CLI、API 现有写入路径不能立即断。

### 2. Recall Memory

由当前 `Episode` 改造而来。

职责：

- 保存可搜索的历史对话片段。
- 支持 role / temporal / session / neighbor-aware recall。
- 作为回答时的 raw evidence 层。
- 提供 `source_message_ids`、rank features、planner decisions。

目标命名：

```text
Episode -> RecallMemoryEntry
EpisodeSearcher -> RecallMemorySearcher
RecallPipeline -> RecallMemoryPipeline 或 RecallPlanner
```

兼容要求：

- 第一阶段保留 `episodes` 表或提供兼容 view/adapter。
- 旧报告字段如 `episode_source_hit_at_10` 可以继续输出，但内部逐步映射到 recall metrics。

### 3. Archival Memory

不沿用旧 Page/Item 作为最终形态；新 Archival Store 从 0 设计。

Archival Memory 分三类：

```text
ArchivalDocument
ArchivalPassage
ArchivalMemory
```

`ArchivalDocument` 偏 Letta：

- 显式导入文档。
- 长摘要。
- sleep-time consolidation 生成的归档文档。
- 项目说明、长期资料、对话压缩、决策记录。
- 支持 chunk、version、citation、source range。

`ArchivalPassage` 偏 Letta：

- 文档或记忆条目切分后的检索单元。
- 负责承载 passage-level 的 text / embedding / score / citation。
- 携带 `archive_id`、`source_id`、`file_id`、`tags`、`scope`、`created_at` 等信息。
- 搜索返回 passage，而不是整份 document。

`ArchivalMemory` 偏 Mem0：

- 从 message 或 document 中抽取的事实、偏好、事件、程序性规则。
- 支持 add/search/update/delete。
- 支持 memory history。
- 支持 entity links。
- 支持 user_id / agent_id / run_id / session_id scope。

兼容要求：

- 旧 `MemoryPage` / `MemoryItem` 不作为新架构主模型。
- 旧 Page/Item 可作为 migration input 或 legacy adapter，并回填为 document / passage / memory。
- 旧 Page/Item 测试在迁移期可以继续通过，但不能阻止新 schema 建立。

### 4. Core Memory

新增 Letta-style always-in-context blocks。

职责：

- 保存短小、稳定、持续有效的信息。
- 每次 context build 默认注入，除非用户或配置关闭。
- 典型 block：
  - `human`
  - `persona`
  - `project`
  - `preferences`
  - `task_state`
  - `constraints`

更新工具语义：

```text
core_memory_append(block, content, source_refs)
core_memory_replace(block, old, new, source_refs)
core_memory_update(block, patch, source_refs)
```

兼容要求：

- 初期只能 opt-in 注入，避免直接打破 hard eval 和 public benchmark。
- 所有 core memory 更新必须写 history。
- 非 source-backed 内容不能自动进入 core memory。

### 5. Context Composer

替代当前 `ContextBuilder` / `RecallPipeline` 的分叉。

职责：

- 统一组织 Core / Recall / Archival Passages / Recent Messages。
- 进行分层预算分配。
- 解释每个 context item 进入或被丢弃的原因。
- 输出兼容 `ContextPackage` 的结构，同时新增 v3 diagnostics。

建议预算顺序：

```text
task
core memory
high-confidence recall evidence
archival passages
recent messages
fallback documents
```

兼容要求：

- v1 / v2 默认路径在迁移期不删除。
- v3 通过新 flag opt-in，例如 `MEMORYOS_MEMORY_ARCH=v3`。
- benchmark CLI 可以同时跑 legacy 与 v3 对照报告。

### 6. Agentic Kernel

这不是 memory layer，而是执行控制平面：把已组装的 context 转成可审计的 agent step。

职责：

- refresh / sanitize incoming messages。
- 通过 tool rules 和 approval state 解析当前可用工具。
- 用 composed context 构造 model request。
- 通过 source-backed executor 执行 tool calls。
- 持久化 assistant / tool / approval messages 和 trace events。
- 决定 continue / stop / pause / compact / escalate。

建议组件：

- `AgentStepRunner`
- `ToolPolicyEngine`
- `ApprovalGate`
- `ToolExecutionManager`
- `ContinuationController`

兼容要求：

- Kernel 初期只能 opt-in，例如 `MEMORYOS_AGENT_KERNEL=v1`。
- 现有 direct memory APIs 在迁移期仍可绕过 kernel 调用。
- 任何 core / archival mutation 都必须通过 source-backed validation 或 explicit approval。
- pending approval 未解决前，会阻止冲突的新 normal turn。

## 兼容状态模型

God 必须在每个 phase 的 dispatch 中声明目标兼容状态。

| 状态 | 含义 | 默认用户影响 |
|---|---|---|
| `legacy-stable` | 旧 v1/v2 行为不变，只冻结基线或写 spec | 无影响 |
| `shadow-write` | 新 schema 可写入，但不参与默认 context | 无默认影响 |
| `shadow-read` | 新 retrieval 可读可测，但不影响默认答案 | 无默认影响 |
| `opt-in-v3` | 通过 flag 使用 v3 composer / kernel path | 仅 opt-in 用户受影响 |
| `bench-candidate` | v3 可跑 hard/LME/LoCoMo 对照评测 | 不改变默认 |
| `default-candidate` | v3 达到默认候选标准 | 需要 God 明确批准 |
| `legacy-deprecated` | 旧路径进入删除/适配收尾 | 需要迁移报告 |

除非 Review 和 God 明确批准，任何 phase 都不得把 v3 设为默认。

## 全局成功标准

Memory v3 第一轮完成的标准：

- 当前 full pytest 仍通过，或所有失败都被标注为明确迁移项并由 God 接受。
- hard eval 不低于当前 `1.00/1.00`，除非 God 明确批准更换评测解释口径。
- legacy v1/v2 CLI/API 在兼容期仍可用。
- v3 至少能 opt-in 跑通：
  - create session
  - ingest messages
  - create recall entries
  - create/update core blocks
  - create/search archival documents, passages, and archival memories
  - build layered context package
  - execute one auditable kernel step with tool approval and continuation state
- 所有 core memory、archival documents、archival passages、archival memories 都有 source refs 或明确外部 document refs。
- 所有 kernel mutation 和 approval decision 都可持久化、可重放。
- Context Composer 输出可解释 diagnostics。
- Agentic Kernel 输出可解释的 step trace 和 tool policy decision。
- LME/LoCoMo 报告能区分：
  - recall source hit
  - archival passage hit
  - archival document hit
  - core memory use
  - context budget drop
  - answer quality

## Phase 顺序

God 必须一次只分发一个 phase。

### Phase 0 — Baseline Freeze + Architecture Decision

目标兼容状态：`legacy-stable`

任务：

- 冻结当前 legacy 行为和指标。
- 明确旧 evidence-planner A-H 被 Memory v3 蓝图取代。
- 记录哪些旧模块保留为 adapter/reference。
- 写出 migration glossary。

输出：

- `docs/superpowers/specs/<date>-memory-v3-architecture-design.md`
- legacy baseline commands 和结果。
- old-to-new 名词映射表。

验收：

- Review 确认没有直接实现改动。
- 当前 baseline 可复现或差异已记录。
- God 的下一 phase dispatch 不再引用旧 A-H evidence planner 作为顶级目标。

### Phase 1 — Memory v3 Contracts

目标兼容状态：`legacy-stable`

任务：

- 固化 v3 数据契约，不急于实现。
- 定义五层记忆接口：
  - Message Log
  - Recall Memory
  - Archival Memory
  - Core Memory
  - Context Composer
- 定义执行内核契约：
  - `AgentStepRunner`
  - `ToolPolicyEngine`
  - `ApprovalGate`
  - `ToolExecutionManager`
  - `ContinuationController`
- 定义 `source_refs`、`identity_scope`、`memory_history`、`diagnostics`、`tool_policy`、`approval_state`、`kernel_trace` 的统一格式。

输出：

- v3 schema spec。
- compatibility matrix。
- store migration policy。
- benchmark compatibility policy。

验收：

- spec 明确哪些旧表保留、哪些新表新增、哪些 adapter 负责兼容。
- Review 确认没有“Page/Item 继续混用为新 archive 主模型”的模糊表述。
- Review 确认 core memory 必须 source-backed。
- Review 确认 kernel tool policy 和 approval state 在实现前已明确。

### Phase 2 — Recall Memory Layer

目标兼容状态：`shadow-read`

任务：

- 将 `Episode` 概念升级为 `RecallMemoryEntry`。
- 保留 raw source attribution。
- 加入 role / temporal / session / neighbor-aware recall。
- 迁移旧 evidence planner 的结构化 ranking、neighbor、budget/drop diagnostics 到 recall 层。

兼容要求：

- 旧 `episodes` 表可以先保留。
- 旧 `episode_*` benchmark 字段继续输出，但映射到 recall diagnostics。
- v1 默认不受影响。

验收：

- recall entries 可从 messages backfill。
- recall search 不依赖 benchmark case id。
- recall diagnostics 可解释 direct hit、neighbor、drop、dedupe、rank。
- LME/LoCoMo recall source hit 不低于当前 smoke 基线。

### Phase 3 — Core Memory Blocks

目标兼容状态：`shadow-write`

任务：

- 新增 Letta-style core memory blocks。
- 新增 core memory history。
- 实现 append / replace / update 工具语义。
- 实现 block render format，但默认不注入 legacy context。

兼容要求：

- 初期只通过 opt-in API/CLI 或内部接口写入。
- 不允许自动从 LLM 输出无来源地写入 core memory。
- 每次更新必须包含 source refs 或明确 `manual` provenance。

验收：

- 可创建、读取、更新、删除 core block。
- update history 可追溯。
- block 有 limit、label、description、value、source_refs。
- source-backed enforcement 有测试。

### Phase 4 — Archival Memory Store

目标兼容状态：`shadow-write`

任务：

- 从 0 设计并实现新的 archival schema。
- 新增：
  - `ArchivalDocument`
  - `ArchivalChunk`
  - `ArchivalPassage`
  - `ArchivalMemory`
  - `ArchivalMemoryHistory`
  - `ArchiveAttachment`
  - 可选 `ArchivalEntityLink`
- 旧 Page/Item 只作为 migration input 或 legacy adapter。
- 建立 Letta-style archive attachment 关系，让 agent / project / source 能按范围检索 attached archives。
- 建立 passage 级 retrieval path，支持 `archive_id` / `source_id` / `file_id` / `tags` / `date` / text / vector / hybrid 查询。

兼容要求：

- 不要求旧 Page/Item 立即删除。
- 不把 Page/Item 名称继续作为新架构核心概念。
- 明确 document memory、passage memory 与 fact memory 的边界。

验收：

- 显式文档可进入 archive。
- message / sleep / retrieval consolidation 可生成 archival document、passage 或 archival memory。
- archival memory 支持 add/search/update/delete/history。
- archive search 返回 passage-level evidence，并带 source refs、scope、created/updated metadata、score、citation。

### Phase 5 — Memory Lifecycle + Promotion Policy

目标兼容状态：`shadow-read`

任务：

- 设计并实现 memory writer。
- 支持三种写入来源：
  - explicit user/system instruction
  - Mem0-style message extraction
  - Letta-style sleep/consolidation job
- 设计 promotion policy：
  - recall -> core
  - recall -> archival
  - archival -> core
  - document -> passage -> archival memory

兼容要求：

- 自动 promotion 初期只产生 candidates，不直接写 core。
- God/Review 可根据 benchmark 和人工审查结果调整 promotion 阈值。

验收：

- promotion candidate 有 reason、source_refs、confidence。
- core promotion 默认需要显式批准或高置信规则。
- archival write 支持 ADD / UPDATE / DELETE / NOOP 事件。
- memory history 完整记录生命周期。

### Phase 6 — Context Composer + Agentic Kernel

目标兼容状态：`opt-in-v3`

任务：

- 新增统一 context composer。
- 用 agentic step runner 包住 composer，步骤包括：
  - refresh / sanitize messages
  - 通过 tool rules 与 approval state 解析可用工具
  - 构造 model request
  - 执行 tool calls
  - 持久化 assistant / tool / approval messages
  - 决定 continue / stop / pause / compact
- 分层组装：
  - task
  - core memory
  - recall evidence
  - archival passages / archival documents
  - recent messages
  - fallback documents
- 替代旧 `ContextBuilder` / `RecallPipeline` 分叉，但保留 adapter。
- 以 Letta-style RAG 顺序组织 archive 访问：先取 attached archives，再按 passage 级结果进入 composer。

兼容要求：

- v3 composer 通过 feature flag 启用。
- kernel execution 通过 opt-in flag 启用，并可与 composer 独立切换。
- 输出仍兼容 `ContextPackage`，同时新增 v3 metadata。
- legacy v1/v2 build_context 仍能运行。

验收：

- v3 context package 能说明每个 item 的 layer、reason、score、tokens、source_refs。
- budget drop 可解释。
- core / recall / archival passage / archival document 命中分别统计。
- tool calls、approval pauses、resume points 都是持久化且可审计的。
- pending approval 会阻止冲突的新 normal turn。
- opt-in v3 hard eval 可跑通。

### Phase 7 — Benchmark + Evaluation Compatibility

目标兼容状态：`bench-candidate`

任务：

- 让 hard eval、LongMemEval、LoCoMo 能以 v3 模式运行。
- 报告 legacy 与 v3 对照。
- 将 answer quality 与 retrieval/memory diagnostics 分离。

兼容要求：

- legacy metrics 不删除。
- 新增 v3 metrics，但不覆盖旧字段含义。

验收：

- hard eval 不低于当前基线，或 God 明确记录接受差异。
- LME/LoCoMo 报告至少包含：
  - recall_source_hit
  - archival_source_hit
  - core_memory_used
  - context_budget_drop
  - answer_quality
- 报告还应包含 kernel approval / pause diagnostics（当 kernel 启用时）。
- 每次指标变化报告 fail-to-pass 和 pass-to-fail。

### Phase 8 — Legacy Adapter + Deprecation Decision

目标兼容状态：`default-candidate` 或保持 `opt-in-v3`

任务：

- 根据 Phase 7 结果决定是否推进 v3 默认候选。
- 收敛旧 Episode/Page/Item/ContextBuilder 的 adapter。
- 删除或标记过时文档。
- 更新 README、source guide、store interface、roadmap。

兼容要求：

- 不因代码洁癖提前删除 legacy。
- 只有在 Review PASS 且 God ACK 后才允许进入 `legacy-deprecated`。

验收：

- God 写出 default/defer/deprecate 决策。
- 若 v3 不达标，保持 opt-in 并回到相关 phase 调整。
- 文档只保留当前可读基线和迁移状态。

## God 动态调整规则

God 不只是推进 phase，还要根据状态动态改蓝图。

### 必须拆分 phase 的情况

- Review 连续 3 次 FAIL。
- 一个 phase 同时改 schema、retrieval、context 和 benchmark，导致无法定位失败。
- 测试失败无法判断是兼容问题还是新架构问题。

### 必须回滚或保持 shadow 的情况

- v1/v2 legacy 默认行为被意外改变。
- hard eval 从 `1.00/1.00` 回归且没有明确接受理由。
- v3 composer 或 kernel 导致 benchmark 报告字段语义混乱。
- 自动 promotion 写入了无 source-backed 的 core memory。
- pending approval 可被绕过，或重启后无法恢复。

### 必须调整蓝图的情况

- SQLite schema 已无法表达新 memory lifecycle，需要先抽 Store interface。
- Archival Memory 过度压缩导致 source attribution 丢失。
- Core Memory 注入导致回答过拟合或污染 evidence attribution。
- Recall Memory 命中率低于旧 Episode smoke 基线。
- Letta/Mem0 参考实现与 memoryOS source-backed 原则冲突。

### 可接受的调整动作

- 将当前 phase 拆成 schema / store / retrieval / context / benchmark 子 phase。
- 将某个自动写入能力降级为 candidate-only。
- 将 v3 default 推迟，继续保持 opt-in。
- 添加 migration adapter phase。
- 添加 rollback cleanup phase。
- 收紧 source-backed 或 identity-scope 要求。

每次 `GOD_ADJUST` 必须记录：

- 日期
- 触发 phase
- 触发证据
- 原目标
- 新目标
- 兼容状态变化
- 对后续 phases 的影响

## Anti-Overfitting 规则

- 不按 benchmark case id 分支。
- 不编码 expected answers。
- 不对 LongMemEval 或 LoCoMo 字符串做特判。
- 不用 retrieval-only smoke metrics 宣称 answer-quality improvement。
- retrieval、memory-layer、answer-quality metrics 必须分开。
- 保留失败样例作为 diagnostics，不隐藏失败。

## 完成定义

Memory v3 第一轮完成不是“所有旧代码删除”，而是：

- v3 架构层可 opt-in 跑通。
- message log / core / recall / archival / composer / kernel 职责清楚。
- legacy baseline 可对照。
- benchmark 报告能证明 v3 带来的收益或明确暴露失败位置。
- God 可以基于 Review 结果决定：
  - 继续迭代
  - 保持 opt-in
  - 推进 default-candidate
  - 回滚某阶段设计

最终报告必须包含：

- phase 完成列表
- 每阶段兼容状态
- schema/store/API 变化
- kernel/tool policy 状态
- legacy adapter 状态
- test commands and outputs
- hard eval result
- LongMemEval / LoCoMo 对照结果
- fail-to-pass / pass-to-fail
- God 对下一轮路线的决策
