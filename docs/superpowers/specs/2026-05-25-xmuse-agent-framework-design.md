# xmuse Agent Framework + memoryOS Middleware Design

Version: 0.1.0 | Date: 2026-05-25

## 一、概述

本文档定义 xmuse 从文件轮询式 master/slave 系统升级为 session-based 多 agent
开发框架的设计，以及 memoryOS Lite 从库模式升级为可独立部署中间件的设计。

两个演进方向共享同一份 spec，因为它们存在耦合：agent 通过 memoryOS HTTP API
实现跨 session 知识传递。

---

## 二、设计约束（已确认）

| 约束 | 来源 |
|------|------|
| 编排模式保留 master/slave 层级 | brainstorming Q1 |
| 引入跨 runtime review（Codex review Claude Code 产出，反之亦然） | brainstorming Q1 |
| 双 runtime：Codex CLI + Claude Code CLI | brainstorming 选项确认 |
| 通信模式：stdin/stdout（LocalSession） | brainstorming Q2 |
| 预留 transport 抽象（RemoteSession → Streamable HTTP） | brainstorming Q2 补充 |
| Per-feature session 生命周期 | brainstorming Q3 |
| memoryOS 作为外部记忆层替代 Session Chain | brainstorming Q3 |
| Abort signal + heartbeat + 孤儿回收 | brainstorming Q4 |
| A2A depth limit 留后续阶段 | brainstorming Q4 |
| memoryOS middleware：X-API-Key auth、request_id、structured logging、CORS | brainstorming 选项确认 |
| SQLite 始终为权威存储 | 项目约束 |
| 默认行为不变（无 Redis / 无 API key / v1 fallback） | 项目约束 |

---

## 三、xmuse Agent Framework

### 3.1 Agent Registry

Agent Registry 管理可用 runtime 的注册、能力声明和生命周期。

```python
class AgentRuntime(str, Enum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"

@dataclass
class AgentDescriptor:
    runtime: AgentRuntime
    name: str
    capabilities: list[str]  # ["code", "review", "test"]
    session_config: SessionConfig

@dataclass
class SessionConfig:
    transport: Literal["local", "remote"]  # local = stdin/stdout
    heartbeat_interval_s: int = 30
    heartbeat_timeout_s: int = 300
    max_context_tokens: int | None = None  # None = runtime default
```

Registry 从配置文件加载，不从 master_state.json 硬编码：

```jsonc
// xmuse/agents.json
{
  "agents": [
    {
      "runtime": "codex",
      "name": "codex-worker-1",
      "capabilities": ["code", "test"],
      "session_config": { "transport": "local", "heartbeat_interval_s": 30 }
    },
    {
      "runtime": "claude_code",
      "name": "claude-reviewer-1",
      "capabilities": ["code", "review"],
      "session_config": { "transport": "local", "heartbeat_interval_s": 30 }
    }
  ]
}
```

### 3.2 Transport 抽象

所有 agent 通信通过 `AgentSession` 接口，屏蔽底层传输差异：

```python
class AgentSession(Protocol):
    async def send(self, message: str) -> None: ...
    async def receive(self) -> str: ...
    async def abort(self) -> None: ...
    def is_alive(self) -> bool: ...

class LocalSession(AgentSession):
    """stdin/stdout transport for same-machine agents."""
    process: asyncio.subprocess.Process
    _abort_event: asyncio.Event

class RemoteSession(AgentSession):
    """Streamable HTTP transport for remote agents (future)."""
    endpoint: str
    credentials: CallbackCredentials
```

LocalSession 实现：
- `send()`: 写入 process.stdin（JSON-line 格式）
- `receive()`: 从 process.stdout 读取一行 JSON
- `abort()`: 设置 abort event + 发送 SIGTERM + 等待 grace period + SIGKILL
- `is_alive()`: 检查 process.returncode is None + last_heartbeat 时效

### 3.3 Session Lifecycle

Per-feature session 生命周期：

```
                 ┌─────────────────────────────────────────┐
                 │           Master Dispatcher              │
                 └──────────────┬───────────────────────────┘
                                │ dispatch(feature_id, task)
                                ▼
                 ┌─────────────────────────────────────────┐
                 │         SessionManager                   │
                 │                                         │
                 │  1. 从 Registry 选择 agent              │
                 │  2. spawn process (codex / claude-code) │
                 │  3. 创建 LocalSession handle            │
                 │  4. 注册到 active_sessions map          │
                 └──────────────┬───────────────────────────┘
                                │
                                ▼
              ┌────────────────────────────────────┐
              │         Agent Session (running)     │
              │                                    │
              │  stdin ← task prompt + context     │
              │  stdout → progress + result        │
              │  heartbeat every 30s               │
              │                                    │
              │  memoryOS.build_context() on start │
              │  memoryOS.ingest() on key events   │
              └────────────────┬───────────────────┘
                               │ task complete / abort / timeout
                               ▼
              ┌────────────────────────────────────┐
              │         Session Teardown            │
              │                                    │
              │  memoryOS.ingest(final_result)     │
              │  从 active_sessions 移除           │
              │  process exit                      │
              └────────────────────────────────────┘
```

状态机：

```
PENDING → STARTING → RUNNING → COMPLETING → DONE
                        │                     │
                        ├── ABORTING ──────────┘
                        └── TIMEOUT ──────────→ FAILED
```

### 3.4 Launcher Adapters

每种 runtime 有独立的 launcher adapter，处理进程启动、prompt 注入和输出解析：

```python
class LauncherAdapter(Protocol):
    def build_command(self, feature_id: str, worktree: Path) -> list[str]: ...
    def format_prompt(self, task: str, context: str) -> str: ...
    def parse_output(self, raw: str) -> AgentOutput: ...

class CodexLauncher(LauncherAdapter):
    """Codex CLI session mode launcher."""
    def build_command(self, feature_id, worktree):
        return ["codex", "--cwd", str(worktree), "--quiet"]

class ClaudeCodeLauncher(LauncherAdapter):
    """Claude Code CLI session mode launcher."""
    def build_command(self, feature_id, worktree):
        return ["claude", "--cwd", str(worktree), "--output-format", "json"]
```

Adapter 职责：
- 构建启动命令（含 worktree 路径、环境变量）
- 将 master 的 task description 格式化为该 runtime 接受的 prompt 格式
- 解析 stdout JSON-line 输出为统一的 `AgentOutput` 结构
- 处理 runtime 特有的 quirks（如 Codex 的 approval policy、Claude Code 的 permission mode）

### 3.5 Worklist Consumer Loop

替代当前 master 的 scan-all-features 轮询模式。

现有 Worklist 基于 `threading.Lock` 的同步 `consume()` 返回 `DispatchEntry | None`。
Consumer 需要 async 适配：新增 `async_consume()` 方法（基于 `asyncio.Queue`），
不修改现有同步 `consume()` 签名，确保现有 21 个 routing 测试不受影响。

```python
@dataclass
class TaskDescriptor:
    feature_id: str
    task_type: Literal["execute", "review", "rework"]
    prompt: str
    required_capabilities: list[str]  # ["code"], ["review"], ["code", "test"]
    developed_by_runtime: AgentRuntime | None = None  # 用于跨 runtime review 排除

class WorklistConsumer:
    def __init__(self, registry: AgentRegistry, session_mgr: SessionManager):
        self._queue = asyncio.Queue[TaskDescriptor]()
        self._registry = registry
        self._session_mgr = session_mgr
        self._max_concurrent = 4  # 并发 session 上限
        self._semaphore = asyncio.Semaphore(4)

    async def run(self):
        """Main consumer loop - processes tasks from queue."""
        while True:
            task = await self._queue.get()  # async blocking
            async with self._semaphore:
                agent = self._registry.select(
                    task.required_capabilities,
                    exclude_runtime=task.developed_by_runtime,
                )
                await self._session_mgr.dispatch(agent, task)

    async def enqueue(self, task: TaskDescriptor) -> None:
        await self._queue.put(task)
```

Registry.select() 策略：
- capability match：agent.capabilities 必须包含 task.required_capabilities
- exclude_runtime：跨 runtime review 时排除开发者使用的 runtime
- 空闲优先：优先选择当前无 active session 的 agent
- 如果多个候选，round-robin

Task 来源：
- Master gate 通过后的 feature execution 请求
- Review 请求（跨 runtime review，携带 `developed_by_runtime`）
- Rework 请求（review 失败后的修复任务）

### 3.6 跨 Runtime Review

利用不同模型的盲点差异提升代码质量：

```
Feature 开发完成 (by Codex)
  → Master 将 review task 入队 worklist
  → WorklistConsumer 选择 Claude Code agent
  → Claude Code session 启动，读取 diff + context
  → 产出 review verdict
  → Master 根据 verdict 决定 merge / rework
```

规则：
- 开发和 review 必须使用不同 runtime
- Review agent 通过 memoryOS.build_context() 获取 feature 背景
- Review verdict 格式复用现有 review_verdict.json schema
- 不改变 hermes_hardening gate 逻辑，review 结果作为 gate 输入之一

### 3.7 Abort / Heartbeat / 孤儿回收

**Abort**：

```python
class SessionManager:
    async def abort(self, feature_id: str) -> None:
        session = self._active.get(feature_id)
        if session:
            await session.abort()  # SIGTERM → grace 10s → SIGKILL
            self._active.pop(feature_id)
```

**Heartbeat（ping/pong 模式）**：

Master 主动检测，不依赖 agent 自行上报（避免 heartbeat 注入的复杂度）：
- SessionManager 每 30s 向 agent stdin 发送 `{"type": "ping"}`
- Agent 收到 ping 后回复 `{"type": "pong"}`
- 连续 10 次 ping 无 pong 响应（5min）→ 标记 TIMEOUT → abort

Agent 也可以主动上报 heartbeat 作为补充（如报告 context_usage）：
```json
{"type": "heartbeat", "ts": "2026-05-25T10:00:00Z", "context_usage": 0.45}
```
主动 heartbeat 不是必需的，Master 不依赖它判断存活。

**孤儿回收**：

Master 启动时：
1. 读取 `xmuse/active_sessions.json`（记录 pid + feature_id + master_instance_id）
2. 只 kill master_instance_id 匹配当前实例的残留进程（避免多实例误杀）
3. 清理状态文件
4. 如果没有状态文件，不做任何 kill 操作（安全降级）

### 3.8 Graceful Shutdown

Master 收到 SIGTERM 时：

```
1. 停止从 WorklistConsumer 消费新任务（设置 shutdown flag）
2. 向所有 active sessions 发送 {"type": "abort"} via stdin
3. 等待 grace period（30s），期间允许 session 完成当前 LLM 调用并写入 result
4. grace period 后仍存活的 session → SIGKILL
5. 持久化 worklist 中未消费的 tasks 到 xmuse/pending_tasks.json
6. Master 重启时从 pending_tasks.json 恢复队列
```

### 3.9 错误处理

| 场景 | 处理 |
|------|------|
| spawn 失败（进程启动失败） | 标记 FAILED，重试 1 次，仍失败则通知 Master |
| agent 返回 error 消息 | 记录到 memoryOS，标记 FAILED，Master 决定是否 rework |
| heartbeat 超时（5min 无 pong） | abort + 标记 TIMEOUT + 记录到 memoryOS |
| memoryOS API 不可达 | agent 继续执行（降级模式），session 结束时重试 ingest |
| stdout 非法 JSON 行 | 视为 debug output，记录到 session log 但不作为协议消息；连续 50 行非法 JSON 触发 health warning |
| agent 进程意外退出（非零 exit code） | 标记 FAILED，读取 stderr 作为 error message |

---

## 四、memoryOS Middleware

### 4.1 Middleware 能力

在现有 FastAPI 应用基础上添加三层 middleware：

```python
# src/memoryos_lite/middleware.py

class RequestIdMiddleware(BaseHTTPMiddleware):
    """注入 X-Request-Id header，贯穿整个请求链路。"""
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """X-API-Key header 校验。未配置 key 时跳过（开发模式）。"""
    async def dispatch(self, request, call_next):
        if not settings.api_key:
            return await call_next(request)
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)
        key = request.headers.get("X-API-Key")
        if key != settings.api_key:
            return JSONResponse(status_code=401, content={"detail": "invalid_api_key"})
        return await call_next(request)

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """JSON 结构化日志，包含 request_id、method、path、status、latency。"""
    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        logger.info("request", extra={
            "request_id": request.state.request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": (time.monotonic() - start) * 1000,
        })
        return response
```

Middleware 注册顺序（请求处理顺序，外 → 内）：
1. CORS（FastAPI 内建 `CORSMiddleware`）
2. RequestId
3. ApiKeyAuth
4. StructuredLogging

代码注册顺序（`app.add_middleware` 调用顺序，与请求处理相反）：
```python
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, ...)
```

### 4.2 新增配置项

```python
# src/memoryos_lite/config.py 新增字段
class Settings(BaseSettings):
    # Middleware
    api_key: str | None = None          # MEMORYOS_API_KEY, None = 跳过 auth
    cors_origins: list[str] = ["*"]     # MEMORYOS_CORS_ORIGINS
    log_format: Literal["json", "text"] = "text"  # MEMORYOS_LOG_FORMAT

    # Agent integration
    agent_session_id_prefix: str = "agent"  # agent session ID 前缀
```

默认行为保证：
- `api_key` 未设置 → auth middleware 跳过（开发模式兼容）
- `cors_origins = ["*"]` → 开发模式全放行
- `log_format = "text"` → 现有日志行为不变

### 4.3 Agent 集成端点

在现有 service contract 基础上，为 agent session 场景补充：

| Method | Path | 说明 |
|--------|------|------|
| POST | `/sessions` | 创建会话（已有） |
| POST | `/sessions/{id}/ingest` | 写入消息（已有） |
| POST | `/sessions/{id}/build-context` | 组装上下文（已有） |
| POST | `/memory/search` | 全局检索（已有） |
| POST | `/sessions/{id}/ingest-batch` | 批量写入（新增，agent 一次性提交多条） |
| GET | `/sessions/{id}/summary` | 会话摘要（新增，agent 快速获取 feature 概况） |

新增端点遵循现有错误契约（404/422/500/503）和 ID 生成规则。

### 4.4 memoryOS 作为 Agent 记忆层

**调用发起方**：SessionManager 负责所有 memoryOS API 调用，agent 自身不直接调用
memoryOS。这简化了 agent prompt（不需要注入 endpoint URL 和 API key），也确保
记忆写入的一致性。

集成协议：

```
Agent Session 启动:
  SessionManager 调用:
    POST /sessions  {"title": "feature:{feature_id}"}
    POST /sessions/{id}/build-context  {"task": task_description, "budget": 4096}
  SessionManager 将 build_context 结果作为 initial context 通过 stdin 传给 agent:
    {"type": "task", "feature_id": "...", "prompt": "...", "context": "<build_context result>"}

Agent Session 执行中:
  Agent 通过 stdout 上报关键决策:
    {"type": "progress", "stage": "decision", "message": "chose approach X because..."}
  SessionManager 收到 decision 类型 progress 后调用:
    POST /sessions/{id}/ingest  {"role": "assistant", "content": decision_record}

Agent Session 结束:
  SessionManager 调用:
    POST /sessions/{id}/ingest  {"role": "system", "content": final_result_summary}
```

Session 命名约定：`feature:{feature_id}` 前缀，便于按 feature 过滤和清理。

---

## 五、兼容性保证

### 5.1 不破坏的行为

| 组件 | 保证 |
|------|------|
| slave_job_runner.py | 继续工作，新 SessionManager 是并行替代而非替换 |
| hermes_hardening.py | gate 逻辑不变，review verdict 格式不变 |
| master_state.json | 继续作为 feature 状态源，SessionManager 读取但不修改其结构 |
| memoryOS 无 API key 模式 | auth middleware 自动跳过 |
| memoryOS v1 fallback | 不受 middleware 影响 |
| 现有 39 个 xmuse_core 测试 | 不修改现有接口 |

### 5.2 渐进式迁移

```
Phase 1: 新增 SessionManager + Launcher Adapters（与 slave_job_runner 并存）
Phase 2: 新 feature 使用 SessionManager 调度，旧 feature 继续用 slave_job_runner
Phase 3: 验证稳定后，slave_job_runner 标记 deprecated
```

---

## 六、模块结构

### 6.1 xmuse Agent Framework 新增模块

```
src/xmuse_core/
├── core/           # 已有：state, status, schema, paths
├── routing/        # 已有：worklist, mentions, callbacks, server
└── agents/         # 新增
    ├── __init__.py
    ├── registry.py         # AgentRegistry, AgentDescriptor
    ├── session.py          # AgentSession protocol, LocalSession, RemoteSession
    ├── manager.py          # SessionManager (lifecycle, heartbeat, abort)
    ├── consumer.py         # WorklistConsumer (main dispatch loop)
    └── launchers/
        ├── __init__.py
        ├── base.py         # LauncherAdapter protocol
        ├── codex.py        # CodexLauncher
        └── claude_code.py  # ClaudeCodeLauncher
```

### 6.2 memoryOS Middleware 新增模块

```
src/memoryos_lite/
├── middleware.py           # 新增：RequestId, ApiKeyAuth, StructuredLogging
├── config.py              # 修改：新增 api_key, cors_origins, log_format
├── api.py                 # 修改：注册 middleware + 新增端点
└── ...                    # 其他模块不变
```

---

## 七、通信协议格式

协议版本：`1.0`。每条消息一行 JSON（JSON-line 格式），以 `\n` 分隔。
单条消息最大 10MB，超过时 agent 应将大内容写入文件并传路径。

### 7.1 Session 握手

Session 启动后第一条交互为版本协商：

```json
Master → Agent: {"type": "hello", "protocol_version": "1.0", "feature_id": "archive-rag"}
Agent → Master: {"type": "hello_ack", "protocol_version": "1.0", "runtime": "codex"}
```

版本不匹配时 Master 立即 abort session。

### 7.2 stdin 消息格式（Master → Agent）

```json
{"type": "task", "feature_id": "archive-rag", "prompt": "...", "context": "..."}
{"type": "abort"}
{"type": "ping"}
```

### 7.3 stdout 消息格式（Agent → Master）

```json
{"type": "pong"}
{"type": "heartbeat", "ts": "2026-05-25T10:00:00Z", "context_usage": 0.45}
{"type": "progress", "stage": "executing", "message": "running tests..."}
{"type": "result", "status": "success", "artifacts": {"result_md": "...", "verdict": {...}}}
{"type": "error", "code": "timeout", "message": "LLM call timed out"}
```

### 7.4 stdout 解析容错

Agent 可能输出非 JSON 内容（stack trace、debug log 等）。处理规则：
- 非 JSON 行视为 debug output，记录到 session log 但不作为协议消息
- 连续 50 行非法 JSON 触发 health warning（可能 agent 进入异常状态）
- 不因非法 JSON 行 abort session（容忍 agent 的 stderr 混入 stdout）

---

## 八、测试策略

### 8.1 xmuse Agent Framework 测试

| 层级 | 覆盖 |
|------|------|
| Unit | Registry 加载/选择、Launcher command 构建、Session 状态机转换 |
| Integration | LocalSession stdin/stdout 往返、heartbeat 超时检测、abort 信号传播 |
| E2E | 完整 dispatch → session → result 流程（使用 mock agent process） |

### 8.2 memoryOS Middleware 测试

| 层级 | 覆盖 |
|------|------|
| Unit | RequestId 注入/传递、ApiKeyAuth 通过/拒绝/跳过、日志格式 |
| Integration | Middleware 链顺序正确、CORS preflight 响应 |
| 兼容性 | 无 API key 时所有现有端点行为不变 |

---

## 九、非目标

- 不实现 A2A 深度递归（留后续阶段）
- 不实现 RemoteSession / Streamable HTTP（预留接口，不实现）
- 不替换 hermes_hardening gate 逻辑
- 不修改 master_state.json 结构
- 不在本阶段移除 slave_job_runner.py
- 不实现 agent 自主决策（agent 仍是 master 调度的执行者）

---

## 十、开放风险

| 风险 | 缓解 |
|------|------|
| Codex CLI session 模式稳定性未验证 | Phase 1 先验证单 agent，稳定后扩展 |
| Claude Code stdin pipe 输出格式可能变化 | Launcher adapter 隔离解析逻辑，变化时只改 adapter |
| per-feature session 对极大 feature 可能 context 不足 | fallback: memoryOS.build_context() 恢复 + 新 session |
| 多 Master 实例同时启动的孤儿回收 race | active_sessions.json 记录 master_instance_id，只 kill 自己的 |
| Worklist async 适配可能影响现有同步测试 | 新增 async_consume() 方法，不修改现有 consume() 签名 |
| agent stdout 混入 stderr 导致解析异常 | 非 JSON 行容错处理，不 abort session |

