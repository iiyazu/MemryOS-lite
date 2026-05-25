# xmuse MVP Deployment Design

Version: 0.1.0 | Date: 2026-05-25

## 一、概述

将新实现的 session-based agent framework 集成为 xmuse 的运行入口，替代现有
god_launcher.sh + slave_job_runner.py，以单进程 asyncio 主循环在 tmux 中运行。

MVP 目标：xmuse 同时迭代 memoryOS 和自身，渐进式自主。

---

## 二、设计约束

| 约束 | 来源 |
|------|------|
| 全面切换新 agent framework | brainstorming 选择 |
| 仅 Codex CLI 作为 runtime | brainstorming 选择 |
| 渐进式自主（人类提需求 → 半自主 → 全自主） | brainstorming 选择 |
| tmux 手动启动 | brainstorming 选择 |
| memoryOS 作为知识层 | 前序设计确认 |
| 现有 50 个 agent framework 测试必须继续通过 | 项目约束 |

---

## 三、架构

```
tmux session "xmuse"
├── window "api": uv run memoryos api --port 8000
└── window "master": python xmuse_main.py --config xmuse/agents.json --lanes xmuse/feature_lanes.json

xmuse_main.py (asyncio)
├── load agents.json → AgentRegistry
├── load feature_lanes.json → enqueue TaskDescriptors
├── WorklistConsumer.run() (main loop)
│   └── SessionManager.dispatch()
│       ├── MemoryOSClient.build_context()
│       ├── CodexLauncher → codex exec (one-shot, stdin prompt)
│       └── MemoryOSClient.ingest(result)
├── Process timeout: 30min default → SIGTERM → SIGKILL
└── Signal handler: SIGTERM/SIGINT → graceful_shutdown()
```

---

## 四、新增组件

### 4.1 xmuse_main.py（主入口）

单文件入口，职责：
- 解析 CLI 参数（--config, --lanes, --memoryos-url）
- 初始化 AgentRegistry、SessionManager、WorklistConsumer
- 从 feature_lanes.json 加载初始任务并 enqueue
- 启动 asyncio event loop
- 注册 SIGTERM/SIGINT handler → graceful_shutdown
- 启动时一次性加载 feature_lanes.json（修改后需重启生效）

### 4.2 feature_lanes.json（任务源）

人类编写的任务队列，格式：

```json
{
  "lanes": [
    {
      "feature_id": "fix-recall-cache-bug",
      "task_type": "execute",
      "prompt": "Fix the recall cache returning stale results when...",
      "worktree": "/home/iiyatu/projects/python/memoryOS-fix-cache",
      "branch": "fix/recall-cache-bug",
      "capabilities": ["code", "test"]
    }
  ]
}
```

规则：
- 每个 lane 对应一个 feature，在独立 worktree 中执行
- xmuse_main 启动时读取，运行中可热加载
- 执行完成的 lane 标记 `"status": "done"`，不再重复执行

### 4.3 agents.json（agent 注册）

```json
{
  "agents": [
    {
      "runtime": "codex",
      "name": "codex-worker-1",
      "capabilities": ["code", "test", "review"],
      "session_config": {
        "transport": "local",
        "heartbeat_interval_s": 30
      }
    }
  ]
}
```

### 4.4 MemoryOSClient（HTTP 集成）

住在 `src/xmuse_core/agents/manager.py` 中，职责：
- `create_session(title)` → POST /sessions
- `build_context(session_id, task, budget)` → POST /sessions/{id}/build-context
- `ingest(session_id, role, content)` → POST /sessions/{id}/ingest
- 所有方法 catch httpx.HTTPError → log warning，不阻塞 agent 执行（降级模式）

配置通过 `--memoryos-url` 传入（默认 `http://127.0.0.1:8000`）。

### 4.5 Codex CLI 适配（one-shot 模式）

**关键事实**：Codex CLI 不支持 stdin/stdout 双向 JSON-line 协议。它是 TTY 应用，
`codex exec` 子命令支持从 stdin pipe 读取 prompt，但不实现 hello/pong 握手。

MVP 策略：**使用 `codex exec` one-shot 模式**，跳过 session 协议层。

```python
class CodexLauncher:
    def build_command(self, feature_id: str, worktree: Path) -> list[str]:
        return [
            "codex", "exec",
            "--approval-mode", "full-auto",
            "--cwd", str(worktree),
        ]
```

执行流程：
1. SessionManager spawn `codex exec` 进程
2. 通过 stdin 传入 formatted prompt（一次性写入后关闭 stdin）
3. 等待进程退出（timeout 由 SessionManager 管理）
4. 收集 stdout 作为执行日志
5. exit code 0 = success，非零 = failed

**不使用的协议层**（MVP 跳过，留给未来 Claude Code 等支持双向协议的 runtime）：
- hello/hello_ack 握手
- ping/pong heartbeat
- JSON-line stdout 解析

**超时检测**：不用 ping/pong，改为进程级 timeout（默认 30min）。
超时后 SIGTERM → grace 10s → SIGKILL。

### 4.6 Gate 逻辑（简化版）

MVP 阶段不使用完整的 hermes_hardening gate。简化为：
1. Agent 执行完成后，SessionManager 检查 exit code
2. 如果 agent 报告 `status: "success"` → 标记 lane 为 done
3. 如果 agent 报告 `status: "error"` → 标记 lane 为 failed，记录 error
4. 人类手动检查 worktree 中的变更，决定是否 merge

未来升级：加入自动 test gate（`uv run pytest`）和 lint gate（`uv run ruff check`）。

---

## 五、自迭代闭环设计

### Phase 1：人类驱动（MVP 启动即可用）

```
人类编辑 feature_lanes.json
  → xmuse_main 检测到新 lane
  → enqueue TaskDescriptor
  → WorklistConsumer dispatch
  → Codex agent 在 worktree 中执行
  → 结果写入 memoryOS
  → 人类审查 worktree diff → git merge
```

### Phase 2：半自主（MVP 稳定后开启）

新增 `xmuse/auto_discovery.py`：
- 定期运行 `uv run pytest` → 解析失败 → 自动生成 fix lane
- 定期运行 `uv run ruff check` → 解析 error → 自动生成 lint lane
- 读取 memoryOS eval 结果 → 发现 regression → 自动生成 investigation lane
- 自动生成的 lane 标记 `"source": "auto"`，人类可以 reject

### Phase 3：全自主（远期）

- xmuse 自主分析 git log、issue tracker、error log
- 自主 prioritize 和 plan
- 自主 execute + self-review（跨 runtime review 启用后）
- 人类只做 merge 审批

---

## 六、文件结构

```
xmuse/
├── xmuse_main.py           # 新增：主入口
├── agents.json             # 新增：agent 注册配置
├── feature_lanes.json      # 新增：任务队列（人类编辑）
├── auto_discovery.py       # Phase 2：自动发现问题
├── god_launcher.sh         # 保留但不再使用（参考）
├── slave_job_runner.py     # 保留但不再使用（参考）
└── hermes_hardening.py     # 保留，gate 逻辑未来可复用
```

---

## 七、部署操作手册

### 7.1 前置条件

- Codex CLI 已安装且 authenticated
- memoryOS 依赖已安装（`uv sync`）
- 至少一个 feature worktree 已创建

### 7.2 启动步骤

```bash
# 1. 创建 tmux session
tmux new-session -d -s xmuse -n api

# 2. 启动 memoryOS API（window 0）
tmux send-keys -t xmuse:api "cd /home/iiyatu/projects/python/memoryOS && uv run memoryos api --port 8000" Enter

# 3. 创建 master window
tmux new-window -t xmuse -n master

# 4. 启动 xmuse master loop（window 1）
tmux send-keys -t xmuse:master "cd /home/iiyatu/projects/python/memoryOS && python xmuse/xmuse_main.py" Enter

# 5. 连接到 session
tmux attach -t xmuse
```

### 7.3 提交新任务

编辑 `xmuse/feature_lanes.json`，添加新 lane：
```json
{
  "feature_id": "my-new-feature",
  "task_type": "execute",
  "prompt": "Implement X by doing Y...",
  "worktree": "/path/to/worktree",
  "branch": "feat/my-new-feature",
  "capabilities": ["code", "test"]
}
```

xmuse_main 会在下一个 poll cycle（5s）检测到变化并 enqueue。

### 7.4 停止

```bash
# Graceful shutdown
tmux send-keys -t xmuse:master C-c
# 或发送 SIGTERM
kill -TERM $(cat xmuse/active_sessions.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('master_pid',''))")
```

---

## 八、非目标

- 不实现 Claude Code runtime（留后续）
- 不实现跨 runtime review（留后续）
- 不实现 RemoteSession / Streamable HTTP
- 不实现 Web UI / dashboard
- 不实现自动 merge（人类始终审批）
- 不修改现有 hermes_hardening.py

---

## 九、风险

| 风险 | 缓解 |
|------|------|
| Codex CLI 不支持 stdin session 模式 | fallback 到 one-shot wrapper |
| memoryOS API 不可用时 agent 卡住 | 降级模式：跳过 build_context，继续执行 |
| feature_lanes.json 格式错误 | 启动时 schema 校验，错误 lane 跳过并 log |
| agent 执行超时（Codex idle timeout） | heartbeat 检测 + 5min timeout → abort |
| worktree 不存在或有冲突 | dispatch 前检查 worktree 状态，blocked 则跳过 |