# xmuse Platform + Agent 架构重设计

> Date: 2026-05-27
> Status: spec
> Inspired by: [clowder-ai/cat-cafe](https://github.com/zts212653/clowder-ai) 的平台+agent 分层架构

## Why

当前 `master_loop.py`（~1400 行）将调度、执行、质量门、review、rework、知识积累全部硬编码在一个 asyncio loop 中。问题：

1. **不可插拔** — 无法独立替换 review 策略或调度算法
2. **无上下文积累** — 每个 lane 的执行和 review 都是孤立的，不知道之前发生了什么
3. **agent 无自主性** — codex worker 只是被动执行 prompt，不能主动查询信息或请求协作
4. **扩展困难** — 添加新能力（如 God 直接修复简单错误）需要修改核心 loop

## What — 目标架构

### 分层

```
┌─────────────────────────────────────────────────────┐
│  xmuse Platform (Python asyncio)                    │
│  ├── EventBus (asyncio callbacks, 非外部 MQ)         │
│  ├── LaneStateMachine (feature_lanes.json 持久化)    │
│  ├── AgentSpawner (one-shot process lifecycle)      │
│  └── MCP Server (localhost HTTP, stdio 均可)         │
└─────────────────────────────────────────────────────┘
         │ spawn + MCP endpoint
         ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Decision God │ │ Execution God│ │ Review God   │ │Knowledge God │
│ (claude/codex)│ │ (codex)      │ │ (claude/codex)│ │(claude/codex)│
│ one-shot per │ │ one-shot per │ │ one-shot per │ │ one-shot per │
│ sched round  │ │ lane         │ │ gated lane   │ │ failed/merged│
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### 核心原则

1. **平台不做决策** — 只做调度、状态机、基础设施
2. **Agent 可插拔** — 每个 God 是独立的 skill prompt + spawn 配置
3. **MCP 是上下文桥梁** — one-shot agent 通过 MCP server 按需查询状态
4. **事件驱动** — lane 状态变更触发下游 agent spawn

## Lane 状态机

```
pending → scheduled → dispatched → executed → gated → reviewed → merged
                                      ↓          ↓         ↓
                                   exec_failed  gate_failed  rejected
                                      ↓          ↓         ↓
                                   abandoned   abandoned   reworking → dispatched
```

状态转换由 agent 通过 MCP `update_lane_status()` 驱动。
平台监听状态变更事件，触发下游 agent spawn。

## MCP Server 接口

### 查询接口（只读）

| Tool | 描述 |
|------|------|
| `list_lanes(status?, limit?)` | 列出指定状态的 lanes |
| `get_lane(lane_id)` | 获取 lane 完整详情（prompt, worktree, history） |
| `get_gate_report(lane_id)` | 获取最近一次 gate 执行报告 |
| `get_diff(lane_id)` | 获取 lane worktree 的 git diff |
| `query_knowledge(query, top_k?)` | 搜索 error_knowledge 相关条目 |
| `get_lane_history(n?)` | 最近 N 个已完成 lane 的摘要 |
| `get_platform_status()` | 当前并发数、队列深度、运行时间等 |

### 写入接口

| Tool | 描述 |
|------|------|
| `schedule_lane(lane_id, priority)` | 设定 lane 优先级（Decision God 调用） |
| `update_lane_status(lane_id, status, metadata?)` | 推进状态机 |
| `record_knowledge(entry)` | 写入 7 槽位知识条目 |
| `record_decision(lane_id, decision, reasoning)` | 记录决策审计日志 |
| `apply_patch(lane_id, patch_content)` | 对 worktree 应用 patch |
| `mention_agent(target, task, context?)` | 请求另一个 God 介入 |

### 安全护栏（平台强制，agent 不可绕过）

- `scope_constraint`: 每次 spawn Execution God 时自动注入，限制修改范围
- `diff_size_guard`: merge 前平台检查 insertion 数量（上限 1000 行）
- `timeout`: 每个 agent 进程最长 3600s
- `worktree_clean`: dispatch 前平台自动 clean worktree

## Agent 定义

### Decision God

```yaml
name: decision-god
trigger: scheduling_round_start
runtime: codex  # or claude
skill_prompt: |
  你是 xmuse 的调度决策者。
  通过 MCP 查看当前队列状态和历史，决定本轮执行哪些 lane。
  考虑：优先级、依赖关系、历史失败率、并发位可用性。
  输出：调用 schedule_lane() 设定优先级，调用 mention_agent("execution-god", ...) 触发执行。
timeout_s: 120
```

### Execution God

```yaml
name: execution-god
trigger: lane_status == "dispatched"
runtime: codex
skill_prompt: |
  你是 xmuse 的代码执行者。
  修复指定 lane 的问题。通过 MCP query_knowledge() 获取相关历史教训。
  完成后调用 update_lane_status(lane_id, "executed")。
timeout_s: 3600
spawn_per: lane
```

### Review God

```yaml
name: review-god
trigger: lane_status == "gated"
runtime: codex  # or claude
skill_prompt: |
  你是 xmuse 的代码审计者。
  通过 MCP 获取 gate 报告和 diff，审查代码质量、scope 合规性、逻辑正确性。
  决策三选一：
  - merge: 调用 update_lane_status(lane_id, "reviewed")
  - rework: 调用 update_lane_status(lane_id, "rejected", {rework_context: "..."})
  - abandon: 调用 update_lane_status(lane_id, "abandoned", {reason: "..."})
timeout_s: 120
spawn_per: lane
```

### Knowledge God

```yaml
name: knowledge-god
trigger: lane_status in ["abandoned", "merged"]
runtime: codex  # or claude
skill_prompt: |
  你是 xmuse 的知识工程师。
  分析已完成 lane 的生命周期，提取可复用的教训。
  对于 gate_failed 的简单错误（类型标注、import 顺序等），直接 apply_patch 修复。
  对于复杂失败，记录 7 槽位知识条目到 error_knowledge。
  槽位：坑/根因/触发条件/修复/防护/来源/教训
timeout_s: 180
spawn_per: lane
```

## 事件流示例

```
1. auto_discovery 生成新 lane → 平台写入 pending
2. 调度轮次开始 → 平台 spawn Decision God
3. Decision God 通过 MCP 查看队列 → 调用 schedule_lane() → mention_agent("execution-god")
4. 平台 spawn Execution God (one-shot codex, 带 scope constraint)
5. Execution God 修完代码 → update_lane_status("executed")
6. 平台执行 run_gate (基础设施) → 状态变为 "gated"
7. 平台 spawn Review God
8. Review God 通过 MCP 读 diff + gate 报告 → 决定 merge → update_lane_status("reviewed")
9. 平台执行 auto_merge (基础设施)  → 状态变为 "merged"
10. 平台 spawn Knowledge God → 分析结果 → record_knowledge()
```

## 从当前架构迁移

| 当前 master_loop 逻辑 | 新架构归属 |
|------------------------|------------|
| `_dispatch_round()` | Platform 事件 + Decision God |
| `_run_lane()` | Execution God |
| `_check_quality_gate()` | Platform 基础设施 (run_gate) |
| `_review_lane_before_merge()` | Review God |
| `_auto_merge_worktree()` | Platform 基础设施 |
| `_should_retry_lane()` | Review God rework 决策 |
| `_inject_error_knowledge()` | Execution God 通过 MCP 自查 |
| `_inject_scope_constraint()` | Platform spawn 时强制注入 |
| `_gc_stale_lanes()` | Platform 定时任务 |
| `_run_auto_discovery()` | Platform 定时任务 |
| `error_knowledge.inject_context()` | MCP query_knowledge() |

## 实现约束

- **不引入外部 MQ** — asyncio callbacks 即可
- **MCP server 用 stdio 或 localhost HTTP** — 视 agent runtime 支持情况选择
- **状态持久化仍用 feature_lanes.json** — 不引入数据库
- **gate 执行仍由平台侧完成** — 模块化 gate 已就绪，不需要 agent 介入
- **merge 操作仍由平台执行** — 安全护栏，agent 不直接 push

## MVP 范围（Phase 1）

只构建：**平台基建 + Execution God + Review God**

目标：能管理手动生成的 lane 的执行、质量门、审查和 merge/rework 决策。

### MVP 包含

- Platform: LaneStateMachine + EventBus + AgentSpawner + MCP Server（最小工具集）
- Execution God: one-shot codex，修代码，调用 `update_lane_status("executed")`
- Review God: one-shot codex/claude，审查 diff + gate 报告，决定 merge/rework/abandon
- MCP 最小工具集: `get_lane`, `get_gate_report`, `get_diff`, `query_knowledge`, `update_lane_status`
- 状态机转换验证（transition guard）
- God 超时/失败 fallback（超时 → 标记 failed，不自动重试）

### MVP 不包含（后续迭代）

- Decision God（MVP 阶段用现有优先级排序逻辑）
- Knowledge God（MVP 阶段用现有 error_knowledge.inject_context）
- `mention_agent` 跨 God 协作
- `apply_patch` / Quick Fix lane
- `schedule_lane` / `record_knowledge` / `record_decision`
- MemoryOS 集成
- 多机分布式部署
- Web UI / dashboard

### MVP 状态机（简化）

```
pending → dispatched → executed → gated → reviewed → merged
                          ↓          ↓         ↓
                       exec_failed  gate_failed  rejected → reworking → dispatched
                          ↓          ↓         ↓
                       failed      failed     failed (max_retries=2)
```

- `pending → dispatched`: Platform（按现有优先级排序）
- `dispatched → executed / exec_failed`: Execution God
- `executed → gated`: Platform（run_gate 基础设施）
- `gated → reviewed / gate_failed`: Review God
- `reviewed → merged`: Platform（auto_merge 基础设施）
- `rejected → reworking → dispatched`: Review God 触发，Platform 重新 dispatch

### MVP MCP 工具集

| Tool | 方向 | 调用者 |
|------|------|--------|
| `get_lane(lane_id)` | 读 | Any |
| `get_gate_report(lane_id)` | 读 | Review God |
| `get_diff(lane_id)` | 读 | Review God |
| `query_knowledge(query, top_k?)` | 读 | Execution God |
| `update_lane_status(lane_id, status, metadata?)` | 写 | Any God |

### Review 建议已采纳

1. **状态机转换验证** — `update_lane_status` 校验合法转换，拒绝非法操作
2. **God 超时合约** — Execution God 3600s / Review God 120s，超时 → lane 标记 failed
3. **移除 apply_patch** — MVP 不含 Knowledge God，不存在直接 patch 能力
4. **Rework 深度限制** — max_retries=2，超过标记 failed

## 不在范围内（全量架构，后续迭代）

- Decision God + Knowledge God
- God 间协作（mention_agent）
- MemoryOS 集成
- 多机分布式部署
- Web UI / dashboard
