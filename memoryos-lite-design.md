# MemoryOS Lite 项目构思

## 1. 项目定位

项目名称建议：

**MemoryOS Lite: 面向长运行 Agent 的上下文窗口记忆管理中间件**

一句话描述：

在长会话 Agent 中，将 LLM context window 视为易腐化的工作内存，在 context rot 前主动限制窗口容量，并把溢出的会话状态分页、压缩、索引到外部记忆层，再由 Paging Agent 负责非标准化的记忆整理与换页。

核心目标不是“让 Agent 记住更多”，而是：

> 让 Agent 在更小、更干净、更高信号密度的上下文中持续工作。

## 2. 需求背景

虽然主流 LLM 的 context window 在持续增大，但长上下文不等于稳定能力。随着上下文增长，模型可能出现注意力分散、关键信息丢失、无关信息干扰和 context rot 等问题。

因此，本项目的核心痛点是：

- 不把 session 撑到模型最大 context window。
- 在 context rot 前设置更保守的工作窗口。
- 将工作窗口之外的信息分页到外部记忆层。
- 在需要时通过 page fault / recall 机制召回相关记忆。
- 通过 benchmark 验证分页和上下文管理是否有效。

## 3. 设计灵感

### Letta / MemGPT 思路

借鉴 Letta 的 OS 式记忆分层：

- context window 类似 RAM。
- core memory 是高优先级常驻内存。
- recall / archival memory 是外部存储。
- Agent 可以通过工具读写和管理记忆。

### memU 思路

借鉴 memU 的 agentic memory / file-based memory 思想：

- 记忆不是简单 key-value 或向量库。
- 记忆整理本身可以由专门的 Memory Agent 完成。
- 记忆可以组织成类似文件系统的结构，便于读、写、diff、审计和演化。

### 本项目融合点

```text
OS-like memory hierarchy
+ Paging Agent
+ patch-based memory update
+ context budget management
+ provenance / source trace
+ memory benchmark
```

## 4. 核心抽象

```text
LLM Context Window  = RAM / working memory
Conversation Log    = write-ahead log
Memory Pages        = paged storage
Memory Index        = page table / vector index / metadata index
Paging Agent        = 后台分页与整理进程
Context Governor    = 控制当前 session 不超过 rot threshold
Context Builder     = 构造受预算约束的 context package
```

与普通 RAG 的区别：

```text
普通 RAG:
用户提问 -> 检索相关文档 -> 拼进 prompt

MemoryOS Lite:
Agent 会话持续增长 -> 主动判断何时分页 -> 决定分页什么
-> 将历史状态整理成 memory pages -> 当前任务需要时再换页召回
```

## 5. 核心模块

### 5.1 Context Rot Guard

系统不等待模型达到最大 context window，而是设置更保守的安全工作窗口。

示例配置：

```text
model_max_context = 128k
rot_safe_budget = 24k / 32k / 48k
hard_limit = 64k
```

当 session token 接近 `rot_safe_budget` 时触发分页。

注意：

- `rot_safe_budget` 不是绝对科学值。
- 它是一个可配置策略。
- 后续可以通过 benchmark 和 eval 结果调优。

### 5.2 Paging Agent

Paging Agent 负责将溢出的上下文整理成 memory page。

输入：

```text
recent conversation
tool results
agent decisions
user preferences
task state
source message ids
```

输出示例：

```json
{
  "page_type": "task_summary",
  "title": "Agent 项目选型讨论",
  "facts": [
    "用户目标是在约 20 天内完成一个可上简历的 Agent infra 项目"
  ],
  "decisions": [
    "不选择客服 Agent、Runbook Oncall Agent 或 Raffle Agent 作为主线"
  ],
  "open_questions": [
    "如何证明自定义 memory benchmark 有效"
  ],
  "discarded_noise": [
    "与当前 MemoryOS 项目无关的早期业务 Agent 细节"
  ],
  "source_message_ids": ["msg_018", "msg_019", "msg_020"]
}
```

Paging Agent 不直接覆盖历史记忆。它生成 page draft，再由 verifier 校验后提交。

### 5.3 Memory Page Store

建议同时支持文件和数据库：

```text
Markdown / JSON:
- 可读
- 可 diff
- 适合展示和调试

PostgreSQL / MySQL:
- metadata
- version
- patch
- audit
- eval result

Chroma / FAISS:
- semantic recall
- 可选，不作为第一核心
```

Page 类型：

```text
core_profile_page      长期用户偏好
task_state_page        当前任务状态
decision_page          已做决策
source_summary_page    历史片段摘要
tool_observation_page  工具结果摘要
```

### 5.4 Patch-based Memory Update

不要让 LLM 直接修改记忆。Memory Agent 只生成 patch。

示例：

```json
{
  "operation": "replace",
  "target_file": "user/profile.md",
  "old_text": "用户想做 Oncall Agent",
  "new_text": "用户不想做可被 Codex 替代的 Oncall Agent",
  "reason": "新对话显式否定了旧偏好",
  "source_refs": ["msg_021", "msg_022"]
}
```

patch 需要经过 verifier：

```text
- old_text 是否存在
- new_text 是否有来源支撑
- source_refs 是否有效
- 是否与现有高置信记忆冲突
- 是否修改了不允许修改的 memory block
```

### 5.5 Context Builder

每次 Agent 执行前，MemoryOS 根据当前任务和 token budget 构建 context package。

输入：

```text
session_id
current_task
recent_messages
available_budget
memory_pages
retrieval_query
```

输出示例：

```json
{
  "pinned_core": [
    "用户目标：约 20 天内完成 Agent infra 项目"
  ],
  "active_task_pages": [
    "MemoryOS Lite 需求定义"
  ],
  "recent_messages": [
    "最近 5 轮对话"
  ],
  "retrieved_pages": [
    "context rot 相关设计讨论"
  ],
  "dropped_pages": [
    {
      "page_id": "page_012",
      "reason": "low relevance"
    }
  ],
  "estimated_tokens": 9200
}
```

选择策略：

```text
pinned core memory 优先
当前任务相关 page 优先
近期决策优先
高置信记忆优先
低相关、过期、冲突、重复记忆降权
严格控制 token budget
```

### 5.6 Page Fault / Recall

当当前上下文缺少信息时，Agent 可以触发外部记忆召回。

工具：

```text
memory.search(query, top_k)
memory.load_page(page_id)
memory.expand_summary(page_id)
```

流程类似 OS page fault：

```text
当前 context 不足
-> 查询外部记忆
-> 加载相关 page
-> 继续执行当前任务
```

### 5.7 Provenance / Source Trace

每条记忆都应能追溯来源：

```text
raw conversation
-> memory page draft
-> verified memory page
-> context package
-> final answer
```

价值：

- 防止 LLM 编造记忆。
- 支持审计和调试。
- 支持 benchmark 中的 source accuracy 指标。

## 6. 系统架构

### Spring Boot Control Plane

职责：

```text
agent / namespace 管理
session 管理
conversation log 持久化
memory page metadata
memory patch audit
eval case 管理
eval run/report 管理
REST API
SSE 执行流
```

### Python Memory Engine

职责：

```text
token estimator
Paging Agent
memory extractor
conflict detector
patch generator
patch verifier
context builder
semantic retrieval
eval runner
```

### 存储建议

MVP：

```text
MySQL / PostgreSQL: metadata、session、patch、eval
Markdown / JSON files: memory pages
Chroma / FAISS: 可选向量索引
```

## 7. 接入其他 Agent 的方式

MemoryOS Lite 应设计成中间件/协议层，不绑定某个 Agent 框架。

### 7.1 REST API

通用接入方式，任何 Agent 都可以调用。

核心 API：

```text
POST /sessions/{id}/ingest
写入新消息、tool result、agent decision

POST /sessions/{id}/build-context
根据当前任务构造受预算限制的 context package

POST /sessions/{id}/page
触发 Paging Agent，将溢出内容分页

POST /memory/search
检索 memory pages

POST /memory/patch
提交记忆更新 patch

GET /sessions/{id}/trace
查看分页、检索、上下文组装轨迹
```

### 7.2 Python SDK

给 LangGraph / AutoGen / 自研 Agent 使用。

示例：

```python
memory.ingest(session_id, message)
context = memory.build_context(session_id, task, budget=12000)
memory.ingest(session_id, agent_output)
memory.maybe_page(session_id)
```

### 7.3 MCP Server

作为 MCP memory server 接入支持 MCP 的 Agent。

工具设计：

```text
memory_search(query, top_k)
memory_load_page(page_id)
memory_write_note(content, type)
memory_commit_patch(patch_id)
memory_build_context(task, budget)
```

### 7.4 OpenAI / Anthropic-compatible Proxy

作为 chat completion 代理：

```text
请求前：
MemoryOS build_context -> 注入 prompt/context package

请求后：
MemoryOS ingest assistant output / tool observations
MemoryOS maybe_page
```

优点：

- 对现有 Agent 侵入较小。
- 不需要 Agent 框架深度改造。

### 7.5 LangGraph Adapter

通过 hook 接入：

```text
before_model: build_context
after_model: ingest assistant output
after_tool: ingest tool observation
after_turn: maybe_page
```

## 8. 自定义 Benchmark 设计

Benchmark 的目的不是证明“模型记忆力强”，而是验证：

> 在限制 context window 的情况下，系统是否能通过分页、检索、换页和上下文构建，维持长会话任务状态。

### 8.1 对照组

至少设计以下 baseline：

```text
A. Full Context
把所有历史都塞进上下文，作为上限参考。

B. Sliding Window
只保留最近 N token。

C. Naive Summary
超过窗口后直接摘要。

D. Vector RAG
历史消息入向量库，按 query 检索。

E. MemoryOS Lite
分页 + page metadata + context builder + page fault recall。
```

### 8.2 Case 类型

设计 5 类 case：

```text
1. Long-range Recall
很早出现的信息被分页后，后面能否召回。

2. State Continuity
多轮项目决策变化后，能否保持最新状态。

3. Conflict Update
旧偏好被新偏好覆盖，是否使用新记忆而不是旧记忆。

4. Multi-hop Memory
答案需要结合多个 page，而不是单条检索命中。

5. Noise Resistance
大量无关对话中，能否不把噪声写入核心记忆。
```

### 8.3 Case 格式

示例：

```json
{
  "case_id": "conflict_001",
  "conversation": [
    {"id": "msg_001", "role": "user", "content": "我想做 Runbook Oncall Agent"},
    {"id": "msg_018", "role": "user", "content": "Runbook Oncall Agent 完全能由 Codex 替代，不想做"}
  ],
  "question": "用户最终决定不做哪个项目方向？",
  "expected_facts": ["Runbook-driven Oncall Agent"],
  "forbidden_facts": ["Raffle Strategy Lab"],
  "required_sources": ["msg_018"]
}
```

### 8.4 指标

核心指标：

```text
Answer Accuracy
回答是否正确。

Source Accuracy
引用的 memory page / source message 是否正确。

Update Accuracy
偏好变化后是否覆盖旧记忆。

Retrieval Hit Rate
正确 page 是否进入 context package。

Context Efficiency
每 1k token 上下文带来的正确率。

Compression Loss Rate
分页摘要后丢失关键事实的比例。

Hallucinated Memory Rate
回答是否使用不存在的记忆。

Latency / Cost
构建上下文和回答的耗时、token 成本。
```

最重要的指标：

```text
Accuracy / Context Tokens
```

因为项目目标是用更小、更干净的上下文维持长会话状态。

### 8.5 消融实验

用于证明各模块确实有效：

```text
MemoryOS Lite
- no page metadata
- no conflict detector
- no context builder ranking
- no source verifier
- no paging agent, only summary
```

如果去掉某模块后指标下降，就说明设计不是堆概念。

### 8.6 控制变量

为了可复现：

```text
同一个模型
同一批 case
同一 token budget
temperature = 0 或 0.2
固定 prompt version
记录每次 run trace
保存 context package
保存 retrieved pages
保存 final answer
```

### 8.7 MVP Benchmark 规模

20 天内建议：

```text
50 个 synthetic cases
5 类任务，每类 10 个
每个 case 8-20 轮对话
每个 case 有 expected facts / forbidden facts / required sources
```

可额外加入 10 个来自真实项目讨论的 case。

## 9. 可参考的公开 Benchmark

可参考但不完全照搬：

```text
LoCoMo:
长对话记忆 benchmark，测试 long-term conversational memory。

LongMemEval:
覆盖信息抽取、多 session 推理、时间推理、知识更新、拒答等能力。

BEAM:
偏大规模 memory retrieval 和 token efficiency。

Letta Memory Benchmark / Letta Evals:
更贴近 stateful agent、memory read/write/update 和 tool usage。
```

本项目自己的 benchmark 应重点验证分页机制、context budget 和 page fault recall，而不是单纯测模型长上下文问答。

## 10. 20 天开发计划

### Day 1-2

- 冻结需求和术语。
- 定义 session、message、memory page、patch、context package 数据模型。
- 写 architecture.md。

### Day 3-5

- Spring Boot Control Plane 初始化。
- 实现 session、conversation log、memory page metadata、patch audit API。

### Day 6-8

- Python Memory Engine 初始化。
- 实现 token estimator、Context Rot Guard、基础 paging trigger。

### Day 9-10

- 实现 Paging Agent。
- 输出 page draft。
- 实现 page verifier。

### Day 11-12

- 实现 Memory Page Store。
- 支持 Markdown / JSON page 写入。
- 支持 source trace。

### Day 13-14

- 实现 Context Builder。
- 支持 pinned core、recent messages、retrieved pages、dropped pages。

### Day 15

- 实现 memory.search / load_page / page fault recall。

### Day 16-17

- 实现 benchmark runner。
- 实现 Sliding Window、Naive Summary、Vector RAG、MemoryOS Lite 对照组。

### Day 18

- 实现极简前端控制台：
  - session timeline
  - memory pages
  - context package
  - benchmark report

### Day 19

- 完善 README、架构图、benchmark 文档。
- 准备 demo case。

### Day 20

- 录屏。
- 准备简历 bullet。
- 准备面试问答。

## 11. 不建议做的范围

20 天内不建议：

```text
完整 graph memory
复杂多 Agent 共享记忆
多模态记忆
生产级权限系统
完全自动 self-evolving memory
分布式向量数据库
复杂 OpenAI-compatible server
```

这些可以作为后续 roadmap。

## 12. 简历表述建议

第一条：

设计并实现 MemoryOS Lite，一个面向长运行 Agent 的上下文窗口记忆管理中间件。系统借鉴 Letta 的 OS 式分层记忆与 memU 的 agentic/file-based memory 思想，在 context rot 前主动控制工作窗口大小，并通过 Paging Agent 将溢出会话内容分页、压缩、索引到外部记忆层。

第二条：

实现 Context Rot Guard、Paging Agent、Memory Page Store、Context Builder 和 Page Fault Recall 等核心模块，支持 Core / Task / Decision / Summary 多类型 memory page、patch-based 记忆更新、来源追踪和受 token budget 约束的上下文构建。

第三条：

设计 MemoryOS benchmark，对比 Full Context、Sliding Window、Naive Summary、Vector RAG 与 MemoryOS Lite，在 long-range recall、state continuity、conflict update、multi-hop memory 和 noise resistance 等任务上评估 answer accuracy、source accuracy、context efficiency 和 hallucinated memory rate。

## 13. 项目核心卖点

本项目不是普通 memory.add/search/delete，也不是普通 RAG。

核心卖点是：

```text
context window 生命周期管理
context rot 前主动分页
Paging Agent 整理非标准化会话状态
memory page 外部存储
page fault recall
context budget control
source trace
memory benchmark
```

最终定位：

> MemoryOS Lite 是一个可接入任意 Agent 的 context-window memory middleware，提供 paging、recall、context package、patch update 和 evaluation 能力。
