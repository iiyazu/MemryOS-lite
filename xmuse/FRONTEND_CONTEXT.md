# xmuse 前端重构上下文文档

本文档供 Open Design 前端原型设计使用，描述 xmuse 系统的后端能力、数据流和交互需求。

## 系统概述

xmuse 是一个本地多 agent 自治编排系统，调度多个 AI agent（Codex / Claude Code）并行执行 feature lane。前端需要展示系统状态、支持人机交互、以及未来的 God Group Chat 长 session 对话。

## 后端 API 端点

### xmuse 调度层（待实现 REST API，当前状态从文件读取）

| 数据 | 来源 | 格式 |
|------|------|------|
| Lane 列表与状态 | `xmuse/feature_lanes.json` | `{lanes: [{feature_id, status, task_type, prompt, depends_on, ...}]}` |
| 执行日志 | `xmuse/logs/round_*.log` | 文本日志 |
| Feature 工作产出 | `xmuse/work/features/{id}/` | brainstorm.md, spec.json, result.md, review_verdict.json |
| Agent 配置 | `xmuse/agents.json` | `{agents: [{runtime, name, capabilities}]}` |
| 错误知识库 | `xmuse/knowledge/` | error patterns, skill proposals |

### MemoryOS API（127.0.0.1:8000）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/sessions` | POST | 创建会话 |
| `/sessions/{id}/ingest` | POST | 写入消息（role + content） |
| `/sessions/{id}/build-context` | POST | 构建上下文（task, budget, retrieval_query） |
| `/sessions/{id}/page` | POST | 触发 paging |
| `/sessions/{id}/trace` | GET | 获取 trace 事件 |
| `/sessions/{id}/summary` | GET | 会话摘要 |
| `/sessions/{id}/ingest-batch` | POST | 批量写入 |
| `/memory/search` | POST | 搜索记忆（query, top_k） |
| `/memory/pages/{id}` | GET | 获取 Memory Page |
| `/archives/ingest` | POST | 文档归档 |
| `/archives/passages` | GET | 列出归档段落 |

## 前端需要支持的核心交互

### 1. 调度监控面板

- Lane 状态总览（done/running/pending/failed 计数 + 列表）
- 实时 lane 状态变化（轮询 feature_lanes.json 或 WebSocket）
- Lane 依赖图可视化（DAG，显示并发组）
- 点击 lane 查看详情（prompt、产出、日志、review verdict）

### 2. God Group Chat（长 session 交互，核心新功能）

这是前端最重要的新增部分。设计规格详见 `docs/superpowers/specs/2026-05-26-god-group-chat-design.md`。

**核心模型：** 多个 AI agent（God）在群聊中共存，通过消息交互、互相委派任务、请求人类审批。

**God 角色：**
- Architect-God — 设计决策、架构审查、任务委派（默认接收者）
- Builder-God — 代码实现、测试、dispatch lane
- Reviewer-God — 代码审查、质量评估
- Ops-God — 监控执行、处理失败、基础设施

**交互模式：**
- 群聊消息流（God 消息 + 人类消息，平等参与）
- God 状态指示器（idle / thinking / waiting_approval）
- 审批卡片（内嵌在聊天中，approve/reject 按钮）
- @mention 路由（@God-A 唤醒特定 God）
- 无 @mention 消息默认路由到 Architect-God

**God 生命周期（记忆接力）：**
```
人类发消息 → Gateway 唤醒 God → God 进程启动
→ MemoryOS build_context 恢复完整状态
→ God 处理消息，产出 JSON（messages + actions）
→ Gateway 执行 actions（dispatch_lane, request_approval, @mention）
→ MemoryOS ingest 保存交互
→ God 进程退出（非常驻）
```

**God 输出格式：**
```json
{
  "messages": [{"text": "...", "visible": true}],
  "actions": [
    {"type": "dispatch_lane", "feature_id": "...", "prompt": "..."},
    {"type": "request_approval", "description": "...", "options": ["approve", "reject"]},
    {"type": "mention", "god_id": "builder", "message": "..."},
    {"type": "call_tool", "god_id": "reviewer", "tool": "review_code", "args": {}}
  ],
  "task_state": {"current_task": "...", "next_step": "...", "pending": []}
}
```

**前端 UI 要素：**
- 群聊主界面（God 头像 + 角色标签 + 消息气泡）
- God 活动侧边栏（当前哪些 God 在思考、在做什么）
- 内嵌审批卡片（God 发起 request_approval 时渲染为卡片）
- @mention 自动补全
- "New Lane" 快捷操作（通过 Architect-God 派发）
- God-to-God 对话链可视化（深度限制 5 跳）

### 3. 错误知识面板

- 错误模式列表（频次、来源、状态）
- 错误 → 技能提炼生命周期展示
- Skill proposals（draft/active/retired）

### 4. 设计 Pipeline 触发

- 输入目标/想法 → 触发 `task_type: "design"` lane
- 展示 pipeline 进度（brainstorm → spec_review → decompose → lane_review → emit）
- 审查中间产物（spec.json, lane_graph.json）
- 人工干预点（review gate 失败时展示 findings，允许修改后重试）

## 技术约束

- 后端: Python FastAPI (MemoryOS) + xmuse master_loop (异步 Python)
- 通信: REST + WebSocket（God Gateway 需要 WebSocket 实时推送）
- 数据持久化: SQLite (MemoryOS), JSON 文件 (xmuse 状态)
- 认证: API Key (MemoryOS), 本地无认证 (xmuse)

## 页面结构建议

1. **Dashboard** — Lane 状态总览 + 系统健康
2. **Lanes** — Lane 列表/详情/DAG 图
3. **Chat** — God Group Chat 主界面（长 session 核心）
4. **Knowledge** — 错误模式 + 技能提炼
5. **Design** — Pipeline 触发 + 中间产物审查
