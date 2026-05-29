# xmuse Frontend API Contract

> 面向前端实现的 xmuse API 契约文档
> Last updated: 2026-05-28
> Audience:
> - repo 内 xmuse 前端
> - Win 前端项目 `2e36b78c-feca-4c9e-94d2-de7a84be2ebc`

## Scope

这份文档只描述前端应直接消费的接口契约，不描述后端内部实现。

文档按三层语义组织：

1. `live now`
   当前后端已经返回，前端可以立即接入。
2. `mixed-run compatibility`
   为 GOD session-first 迁移准备的兼容约束。部分字段可能尚未 live，但前端必须按该语义预留。
3. `reserved next`
   已在 spec / plan 中锁定，前端可以先建类型与 UI 占位，但不能假定后端今天一定返回。

## Base URLs

默认本地开发地址：

| Surface | Base URL | Status |
|---|---|---|
| Dashboard REST | `http://localhost:8200/api` | `live now` |
| Chat REST | `http://localhost:8201/api/chat` | `live now` |
| MCP JSON-RPC | `http://localhost:8100/mcp` | `live now` |

建议前端环境变量：

```bash
NEXT_PUBLIC_XMUSE_API_BASE_URL=http://localhost:8200/api
NEXT_PUBLIC_XMUSE_CHAT_API_BASE_URL=http://localhost:8201/api/chat
NEXT_PUBLIC_XMUSE_MCP_ENDPOINT=http://localhost:8100/mcp
```

注意：

- 当前前端工程里的 `frontend/lib/mcp-config.ts` 默认把 MCP 指到 `http://localhost:8200/mcp`。
- 除非前面有反向代理，否则应改为 `8100/mcp`。

## Compatibility Rules

### 1. `status` 不是最终语义层

当前 lane 记录里的 `status` 仍然是 MVP runtime 状态。
前端必须准备接受后续新增的 `effective_status`。

约束：

- 如果响应里同时有 `status` 和 `effective_status`，UI 语义优先使用 `effective_status`
- 如果只有 `status`，按下面的 mixed-run 映射在前端本地降级解释

### 2. 混跑期状态映射

| Raw `status` | Mixed-run meaning | Preferred UI label |
|---|---|---|
| `pending` | dependency-ready but not yet dispatched | `ready` |
| `dispatched` | worker assigned | `dispatched` |
| `executed` | worker finished | `executed` |
| `gated` | gate passed, review queue bridge in progress | `under_review` |
| `reviewed` | verdict accepted through bridge | `reviewed` |
| `awaiting_final_action` | waiting human final gate | `awaiting_final_action` |
| `merged` | merged | `merged` |
| `rejected` | rework requested | `requeued` |
| `reworking` | retry/rework running | `requeued` |
| `exec_failed` | execution failure | `exec_failed` |
| `gate_failed` | gate failure | `gate_failed` |
| `failed` | terminal failure under legacy runtime | `terminated` by default |

### 3. 会话身份兼容规则

前端不能再把 session 唯一性绑定到 `feature_id`。

兼容约束：

- `feature_id` 只代表当前 work assignment
- `god_session_id` 才是未来稳定主键
- `session_address` 和 `session_inbox_id` 是路由与投递标识

如果 `/api/sessions` 还只返回旧 shape，前端可以继续展示；但一旦新字段出现，前端应以新字段为主。

## Dashboard REST API

### `GET /api/lanes`

用途：

- 读取 lane 列表
- 作为 observability / lane control / audit surface 的主列表数据源

当前响应：

```json
{
  "lanes": [
    {
      "feature_id": "chat-backend",
      "task_type": "execute",
      "status": "pending",
      "prompt": "Build chat API",
      "capabilities": ["code"],
      "priority": 0,
      "depends_on": [],
      "conversation_id": "conv-1",
      "resolution_id": "res-1",
      "graph_id": "graph-1",
      "graph_version": 1,
      "gate_profile": "xmuse-core"
    }
  ]
}
```

字段契约：

| Field | Type | Status | Notes |
|---|---|---|---|
| `feature_id` | `string` | `live now` | lane id |
| `task_type` | `"execute" \| string` | `live now` | 当前几乎总是 `execute` |
| `status` | `string` | `live now` | 原始 runtime 状态 |
| `effective_status` | `string` | `reserved next` | 混跑归一化状态 |
| `prompt` | `string` | `live now` | lane 描述 |
| `capabilities` | `string[]` | `live now` | 需要的能力 |
| `priority` | `number` | `live now` | 调度优先级 |
| `depends_on` | `string[]` | `live now` | graph 依赖 |
| `conversation_id` | `string` | `live now` | 来自 chat plane |
| `resolution_id` | `string` | `live now` | 来自 structured resolution |
| `graph_id` | `string` | `live now` | lane graph id |
| `graph_version` | `number` | `live now` | graph version |
| `gate_profile` | `string` | `live now` | gate profile |
| `gate_profiles` | `string[]` | `live now` | 多 profile 扩展 |
| `source_lane_id` | `string` | `live now` | patch-forward / follow-up lane 来源 |
| `review_decision` | `string` | `live now` | legacy bridge metadata |
| `review_summary` | `string` | `live now` | legacy bridge metadata |
| `review_verdict_id` | `string` | `live now` | legacy bridge metadata |
| `final_action_hold_id` | `string` | `live now` | final-action hold 标识 |
| `failure_reason` | `string` | `live now` | `exec_failed/gate_failed/failed` 解释 |

前端建议：

- 列表筛选先兼容旧 `status`
- 一旦 `effective_status` 出现，筛选和颜色映射改用 `effective_status`
- `prompt` 只用于摘要，不要当作结构化业务字段

### `GET /api/lanes/{feature_id}`

用途：

- 读取单个 lane 详情
- 读取聚合日志

当前响应：

```json
{
  "lane": {
    "feature_id": "chat-backend",
    "status": "gated",
    "prompt": "Build chat API"
  },
  "execution_log": "started\nfinished\n",
  "logs": [
    {
      "path": "logs/chat-backend-round-1.log",
      "content": "started\nfinished\n"
    }
  ]
}
```

字段契约：

| Field | Type | Status | Notes |
|---|---|---|---|
| `lane` | `Lane` | `live now` | 与列表项同 shape，但字段通常更全 |
| `execution_log` | `string` | `live now` | 所有匹配日志拼接文本 |
| `logs` | `Array<{ path: string; content: string }>` | `live now` | 原始日志片段 |

### `POST /api/lanes`

用途：

- 人工创建 lane

请求体：

```json
{
  "feature_id": "manual-fix",
  "prompt": "Investigate dashboard state mismatch",
  "capabilities": ["code", "test"],
  "priority": 70
}
```

响应：

- 返回创建后的 lane 对象
- 当前默认状态仍是 `pending`

注意：

- `pending` 在 mixed-run UI 里应显示为 `ready`

### `POST /api/lanes/{feature_id}/approve`

用途：

- 批准已完成 lane
- 或 resolve `awaiting_final_action` 的 pending hold

当前可批准状态：

- `done`
- `merged`
- `awaiting_final_action`

当前行为：

- 若 lane 是 `awaiting_final_action` 且 hold action 为 `merge`，批准后 lane 状态变 `merged`
- 若 hold action 为 `terminate`，批准后 lane 状态会落到 legacy `failed`

前端注意：

- mixed-run UI 应将上面第二种结果显示为 `terminated`
- 不能把 approve 按钮只绑定到 `done`

### `POST /api/lanes/{feature_id}/reject`

用途：

- 人工拒绝 lane
- 请求 rework

请求体：

```json
{
  "reason": "Missing tests",
  "rework": true
}
```

当前行为：

- 写入 `approval_status = "rejected"`
- 写入 `rejection_reason`
- 如果 `rework = true`，当前会把状态重置为 legacy `pending`

前端语义：

- 将此行为解释为 `requeued`
- 不要把它理解成“全新 lane”

### `GET /api/sessions`

用途：

- 读取活跃 session
- 当前既兼容旧 list shape，也兼容旧 dict shape
- 后续承接 GOD session registry

当前旧 shape 示例：

```json
{
  "sessions": [
    {
      "feature_id": "lane-a",
      "pid": 12345,
      "state": "running"
    }
  ]
}
```

当前兼容的 MCP dict shape：

```json
{
  "sessions": [
    {
      "feature_id": "lane-a",
      "session_id": "sess-1",
      "pid": 12345,
      "status": "running"
    }
  ]
}
```

预留新 shape：

```json
{
  "sessions": [
    {
      "god_session_id": "god-1",
      "role": "review",
      "agent_name": "review-god",
      "runtime": "codex",
      "session_address": "@review",
      "session_inbox_id": "inbox-review",
      "status": "running",
      "assignment_feature_id": "lane-a",
      "pid": 12345
    }
  ]
}
```

前端建议：

- session row key 优先级：`god_session_id` -> `session_id` -> `feature_id`
- 展示 assignment 时用 `assignment_feature_id`，不要把它当 session id

### `GET /api/errors`

用途：

- 读取 error knowledge entries

响应：

```json
{
  "errors": [
    {
      "entry_id": "err-1",
      "pit": "pytest failed"
    }
  ]
}
```

注意：

- 当前后端对 `error_knowledge.json` 的 shape 比较宽松
- 前端最好容忍字段不全

### `GET /api/resolutions`

用途：

- 读取 resolution read model

当前响应示例：

```json
{
  "resolutions": [
    {
      "resolution_id": "res-1",
      "conversation_id": "conv-1",
      "version": 1,
      "status": "approved",
      "goal_summary": "Build chat MVP",
      "approved_by": ["human"],
      "approval_mode": "manual"
    }
  ]
}
```

前端建议：

- 这是 chat -> execution handoff 的摘要视图
- 不要把它当成完整 resolution 内容，完整对象走 chat API

### `GET /api/verdicts`

用途：

- 读取 verdict read model

当前状态：

- endpoint `live now`
- 但 read model 内容仍偏薄，很多环境下可能为空

前端建议：

- 接口应被消费，但 UI 需要接受空列表
- 后续 authoritative verdict store 落地后，这里会变成审计主数据源

### `GET /api/metrics`

当前响应：

```json
{
  "total": 4,
  "done": 1,
  "failed": 1,
  "pending": 2,
  "avg_time_seconds": 20.0
}
```

预留 mixed-run 扩展：

```json
{
  "total": 4,
  "done": 1,
  "failed": 1,
  "pending": 2,
  "avg_time_seconds": 20.0,
  "ready": 1,
  "requeued": 1,
  "merged": 1,
  "terminal": 2
}
```

前端建议：

- 当前 live 页面可继续使用 `total/done/failed/pending`
- 一旦后端开始返回 `ready/requeued/terminal`，优先展示这些归一化指标

## Chat REST API

### `POST /api/chat/conversations`

请求：

```json
{ "title": "xmuse MVP" }
```

响应：

```json
{
  "id": "conv-1",
  "title": "xmuse MVP",
  "created_at": "2026-05-28T10:00:00Z"
}
```

### `GET /api/chat/conversations`

响应：

```json
{
  "conversations": [
    {
      "id": "conv-1",
      "title": "xmuse MVP",
      "created_at": "2026-05-28T10:00:00Z"
    }
  ]
}
```

### `GET /api/chat/conversations/{conversation_id}/messages`

响应：

```json
{
  "messages": [
    {
      "id": "msg-1",
      "conversation_id": "conv-1",
      "author": "Human operator",
      "role": "human",
      "content": "Need chat-driven lanes.",
      "created_at": "2026-05-28T10:01:00Z"
    }
  ]
}
```

### `POST /api/chat/conversations/{conversation_id}/messages`

请求：

```json
{
  "author": "Architect God",
  "role": "assistant",
  "content": "Propose splitting the work into three lanes."
}
```

当前说明：

- 这是通用 message append endpoint
- 当前前端 `/chat` 页面主要使用更窄的 thread message endpoint

### `POST /api/chat/conversations/{conversation_id}/proposals`

请求：

```json
{
  "author": "Architect God",
  "proposal_type": "plan",
  "content": "Build chat, planner, dashboard.",
  "references": ["docs/spec.md"]
}
```

响应：

- 返回 `Proposal`
- `status` 初始为 `open`

### `POST /api/chat/proposals/{proposal_id}/approve`

用途：

- proposal -> `StructuredResolution`
- 并触发：
  - resolution read model append
  - lane graph save
  - ready lane projection into `feature_lanes.json`

请求：

```json
{
  "approved_by": ["Human operator"],
  "approval_mode": "manual",
  "goal_summary": "Build chat MVP",
  "content": {
    "lanes": [
      { "feature_id": "chat-backend", "prompt": "Build chat API", "depends_on": [] }
    ]
  }
}
```

响应：

- 返回完整 `StructuredResolution`

### `GET /api/chat/resolutions/{resolution_id}`

用途：

- 读取完整 resolution 对象

响应关键字段：

| Field | Type |
|---|---|
| `id` | `string` |
| `conversation_id` | `string` |
| `version` | `number` |
| `status` | `draft \| approved \| superseded \| cancelled` |
| `derived_from_proposal_ids` | `string[]` |
| `approved_by` | `string[]` |
| `approval_mode` | `string` |
| `goal_summary` | `string` |
| `content` | `object` |
| `created_at` | `string` |

### `GET /api/chat/threads`

用途：

- `/chat` 页面当前主入口

当前响应示例：

```json
{
  "threads": [
    {
      "id": "conv-1",
      "featureId": "xmuse MVP",
      "title": "xmuse MVP",
      "agent": "Human + Gods",
      "status": "reviewed",
      "updatedAt": "2026-05-28T10:05:00Z",
      "summary": "Need a dashboard lane",
      "messages": [
        {
          "id": "msg-1",
          "role": "user",
          "author": "Human operator",
          "kind": "checkpoint",
          "content": "Need a dashboard lane"
        }
      ]
    }
  ]
}
```

注意：

- 这是 thread read model，不是底层 chat store 原始表结构
- 当前 `status` 仍较粗糙，后续 GOD session layer 落地后会增强

### `POST /api/chat/threads/{conversation_id}/messages`

用途：

- `/chat` 页面发送人类 checkpoint

请求：

```json
{
  "message": "Approved. Proceed with the next minimal patch."
}
```

响应：

```json
{
  "thread_id": "conv-1",
  "message": {
    "id": "msg-2",
    "role": "user",
    "author": "Human operator",
    "kind": "checkpoint",
    "content": "Approved. Proceed with the next minimal patch."
  }
}
```

## MCP JSON-RPC

MCP 主要用于 agent/tool surface，不是当前前端主数据源。
前端若只做 chat + observability，可先优先接 REST。

当前入口：

| Method | Path |
|---|---|
| `GET` | `/health` |
| `GET` | `/sse` |
| `POST` | `/messages` |
| `POST` | `/mcp` |

标准调用：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_lane",
    "arguments": { "lane_id": "chat-backend" }
  }
}
```

前端只建议把 MCP 用于：

- 调试卡片
- raw tool call viewer
- 对照 REST 数据做低层排障

不建议：

- 用 MCP 取代 dashboard/chat 主 REST

## Recommended Frontend Type Updates

Win 前端工程当前最需要的类型修正：

### `frontend/lib/types.ts`

建议新增或预留：

```ts
export type EffectiveLaneStatus =
  | "planned"
  | "ready"
  | "dispatched"
  | "executed"
  | "under_review"
  | "reviewed"
  | "awaiting_final_action"
  | "merged"
  | "requeued"
  | "terminated"
  | "exec_failed"
  | "gate_failed";

export type Lane = {
  feature_id: string;
  task_type: string;
  status: string;
  effective_status?: EffectiveLaneStatus;
  prompt: string;
  capabilities: string[];
  priority: number;
  depends_on?: string[];
  conversation_id?: string;
  resolution_id?: string;
  graph_id?: string;
  graph_version?: number;
  gate_profile?: string;
  gate_profiles?: string[];
  source_lane_id?: string;
  review_decision?: string;
  review_summary?: string;
  review_verdict_id?: string;
  final_action_hold_id?: string;
  failure_reason?: string;
};

export type GodSession = {
  god_session_id?: string;
  session_id?: string;
  feature_id?: string;
  role?: string;
  agent_name?: string;
  runtime?: string;
  session_address?: string;
  session_inbox_id?: string;
  assignment_feature_id?: string;
  status?: string;
  state?: string;
  pid?: number;
};
```

### `frontend/lib/dashboard-api-client.ts`

建议补充接口：

- `listSessions()`
- `listMetrics()`
- `listResolutions()`
- `listVerdicts()`

并且：

- lane normalize 时保留 `raw status`
- 如果收到 `effective_status`，不要丢掉

### `frontend/components/observability-client.tsx`

建议把当前这些硬编码语义迁移为兼容层：

- `pending` 视图文案改成 `ready`
- `rejected/reworking` 统一显示为 `requeued`
- `failed` 在有 `failure_reason` 时显示更具体原因

## Reserved Next-Phase Read Models

这些对象已经在架构和计划中定案，但当前接口未必 live：

- `lane_graphs`
- `execution_runs`
- `lane_runs`
- `review_tasks`
- `verdicts` authoritative store-backed view
- `final_actions`
- `audit_timeline`

前端现在可以先做：

- 信息架构
- types 占位
- 空态 UI

前端现在不要做：

- 假设这些 endpoint 一定已经存在
- 把 lane metadata 逆向拼成 authoritative review truth

## Summary

当前前端实现应以这三条为主：

1. 主数据面继续走 `8200/api` 和 `8201/api/chat`
2. lane/session 视图按 mixed-run 兼容层解释，不再把原始 `status` 当最终语义
3. 为 `god_session_id`、`effective_status`、verdict/read-model 扩展字段预留类型和 UI
