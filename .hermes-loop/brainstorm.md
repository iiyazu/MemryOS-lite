# Brainstorm: Phase 2 - Recall Memory Layer

## 现状判断

代码库里已经有一条 `v2` recall 路径，但它还只是 episode-first 的原型：

- `src/memoryos_lite/retrieval/recall_pipeline.py` 负责 episode 检索、预算截断和少量 metadata。
- `src/memoryos_lite/retrieval/episode_searcher.py` 只有 BM25 + 简单 role boost。
- `src/memoryos_lite/evals.py` 和 `src/memoryos_lite/public_benchmarks.py` 仍在外层拼装 `episode_*` / `planned_evidence_*` 指标。
- `src/memoryos_lite/v3_contracts.py` 已经定义了 `RecallMemoryEntry`、`DiagnosticEvent`、`LayerBudgetDecision` 和旧表边界，说明 phase-2 应该是在这个语义上收敛，而不是再造一套新名词。

这意味着 phase-2 的核心不是“再加一个检索器”，而是把现有 episode 语义升级成真正的 Recall Memory Layer，并把排名、邻居、预算、drop、dedupe 这些诊断收进 recall 层本身。

## 方案 A: 继续在现有 episode pipeline 上加料

做法：

- 保持 `Episode` 和 `EpisodeSearcher` 作为主入口。
- 在 `RecallPipeline` 里逐步加入 temporal / session / neighbor 权重。
- 直接扩展 `metadata`，让评测层继续消费旧字段。

优点：

- 改动最小，最容易维持当前 smoke baseline。
- 不需要马上动 store 或迁移边界。

缺点：

- `Episode` 继续承担太多职责，语义会越来越像“RecallMemoryEntry 但还没改名”。
- 结构化诊断仍散落在 eval / benchmark 层，后面迁移会更痛。
- 邻居、去重、预算和 rank 的规则会被写成一堆局部补丁。

适用场景：只追求最短路径修补现有 v2 原型，不适合 phase-2 的目标描述。

## 方案 B: contract-first recall layer + 显式 adapter（推荐）

做法：

- 继续保留 `episodes` 表作为物理存储与回填来源。
- 把 `Episode` 明确视为 legacy 输入，检索语义改用 `RecallMemoryEntry`。
- 新增或细化回 recall 层内的组件职责：
  - `RecallMemorySearcher`
  - `RecallEvidencePlanner`
  - `RecallBudgeter`
  - `RecallDiagnostics`
- `Episode -> RecallMemoryEntry` 只通过 adapter 转换，后续的 direct hit / neighbor / drop / dedupe / rank 都在 recall 层内输出结构化诊断。
- `evals.py` / `public_benchmarks.py` 只做指标映射，不再决定 recall 语义。

优点：

- 和 `v3_contracts.py` 的边界一致，phase 切分清楚。
- 兼容 `v1` 默认路径，同时让 `v2` 真正成为 recall memory，而不是 episode wrapper。
- 后续 phase 3/4 要引入 core / archival 时，diagnostics 和 source attribution 不用重做。

缺点：

- 文件会更多，adapter 也会更多。
- 需要非常小心地保留旧 `episode_*` 指标映射，避免 benchmark 断层。

适用场景：当前 phase 的最佳匹配，也是最稳的长期路径。

## 方案 C: 新建独立 recall 表，episodes 只做兼容层

做法：

- 新建 `recall_memory_entries` 或等价表。
- ingest 时双写，回填时从 messages 构建 recall entries。
- `episodes` 逐步退化为兼容镜像或只读 legacy 输入。

优点：

- 语义最干净，未来删除 legacy 时成本低。
- 结构上最接近最终 v3 目标。

缺点：

- migration 和双写复杂度高。
- phase-2 的风险预算不划算，容易把注意力从 recall 质量转移到数据搬运。
- 对当前基线来说，收益不明显。

适用场景：更像 phase-4 或更后面的结构性重构，不适合现在动。

## 推荐结论

选方案 B。

原因很直接：当前代码已经有 recall 原型、bench 指标和 v3 contract 雏形，phase-2 最需要的是把“谁负责 recall 语义”说清楚。保持 `episodes` 作为回填和兼容输入，新增 `RecallMemoryEntry` 语义层，再把 neighbor / dedupe / budget / drop diagnostics 统一放进 recall 层，能同时满足：

1. `shadow-read` 的兼容要求。
2. `Episode -> RecallMemoryEntry` 的升级目标。
3. 旧 `episode_*` 指标的继续输出。
4. 后续 core / archival / composer / kernel 继续沿用同一套 provenance 结构。

## 关键风险

- 邻居扩展如果不和预算器联动，会把 recall hit 做高但上下文挤爆。
- 回填必须按 session 内确定性顺序，不要依赖时间戳排序的偶然性。
- diagnostics 必须结构化命名，不能再把原因编码塞进字符串里。
- `benchmark_case_id` 只能是辅助字段，recall search 不能依赖它。

