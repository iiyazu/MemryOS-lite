# xmuse 项目交接文档

更新日期: 2026-05-28
仓库路径: `/home/iiyatu/projects/python/memoryOS`
分支: `feat/phase-2.5-3-retrieval-agent`
运行环境: WSL2/Linux。涉及 Codex 历史记录时，优先看 WSL 侧记录，不要默认去 Windows/Open Design 前端目录找。

## 当前定位

xmuse 是在 MemoryOS 仓库内演进的自主软件开发平台原型。目标架构是：

1. 人类在前端聊天主界面中与多个长驻 CLI GOD 会话讨论需求。
2. 多个 GOD 通过 MCP、router、inbox 等基础设施对等交流。
3. 讨论结果经审议后结构化为 `Resolution -> LaneGraph -> lanes`。
4. Execute GOD 负责一批 lane 的图级调度，根据依赖并发派发 `codex exec`/类似 one-shot worker 子进程。
5. Review GOD 是长驻的非执行审计者，消费正式 ReviewVerdict artifact，决定 merge、rework、patch-forward 或 terminate。
6. 判断门可配置 human-in-the-loop。聊天是主展示面，执行状态和审计默认在单独 dashboard 面查看。

当前实现仍处于迁移期：MVP 主线已经打通到 chat-to-lane 和 one-shot worker 执行面；session-first GOD 层 Phase 1 已建立地基，但还没有替代现有 one-shot 编排。

## 主要设计文档

| 路径 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-05-28-xmuse-god-session-first-architecture-design.md` | session-first GOD 目标架构 |
| `docs/superpowers/plans/2026-05-28-xmuse-god-session-layer-phase-1.md` | Phase 1 实施计划 |
| `docs/superpowers/specs/2026-05-27-xmuse-architecture-blueprint-design.md` | xmuse 全景蓝图 |
| `docs/superpowers/specs/2026-05-27-xmuse-mvp-chat-to-lane-design.md` | chat-to-lane MVP 主线 |
| `docs/superpowers/specs/2026-05-28-xmuse-blueprint-anchored-self-evolution-design.md` | 自迭代蓝图锚定设计 |

## 当前主线

```text
前端 /chat
  -> xmuse/chat_api.py
  -> src/xmuse_core/chat/store.py
  -> StructuredResolution
  -> src/xmuse_core/structuring/planner.py
  -> LaneGraph snapshots in xmuse/lane_graphs/
  -> src/xmuse_core/structuring/projection.py
  -> xmuse/feature_lanes.json
  -> xmuse/platform_runner.py
  -> src/xmuse_core/platform/orchestrator.py
  -> one-shot lane workers via AgentSpawner
  -> gate / review / final action
  -> xmuse/dashboard_api.py
```

`master_loop` 当前保留为 review gate、rework、auto-merge 等经验参考源；MVP 主执行面是 chat-to-lane -> platform runner/orchestrator 路径。

## Phase 1 已完成内容

最近完成并提交的 session-first Phase 1 地基：

| 能力 | 文件 | 状态 |
|---|---|---|
| 混跑期状态归一化 | `src/xmuse_core/platform/state_normalizer.py` | 已有 `normalize_lane_state()` / `summarize_lane_states()` |
| 稳定 GOD 身份注册表 | `src/xmuse_core/agents/god_session_registry.py` | `god_session_id`、address、inbox、atomic write、sidecar lock |
| 长驻 GOD session layer | `src/xmuse_core/agents/god_session_layer.py` | async interface，按 role 复用 live session，dead session 可用同一 `god_session_id` respawn |
| Session router | `src/xmuse_core/routing/session_router.py` | 通过 `session_address` 投递到 inbox，inbox append 使用 lock + atomic replace |
| Dashboard 混跑兼容 | `xmuse/dashboard_api.py` | `/api/lanes` 暴露 `effective_status`；`/api/metrics` 使用状态归一化；`/api/sessions` 支持 GOD registry 形态 |

最近相关提交：

```text
c242eea feat: normalize xmuse dashboard state reads
4f11408 fix: harden xmuse session router inbox writes
676a616 feat: add xmuse session router
54862fe fix: reuse respawned xmuse god sessions
ed4ca35 fix: tighten xmuse god session layer reuse
3b864a8 fix: make xmuse god session layer async
28b255f feat: add xmuse god session layer
bd0b667 fix: lock god session registry writes
b4ec7bd fix: harden god session registry
7339722 fix: prefix god session ids
32aa77e feat: add god session registry
```

## 当前运行语义

### GOD 与 worker 的语义边界

目标语义下，GOD 是长驻 CLI 会话，不是“做完一个 lane 就退出”的短进程。

当前实现里仍然有旧路径：

- `src/xmuse_core/platform/agent_spawner.py` 负责启动 one-shot lane worker。
- `src/xmuse_core/platform/orchestrator.py` 仍按单 lane 推进状态机。
- `GodSessionLayer` 和 `SessionRouter` 是新地基，还没有成为执行主路径。

因此目前应这样理解：

- `AgentSpawner` = lane worker launcher，不是 GOD 本体。
- `PlatformOrchestrator` = 迁移期 execution run controller，未来应演进为图级 scheduler。
- `Review GOD` 目标上应是长驻审计会话；当前 runtime 仍有短进程/metadata 兼容痕迹。

### Lane 状态

当前 legacy 状态机仍存在：

```text
pending -> dispatched -> executed -> gated -> reviewed -> awaiting_final_action | merged | failed
rejected -> reworking -> dispatched
exec_failed / gate_failed / failed
```

混跑期 dashboard 和新 consumer 应通过 `state_normalizer` 解读：

| Legacy/raw | Effective |
|---|---|
| `pending` | `ready` |
| `gated` | `under_review` |
| `rejected`, `reworking` | `requeued` |
| `merged`, legacy `done`, `completed` | `merged` |
| `failed` without structured reason | `terminated` |
| `exec_failed`, `gate_failed` | same |

Dashboard `/api/lanes` 同时返回 raw `status` 和 `effective_status`。UI 语义优先使用 `effective_status`。

## 当前数据状态

截至本次更新，本地数据大致为：

- `xmuse/feature_lanes.json`: 109 lanes
  - `done`: 79
  - `merged`: 25
  - `failed`: 3
  - `exec_failed`: 1
  - `dispatched`: 1
- `xmuse/lane_graphs/`: 29 graph snapshot 文件
- `xmuse/chat.db`: chat-plane SQLite 数据库存在
- `xmuse/final_actions.json`: final-action hold 数据存在
- `xmuse/self_evolution/`: self-evolution read-model 数据目录存在
- `xmuse/history/recovered_codex_sessions_2026-05-28.json`
- `xmuse/history/recovered_codex_sessions_2026-05-28.md`

注意：`feature_lanes.json` 不是 authoritative graph，只是当前执行队列/投影文件。authoritative graph 在 `xmuse/lane_graphs/` 快照里，但图级运行态还没完全接管调度。

## Dashboard / API

| 服务 | 文件 | 默认端口 | 说明 |
|---|---|---:|---|
| MCP server | `xmuse/mcp_server.py` | 8100 | JSON-RPC 2.0 over `/mcp`，SSE endpoint `/sse` |
| Dashboard API | `xmuse/dashboard_api.py` | 8200 | lanes, sessions, metrics, resolutions, verdicts, self-evolution read models |
| Chat API | `xmuse/chat_api.py` | 8201 | conversations, messages, proposals, structured resolutions |

Dashboard API 现在包含：

- `GET /api/lanes`
- `GET /api/lanes/{feature_id}`
- `POST /api/lanes`
- `POST /api/lanes/{feature_id}/approve`
- `POST /api/lanes/{feature_id}/reject`
- `GET /api/sessions`
- `GET /api/errors`
- `GET /api/resolutions`
- `GET /api/verdicts`
- `GET /api/self-evolution`
- `GET /api/metrics`

`/api/sessions` 兼容三种形态：

- legacy list
- MCP dict keyed by `feature_id`
- GOD registry list with `god_session_id`, `role`, `session_address`, `session_inbox_id`, `status`, `pid`

## 前端

当前用户提供的初版前端位置在 Windows 侧：

```text
C:\Users\iiyatu\AppData\Roaming\Open Design\namespaces\release-stable-win\data\projects\2e36b78c-feca-4c9e-94d2-de7a84be2ebc\frontend
```

设计方向：

- `/chat` 是主展示面，展示人类与多个 GOD 的群聊流。
- execution 状态、audit、metrics 默认在独立 dashboard 面展示，不塞进聊天主流。
- 美学设计尽量延续当前 Open Design 前端。

曾出现过 Next.js dev 运行错误：

```text
Error: Cannot find module './948.js'
Require stack: ... frontend/.next/server/webpack-runtime.js
```

优先处理方式通常是清理 `.next` 后重启 dev server；但如果继续前端工作，先检查 Windows 侧前端真实目录，不要误操作 WSL 仓库内旧的 `xmuse/frontend*` 删除/迁移痕迹。

## 启动命令

```bash
cd /home/iiyatu/projects/python/memoryOS

# MCP server
uv run python xmuse/mcp_server.py

# Dashboard API
uv run python xmuse/dashboard_api.py

# Chat API
uv run python xmuse/chat_api.py

# Platform runner
uv run python xmuse/platform_runner.py --max-hours 8 --max-concurrent 4
```

Windows 侧前端：

```powershell
cd C:\Users\iiyatu\AppData\Roaming\Open Design\namespaces\release-stable-win\data\projects\2e36b78c-feca-4c9e-94d2-de7a84be2ebc\frontend
npm run dev
```

## 验证记录

最近完成的 xmuse Phase 1 验证：

```bash
uv run pytest tests/test_xmuse_dashboard_api.py -q
# 19 passed
```

```bash
uv run pytest \
  tests/test_xmuse_state_normalizer.py \
  tests/test_xmuse_god_session_registry.py \
  tests/test_xmuse_god_session_layer.py \
  tests/test_xmuse_session_router.py \
  tests/test_xmuse_dashboard_api.py \
  tests/test_xmuse_core_agents_manager.py -q
# 55 passed
```

```bash
uv run pytest \
  tests/test_xmuse_chat_api.py \
  tests/test_xmuse_mvp_e2e_chat_to_lane.py \
  tests/test_xmuse_platform_orchestrator.py \
  tests/test_xmuse_platform_runner.py \
  tests/test_xmuse_mcp_server.py -q
# 24 passed
```

没有在本轮跑完整仓库 `uv run pytest -q`。

## 当前工作树注意事项

当前工作树存在大量未提交/未跟踪文件，且很多不是本次 HANDOFF 更新产生的。不要用 `git reset --hard`、`git checkout --` 或批量删除来“清理”。

已观察到的类别包括：

- 多份 xmuse spec/plan 文档改动
- `src/memoryos_lite/*` 相关改动
- `src/xmuse_core/platform/*`、`agents/*`、`gates/*` 改动
- `src/xmuse_core/chat/`、`structuring/`、`self_evolution/`、`skills/` 等未跟踪模块
- `xmuse/frontend*` 目录删除痕迹
- `xmuse/lane_graphs/`、`xmuse/self_evolution/`、`xmuse/history/`、`xmuse/logs/` 等运行数据

如果需要提交，务必只 stage 当前任务明确涉及的文件。

## WSL 侧 Codex 记录

用户明确要求查 Codex 记录时看 WSL 侧。当前可用记录：

```text
xmuse/history/recovered_codex_sessions_2026-05-28.json
xmuse/history/recovered_codex_sessions_2026-05-28.md
```

也可检查 `$CODEX_HOME` / `~/.codex` 下的 WSL 侧配置和会话材料。不要把 Windows/Open Design 前端目录当作 Codex 历史记录来源。

## 未完成能力

以下是当前尚未闭环的能力事实，供接手者理解系统边界：

1. GOD session layer 尚未接入主执行路径。现在只是可创建、复用、寻址、投递的地基。
2. Execute GOD 还不是“批量 lane 图级 scheduler”。当前仍是 `platform_runner + orchestrator` 对 flat queue/单 lane 调度。
3. ReviewVerdict 产出侧还没有完全变成 authoritative artifact stream；部分 runtime 仍依赖 metadata/兼容桥。
4. Patch-forward lineage 还没有完全回写 LaneGraph authoritative store。
5. ClarificationRequest / blocked_for_input 这类“信息不足打回”对象还没落地。
6. Dashboard 读模型还不是完整审计面，graph/run/review/final-action/patch-forward chain 需要统一投影。
7. 前端聊天流还没有接入真实长驻 GOD 群聊输出。
8. `master_loop` 仍有历史能力；当前 MVP 主线没有接回 `master_loop`。
