# Agentic Memory Roadmap

本文记录当前后续路线。历史阶段记录已从基线文档中移除，保留在
`docs/superpowers/` 的 spec/plan 中。

## 当前基线

MemoryOS Lite 当前定位是 eval 驱动、源归因的 Agent/RAG 记忆原型。

已稳定的边界：

- 默认 memory architecture 是 `v3` layered composer。
- `v1` legacy ContextBuilder 保留为显式回退：`MEMORYOS_MEMORY_ARCH=v1`。
- `v2` episode-first recall 通过 `MEMORYOS_RECALL_PIPELINE=v2` 显式启用。
- `MEMORYOS_AGENT_KERNEL=v1` 是实验性 kernel opt-in。
- SQLite 是当前权威存储。
- Episode 是 v2 的 raw-message retrieval 单元。
- Page 保留为压缩、审计和 fallback artifact。
- Item 是支持性语义诊断层，不是当前成功门槛。
- Core / Archival / Context Composer 已作为默认上下文路径启用。

最新验证：

| 项 | 结果 |
|---|---:|
| Full pytest | `352 passed, 1 warning` |
| Hard eval | `1.00/1.00` |
| LongMemEval v2 smoke | `episode_source_hit_at_10 = 8/10` |
| LoCoMo v2 smoke | `episode_source_hit_at_10 = 5/10` |
| v3 public smoke | `memory_arch` / `v3_layer_counts` / `v3_budget_decisions` / `v3_diagnostics` present |

## 当前决策：v3 默认启用

结论：默认切到 `v3`，保留 `v1` fallback 和 kernel opt-in。

原因：

- v3 composer 已能输出 legacy-compatible diagnostics 和 v3 layered diagnostics。
- `v1` 仍保留给 Page / Item / ContextBuilder 回归测试与兼容使用。
- kernel 默认化风险更高，继续由 `MEMORYOS_AGENT_KERNEL=v1` 显式启用。

完成标准：

- README / source / store / benchmark 文档反映 v3 默认、v1 fallback、kernel opt-in。
- benchmark 报告能同时保留 legacy 字段和 v3 diagnostics。
- 不把 MemoryOS Lite 描述成生产级系统。

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
