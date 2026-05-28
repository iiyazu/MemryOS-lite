# xmuse 蓝图探讨记录（Session 3）

> Date: 2026-05-29
> 参与者: 人 + claude (opus)
> 状态: 决策已锁定，待实施

## 总体规划

四阶段演进路线（按优先级排序）：

| 阶段 | 主题 | 状态 | 依赖 |
|---|---|---|---|
| C | 系统解耦/模块化 | spec 已写，Steps 1-3 实施中 | 无 |
| A | A2A 消息契约 | 决策已锁定 | C 完成后挂接口 |
| D | 前端方案 | 搁置，API 契约已有 | — |
| B | A2A 协议完善 | 决策已锁定，分 B1-B4 | A 完成后 |

## C 阶段：解耦/模块化

- **方案**: 极简门面（orchestrator/controller 只做装配+路由）
- **目标文件**: orchestrator.py (1457行) + controller.py (100k)
- **拆分边界**: platform/{execution,selection,prompts,projection,verdicts}/ + self_evolution/{proposal,budget,evidence,clarification,adapters}/
- **测试策略**: 门面集成测试 + 强制单测（review fallback / god_picker / reproject_dependents）
- **迁移路径**: 7 步串行 PR，每步独立可发布
- **今晚交付**: spec + Steps 1-3 手做 + Steps 4-7 注入 xmuse
- **Spec**: `docs/superpowers/specs/2026-05-29-orchestrator-controller-decoupling-design.md`

## A 阶段：A2A 消息契约

| 决策点 | 结论 |
|---|---|
| 消息线 | 1+2+3（architect→execute / execute→review / review→execute rework） |
| 序列化 | JSON |
| 传输通道 | 分层：短命 SubprocessTransport / 长命 MCPTransport |
| 触发模式 | Pull（orchestrator 唯一触发者） |
| Request 边界 | Fully-resolved（Transport 是 dumb pipe） |

接口已在 C spec Section 6 定义（ExecuteRequest/Response/ReviewRequest/ReviewVerdict + Transport Protocol）。

## B 阶段：A2A 协议完善（分 4 子阶段）

依赖链：B1 → B2 → B3 → B4

### B1: GodManifest + 能力注册

```python
@dataclass(frozen=True)
class GodManifest:
    name: str                          # "execute-codex", "review-claude"
    runtime: str                       # "codex" | "claude"
    capabilities: list[str]            # ["execute", "review", "brainstorm", "gate"]
    supported_request_versions: dict[str, int]  # {"ExecuteRequest": 2, "ReviewRequest": 1}
    max_concurrency: int
    health_endpoint: str | None
```

注册方式：短命 god 从 `xmuse/god_manifests/*.json` 加载；长命 god 连接后 push manifest。

### B2: schema 版本协商

策略：additive-only 字段裁剪。v2 Request 发给只支持 v1 的 god 时 strip 新增字段。破坏性变更 = 新 major version，不降级，直接 fail。

### B3: 死信队列

SQLite `dead_letters` 表。MCP tool `get_dead_letters` / `replay_dead_letter`。orchestrator 不再自己做 retry——只关心"成功 or 进了 DLQ"。

### B4: 多 god 协作

- **vote 模式**: per-lane `vote_policy`（majority / unanimous / weighted），默认 majority
- **peer 模式**: 单轮（A 出方案 → B 评审 → approve 或 A 修改后直接提交）

## D 阶段：前端

搁置。API 契约已有：`xmuse/FRONTEND_API.md` + `xmuse/FRONTEND_API_INCREMENTAL.md` + `xmuse/FRONTEND_VISION.md`。

技术选型倾向 Tauri + React（待后续确认）。

## 运行时配置（本次 session 变更）

| 环境变量 | 用途 | 当前值 |
|---|---|---|
| `XMUSE_GOD_RUNTIME` | GOD execute/review 的 CLI | `codex` |
| `XMUSE_CODEX_MODEL` | GOD codex 模型 | `gpt-5.5` |
| `XMUSE_NON_GOD_CODEX_MODEL` | 非 GOD codex 调用模型 | `gpt-5.4` |
| `XMUSE_PEER_CHAT_RUNTIME` | peer-chat decomposer CLI | `codex` |
| `XMUSE_CHAT_DRIVER_RUNTIME` | chat-driver CLI | `codex` |
| `XMUSE_CLAUDE_MODEL` | Claude GOD 模型（当 claude 可用时） | `sonnet` |

代码变更：`peer_chat_decomposer.py` + `chat/driver.py` 新增 runtime 分发（codex/claude），支持 env 切换。

## 健康监控策略

- 每 60s 检查 `claude --version` / `codex --version` 可达性
- 15 分钟窗口内 lane 失败率 ≥4 且成功=0 → 触发 swap
- 当前状态：codex-only（CC API 暂不可用），等人工通知切回

