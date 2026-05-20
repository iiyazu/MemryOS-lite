# Agentic Memory Roadmap

本文记录当前后续路线。历史阶段记录已从基线文档中移除，保留在
`docs/superpowers/` 的 spec/plan 中。

## 当前基线

MemoryOS Lite 当前定位是 eval 驱动、源归因的 Agent/RAG 记忆原型。

已稳定的边界：

- 默认 recall path 是 `v1`。
- `v2` episode-first recall 通过 `MEMORYOS_RECALL_PIPELINE=v2` 显式启用。
- SQLite 是当前权威存储。
- Episode 是 v2 的 raw-message retrieval 单元。
- Page 保留为压缩、审计和 fallback artifact。
- Item 是支持性语义诊断层，不是当前成功门槛。

最新验证：

| 项 | 结果 |
|---|---:|
| Full pytest | `311 passed, 1 warning` |
| Hard eval | `1.00/1.00` |
| LongMemEval v2 smoke | `episode_source_hit_at_10 = 8/10` |
| LoCoMo v2 smoke | `episode_source_hit_at_10 = 5/10` |

## 下一阶段：Phase 1.5 Baseline Hardening

目标：把当前分支整理成可维护基线。

任务：

- 清理过时过程文档。
- 保留少量当前可读的基线文档。
- 明确 v1/v2 边界。
- 保证 clean tree 下测试和文档不依赖未跟踪文件。

完成标准：

- README 和 CLAUDE.md 只描述当前实现和 SQLite-first、v2 opt-in 状态。
- store/source/benchmark 文档反映 Episode 和 v2 opt-in。
- 过时阶段报告不再作为当前文档入口。

## Phase 2：Evidence Planner / Context Packing

目标：把已经检索到的 episode 证据更稳定地组织成可回答上下文。

优先级：

1. 改进 `RecallPipeline` 的 evidence ordering。
2. 增加 temporal / multi-session neighbor policy。
3. 让 `ContextPackage.metadata` 能解释每个证据为什么进入或被丢弃。
4. 在 LongMemEval/LoCoMo 固定 slice 上比较 planned evidence 指标。

验收指标：

- hard eval 保持 `1.00/1.00`。
- v2 smoke 不低于当前 episode/planned evidence 命中。
- `budget_dropped_relevant` 保持可解释。

## Phase 3：Answer Quality

目标：减少“找到了证据但答案没用好”的情况。

方向：

- 用更明确的 answer prompt 呈现 raw evidence。
- 强制 answer citation 指向 `source_message_ids`。
- 对 no-evidence 情况输出可解释 refusal。
- 将 answer diagnostics 与 retrieval diagnostics 分开报告。

## Phase 4：Semantic Memory Layer

目标：在 episode recall 稳定后，再增强 item/core memory。

方向：

- 改进 `MemoryItem` 抽取和搜索。
- 增加 stable facts / core profile 的可控更新机制。
- 借鉴 Letta memory blocks 和 Mem0 memory types，但保持本项目的源归因优先。

## Anti-Overfitting Rules

- 不按 case id 或数据集专有字符串写规则。
- 每次 benchmark 提升都要报告 fail->pass 和 pass->fail。
- 检索指标与答案指标分开看。
- 所有默认行为变更必须证明不会破坏 v1。
