# xmuse Frontend API Reference

> 用于 Gemini 生成前端设计的 API 信息文档
> Server: FastAPI, 默认端口 8100
> Protocol: JSON-RPC 2.0 over HTTP POST

## HTTP Endpoints

| Method | Path | 用途 |
|--------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/sse` | MCP SSE transport (Agent 用) |
| POST | `/messages` | JSON-RPC MCP 消息入口 |
| POST | `/mcp` | JSON-RPC MCP 消息入口 (同上) |

## 调用方式

所有工具通过 JSON-RPC 调用：

```json
POST /mcp
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_lanes",
    "arguments": {}
  }
}
```

响应格式：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "..."}],
    "structuredContent": { ... }
  }
}
```

前端直接使用 `result.structuredContent` 获取结构化数据。

---

## 工具列表 (11 个)

### 1. list_lanes

列出所有 lane（任务）。

**参数:** 无

**返回:**
```json
{
  "lanes": [
    {
      "feature_id": "error-knowledge-bounds",
      "task_type": "execute",
      "status": "pending",
      "prompt": "Add size bounds and eviction...",
      "branch": "feat/error-knowledge-bounds",
      "capabilities": ["code", "test"],
      "gate_profile": "xmuse-core",
      "priority": 70,
      "source": "auto",
      "retry_count": 0,
      "worktree": "/path/to/worktree",
      "base_head_sha": "201071c...",
      "gate_report": { ... },
      "depends_on": ["other-lane-id"]
    }
  ]
}
```

**Lane 字段说明:**

| 字段 | 类型 | 说明 |
|------|------|------|
| feature_id | string | 唯一标识 |
| task_type | string | 固定 "execute" |
| status | string | 见状态机 |
| prompt | string | 任务描述 |
| branch | string? | git 分支名 |
| capabilities | string[] | 所需能力 ["code","test"] |
| gate_profile | string? | 质量门 profile |
| priority | int | 优先级 (0-110, 越高越先执行) |
| source | string? | 来源 ("auto" / 未设置=手动) |
| retry_count | int? | 当前重试次数 |
| worktree | string? | 工作目录路径 |
| depends_on | string[]? | 依赖的 lane id 列表 |
| gate_report | object? | 最近一次 gate 报告 |

**Lane 状态机:**
```
pending → dispatched → executed → gated → reviewed → merged
              ↓            ↓          ↓
          exec_failed  gate_failed  rejected → reworking → dispatched
              ↓            ↓          ↓                    (max 2次)
           failed       failed      failed
```

### 2. enqueue_lane

创建新 lane。

**参数:**
```json
{
  "feature_id": "my-new-task",
  "prompt": "Fix the bug in ...",
  "capabilities": ["code", "test"]
}
```

**返回:**
```json
{
  "feature_id": "my-new-task",
  "task_type": "execute",
  "prompt": "Fix the bug in ...",
  "capabilities": ["code", "test"],
  "status": "queued"
}
```

### 3. get_status

获取单个 lane 状态 + 活跃 session 信息。

**参数:**
```json
{ "feature_id": "error-knowledge-bounds" }
```

**返回:**
```json
{
  "feature_id": "error-knowledge-bounds",
  "lane": {
    "feature_id": "error-knowledge-bounds",
    "status": "pending",
    "priority": 70,
    ...
  },
  "active_session": null
}
```

### 4. abort_lane

中止正在执行的 lane，发送 SIGTERM 给活跃进程。

**参数:**
```json
{ "feature_id": "my-task" }
```

**返回:**
```json
{
  "feature_id": "my-task",
  "aborted": true,
  "lane": { "feature_id": "my-task", "status": "aborted", ... },
  "active_session": { "pid": 12345, "status": "aborted", "abort_requested": true }
}
```

### 5. get_error_knowledge

关键词搜索错误知识库。

**参数:**
```json
{ "query": "mypy arg-type", "top_k": 3 }
```

**返回:**
```json
{
  "query": "mypy arg-type",
  "matches": [
    {
      "score": 2,
      "entry": {
        "id": "ek-001",
        "pit": "mypy arg-type on Optional fields",
        "root_cause": "Passing str | None to str parameter",
        "trigger": "Optional field without None check",
        "fix": "Add `if x is not None:` guard",
        "prevention": "Use strict mode or --warn-return-any",
        "source": "auto-mypy-...",
        "lesson": "Always narrow Optional before passing"
      }
    }
  ]
}
```

### 6. get_logs

获取指定 lane 的执行日志。

**参数:**
```json
{ "feature_id": "error-knowledge-bounds", "max_bytes": 200000 }
```

**返回:**
```json
{
  "feature_id": "error-knowledge-bounds",
  "logs": [
    { "path": "logs/gates/error-knowledge-bounds/report.json", "content": "..." }
  ],
  "combined": "== logs/gates/... ==\n...",
  "truncated": false
}
```

---

## Platform God 工具 (5 个)

以下工具主要供 God agent 使用，前端也可调用用于展示详情。

### 7. get_lane

获取单个 lane 完整详情（比 get_status 更完整）。

**参数:**
```json
{ "lane_id": "error-knowledge-bounds" }
```

**返回:** 完整 lane 对象（同 list_lanes 中的单个 lane）

### 8. get_gate_report

获取 lane 的质量门执行报告。

**参数:**
```json
{ "lane_id": "error-knowledge-bounds" }
```

**返回:**
```json
{
  "feature_id": "error-knowledge-bounds",
  "passed": false,
  "blocking_passed": false,
  "nonblocking_failures": [],
  "profile_ids": ["xmuse-core"],
  "resolution_reasons": { "xmuse-core": ["explicit_lane_profile"] },
  "warnings": ["skipped missing pytest path..."]
}
```

### 9. get_diff

获取 lane worktree 的 git diff。

**参数:**
```json
{ "lane_id": "error-knowledge-bounds" }
```

**返回:**
```json
{
  "diff": "diff --git a/src/... b/src/...\n+...\n-...",
  "returncode": 0
}
```

### 10. query_knowledge

搜索错误知识库（同 get_error_knowledge，God agent 专用名称）。

**参数:**
```json
{ "query": "import order ruff", "top_k": 5 }
```

**返回:** 同 get_error_knowledge

### 11. update_lane_status

更新 lane 状态（驱动状态机）。前端可用于手动推进/中止 lane。

**参数:**
```json
{
  "lane_id": "error-knowledge-bounds",
  "status": "dispatched",
  "metadata": { "assigned_to": "codex" }
}
```

**返回:** 更新后的 lane 对象，或错误：
```json
{ "error": "cannot transition error-knowledge-bounds from pending to merged" }
```

**合法状态转换:**

| 当前状态 | 可转换到 |
|----------|----------|
| pending | dispatched |
| dispatched | executed, exec_failed |
| executed | gated |
| gated | reviewed, rejected, gate_failed |
| reviewed | merged, failed |
| rejected | reworking, failed |
| reworking | dispatched |
| exec_failed | failed, reworking |
| gate_failed | failed, reworking |

---

## 前端定位

xmuse 前端不是"lane 管理后台"，而是**God 协作可观测性平台**。

核心价值：让用户判断"God 们干得好不好"，观察 CLI 协作链路的决策质量和知识演化。

### 核心展示维度

1. **God 协作时间线** — 哪个 God 做了什么决策、为什么 reject/merge、rework context 是什么
2. **知识积累趋势** — error_knowledge 命中率、同类错误是否收敛
3. **决策审计** — Review God 的 merge/rework/abandon 分布、决策是否合理
4. **异常告警** — 超时、连续失败、rework 循环

### 建议页面结构

| 页面 | 核心内容 |
|------|----------|
| **Observability Dashboard** | God 协作时间线 + 决策分布 + 异常告警 + 知识命中率趋势 |
| **Lane 详情 / 决策审计** | 单条 lane 的完整生命周期：God 决策链、gate 报告、diff、rework context |
| **知识库 Explorer** | error_knowledge 搜索 + 条目详情 + 命中/未命中统计 |

---

## 技术细节

- **Server 端口:** 8100 (可通过环境变量配置)
- **启动命令:** `uv run python xmuse/mcp_server.py`
- **CORS:** 未配置，前端需 same-origin 或添加 CORS 中间件
- **认证:** 无（本地使用）
- **数据持久化:** JSON 文件 (`xmuse/feature_lanes.json`, `xmuse/error_knowledge.json`)

## 前端调用示例 (JavaScript)

```javascript
async function callMcp(toolName, args = {}) {
  const res = await fetch('http://localhost:8100/mcp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: { name: toolName, arguments: args }
    })
  });
  const data = await res.json();
  return data.result.structuredContent;
}

// 获取所有 lanes
const lanes = await callMcp('list_lanes');

// 创建新 lane
await callMcp('enqueue_lane', {
  feature_id: 'fix-login-bug',
  prompt: 'Fix the login timeout issue in auth.py',
  capabilities: ['code', 'test']
});

// 获取 gate 报告
const report = await callMcp('get_gate_report', { lane_id: 'fix-login-bug' });
```
