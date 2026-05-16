# Agentic Memory Roadmap — Phase 2.5 → 3

## 项目定位

构建一个 eval 驱动的 agentic 记忆系统，结合 memU（子页面原子记忆 + source attribution）和 Letta（LLM 主动读写记忆）的设计，在 agent 面试中展示：

1. **数据驱动的工程决策** — 先诊断，再优化，每步有 benchmark 支撑
2. **结构化 agent 编排** — bounded Think-Act-Observe loop，可审计
3. **可演示的记忆生命周期** — memorize → recall → patch → 遗忘恢复

---

## 三阶段路线图

| Phase | 目标 | Exit Criteria |
|-------|------|---------------|
| 2.5 | LongMemEval 50-case retrieval 诊断基线 | 6 维 metrics baseline + 失败模式分类报告 |
| 2.6 | 数据驱动检索优化 | before/after 可解释提升 + anti-overfitting 验证 |
| 3 | Structured Think-Act-Observe + Demo | fake LLM demo 可跑 + trace 可审计 + benchmark 不退化 |

面试叙事线：**先测量 → 再优化 → 再产品化展示**。

---

## Phase 2.5: LongMemEval 诊断基线

### 目标

用 LongMemEval 50-case 子集建立当前系统的 retrieval 诊断基线，确认 page/item/evidence 链路的真实贡献。

### 6 维 Retrieval Metrics

| Metric | 含义 |
|--------|------|
| `source_hit` | ground truth source message 在 retrieved_evidence 中 |
| `page_source_overlap@k` | 检索到的 top-k pages 的 source_message_ids 包含 target |
| `item_source_overlap@k` | 检索到的 top-k items 的 source_message_ids 包含 target |
| `item_promoted_evidence_count` | item evidence 实际进入 retrieved_evidence 的数量 |
| `candidate_budget_dropped` | 因预算不足被丢弃的 evidence 候选数 |
| `source_not_indexed` | target source message 不在任何 page/item 的 source_message_ids 中 |

### 主线流程

1. 准备 50-case 子集，按 question type 均匀采样
2. 跑 ingest → page/item extraction → build_context
3. 记录 6 维 retrieval metrics
4. 分类失败模式（见 Phase 2.6 指标化命名）
5. 输出诊断报告

### Optional

6. 对同一 50 cases 跑 answer + LLM judge，作为 answer quality 参考。**不作为硬门槛。**

### 不做

- 不跑全量 500 cases
- 不做优化（纯测量）
- 不改核心 retrieval/paging/agent 逻辑
- 允许改诊断基础设施（eval harness、trace 输出）

### Exit Criteria

- 50 cases 的 6 维 retrieval metrics baseline 数据
- 失败 cases 按指标化类别分类完成
- 诊断报告：每类失败的占比 + 典型 case 示例

---

## Phase 2.6: 数据驱动检索优化

### 目标

根据 Phase 2.5 诊断报告，针对性优化检索链路，产出 before/after 可解释提升。

### 失败模式指标化命名

| 指标名 | 含义 | 可能的优化手段 |
|--------|------|--------------|
| `page_source_overlap@k=0` | 检索到的 pages 不包含 target source | page summary 质量、embedding 选择 |
| `item_source_overlap@k=0` | 检索到的 items 不包含 target source | item extraction 覆盖率、BM25 调优 |
| `item_hit_but_not_promoted` | item 命中但 evidence 未进入 package | evidence filtering 逻辑 |
| `promoted_but_budget_dropped` | evidence 候选因预算被丢弃 | evidence reserve 比例、priority |
| `source_not_indexed` | target 不在任何 page/item 的 source refs 中 | paging 窗口、item extraction |
| `evidence_filtered_out` | evidence 被 generic ack/low-value 过滤 | 过滤阈值调优 |

### source_hit miss 子原因拆解

source_hit miss 是最终现象，诊断时追溯具体子原因：

- budget dropped
- low-value / generic ack filtered
- source 在 recent_messages 被去重
- query overlap 不够（BM25 未命中）
- source_id attribution 错误（item 指向错误 message）

### 工作方式

1. 从诊断报告中取占比最高的失败类别
2. 提出假设 → 实现最小改动 → 跑 50 cases 验证
3. 记录 before/after diff（哪些 case fail→pass，哪些 pass→fail）
4. 重复直到边际收益递减

### Anti-Overfitting 约束

每次优化必须通过：

- hard eval 保持 1.00
- LongMemEval 50-case source_hit 不退化
- 至少抽查 3 个新增 pass case 的 source attribution 是否合理
- **禁止按 case_id 或 dataset-specific string 做特殊规则**

面试叙事："我们有明确的 anti-overfitting 规则，避免 benchmark hacking。"

### Exit Criteria

- before/after 对比表：每次优化的 delta + 影响的 case IDs
- 内置 eval 保持 1.00/1.00
- LongMemEval 子集 source_hit 有可量化提升
- 每个优化决策有一句话解释"为什么这样做"

### 不做

- 不引入 MemoryCategory / WorkflowStep
- 不加重依赖（reranker model、外部向量库）
- 不追求 100% — 边际收益递减时停止

---

## Phase 3: Structured Think-Act-Observe + Demo

### 目标

加入轻量 inner monologue loop（bounded structured memory loop），构建连贯 demo script，形成面试核心亮点。

### Graph 拓扑

```
router
  ├─ ingest → maybe_page → memory_think
  ├─ recall → memory_think
  └─ update → memory_think

memory_think → memory_action
memory_action:
  - memorize: tool.invoke(memorize_item)
  - recall: tool.invoke(recall_items)
  - patch: tool.invoke(recall_items) → tool.invoke(patch_item)
  - none: skip

memory_action → memory_observe → build_context → answer/END
```

memory_think_node 覆盖所有 intent（ingest/recall/update），不只是 ingest 后。

### MemoryDecision（结构化决策）

```python
class MemoryDecision(TypedDict):
    action: Literal["memorize", "recall", "patch", "none"]
    reason_code: Literal["durable_fact", "memory_question", "correction", "irrelevant"]
    query: str       # recall/patch 时有值
    content: str     # memorize/patch 时有值
    confidence: float  # 0.0-1.0, traced for auditability
```

**生成方式（三条路径）：**

| 路径 | 用途 | 实现 |
|------|------|------|
| Scripted decision provider | fake LLM demo / 测试 | 预定义 decision 序列 |
| Structured LLM output | 真实 LLM | JSON mode / structured output |
| Rule-based fallback | 无 API key 时 | intent→action 映射规则 |

面试叙事："demo 稳定因为有 scripted path，真实 LLM 参与时用 structured output 保证格式。"

### memory_think_node

**输入：**
- user message
- intent (ingest / recall / update)
- recent tool observations（上一轮 observe 结果，首轮为空）
- memory operation policy（config: enabled/disabled）

**输出：** MemoryDecision

**不依赖** context sufficiency signal（build_context 在 think 之后）。

### memory_action_node（受约束执行器）

直接调用 `tool.invoke()`，**不走 LLM 自由选择工具**：

| action | 执行 | tool turns |
|--------|------|-----------|
| memorize | `memorize_item.invoke({content, item_type})` | 1 |
| recall | `recall_items.invoke({query, top_k})` | 1 |
| patch | `recall_items.invoke({query})` → `patch_item.invoke({id, content})` | 2 |
| none | skip | 0 |

### Patch 两步语义

```
patch = recall old item by query → patch selected item with new content
```

- Step 1: `recall_items(query)` → 找到旧 item
- Step 2: `patch_item(item_id, new_content, source_message_ids=[latest_user_msg])`

**如果 recall 没找到 item：**
- `observation.success = false`
- 不执行 patch
- build_context 继续正常执行

`patch_item()` 扩展支持 `source_message_ids` 参数，默认绑定最新 user message，确保 citation 指向 correction message。

### MemoryObservation

```python
class MemoryObservation(TypedDict):
    action_taken: str
    created_item_id: str | None
    recalled_item_ids: list[str]
    patched_item_id: str | None
    success: bool
    error: str | None
    tool_outputs: list[str]
```

### Trace 两条路径

**Action path:**
```
memory_thought → memory_action → memory_observation → context_built → agent_answered
```

**No-op path:**
```
memory_thought → memory_observation(skipped) → context_built
```

测试不绑定固定 trace 顺序，按路径分别验证。

### Demo Script

**两个版本：**

| 版本 | 轮数 | 用途 | Config |
|------|------|------|--------|
| Full auto | 25-30 轮 | `memoryos demo agent` 自动重放 | 默认 |
| Interactive story | 6-8 轮 | 面试现场可讲解 | `rot_safe_budget=12, recent_message_limit=2` |

通过调小 config 实现快速遗忘，6-8 轮即可展示完整记忆生命周期。

**三幕结构：**

| 幕 | 触发 | Think decision | 展示能力 |
|----|------|---------------|----------|
| Act 1: 技术选型 | 用户告知技术栈 | `memorize, durable_fact` | 主动记忆 + recall + citation |
| Act 2: 偏好纠正 | 用户纠正旧信息 | `patch, correction` | recall→patch + citation 更新 |
| Act 3: 遗忘恢复 | 早期信息出 context | `recall, memory_question` | item retrieval 长期记忆恢复 |

### 约束

- 不引入新 storage schema
- 不引入 persistent scratchpad / working memory
- Think node 用同一个 LLM（不加额外模型）
- memory_action_node 确定性调用 tools，不走 LLM 自由选择
- Demo 默认路径不依赖真实 API

### Exit Criteria

- Demo agent 不调用真实 API 也能跑通 Think-Act-Observe trace（fake LLM 确定性重放）
- 真实 LLM demo 是增强路径，不是唯一路径
- Hard eval 保持 1.00
- LongMemEval 子集不退化
- Demo script 三幕均可跑通并产出正确 trace
- Trace 可审计：每个 memory decision 有 action + reason_code + confidence

---

## 面试叙事线

**一句话定位：**
> "一个 eval 驱动的 agentic 记忆系统，用结构化 Think-Act-Observe loop 替代无限 agent loop，每个设计决策都有 benchmark 数据支撑。"

**三个核心亮点：**

1. **数据驱动** — "我先跑了 LongMemEval 50 cases，发现 X% 的 source_hit miss 来自 Y 原因，所以做了 Z 优化，分数从 A 提到 B。"
2. **结构化 agent 编排** — "不是让 LLM 随机调工具，而是 bounded structured memory loop：think 输出结构化决策，action 确定性执行，observe 汇总结果。可审计、可复现。"
3. **Anti-overfitting 工程纪律** — "每次优化必须通过 hard eval + LongMemEval 不退化 + 抽查 attribution 合理性 + 禁止 case-specific 规则。"

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 编排 | LangGraph StateGraph |
| LLM | OpenAI-compatible (deepseek-v4-flash / gpt-4o-mini) |
| 存储 | SQLite + Qdrant (optional) |
| Embedding | text-embedding-3-small |
| 检索 | BM25 + embedding cosine + item-level RAG |
| 测试 | pytest, 确定性 eval (无 LLM), fake LLM |
| Trace | 结构化 TraceEvent, 全链路可审计 |

---

## 不做的事（明确边界）

- 不引入 MemoryCategory / WorkflowStep pipeline
- 不引入 persistent scratchpad / working memory
- 不加重依赖（reranker model、外部向量库作为必须）
- 不追求 LongMemEval 100% — 边际收益递减时停止
- 不做 free-form chain-of-thought reasoning
- 不做跨 session 记忆（Phase 3 scope 内）
