# Orchestrator + Controller 解耦设计

> Date: 2026-05-29
> Status: design (approved via brainstorming session)
> Author: 自迭代节奏会议（人 + claude）
> Scope: `src/xmuse_core/platform/orchestrator.py` (1457 行) + `src/xmuse_core/self_evolution/controller.py` (100k 行)

## 1. 问题陈述

xmuse 控制平面的两个核心文件已经超过单文件可读阈值：

| 文件 | 行数 | 职责数量 | 测试痛点 |
|---|---|---|---|
| `platform/orchestrator.py` | 1457 | 6 大类（dispatch / execute / review / gate / merge / project） | review-rework 路径已多次踩坑（fallback 解析、retry 决策、超时恢复） |
| `self_evolution/controller.py` | 100k 字节 | 8 大类（aggregate / evidence / propose / review / guardrail / land / clarification / budget） | 50+ 私有 helper，单测必须 mock 全套 store 与 IO |

直接症状：

- 当前 review-rework 死循环（fe-vision2-layer1 review_recovered_from=review_timeout, retry=2）就发生在 orchestrator 的 `_run_review_god` + `_review_fallback_*` 调用链里。要修必须改类内方法，但类已 50+ 私有方法，副作用难评估。
- controller 直接读 `feature_lanes.json` + `chat.db`，无适配层；任何 store schema 变动都要在 controller 内多处修改。
- A2A 阶段（god ↔ god 消息契约规范化）的接口层无处挂载，因为 spawn / message / response 都嵌在 orchestrator 私有方法里。

## 2. 目标

P0（今晚必达）：

- 写出本 spec 并 commit。
- 落地"迁移路径"前 3 步：`prompts/builders.py`、`selection/god_picker.py`、`verdicts/writer.py`。每步独立 commit + 测试通过。
- 以 chat→proposal→lanes 的方式把第 4-7 步注入 xmuse 自迭代队列，让 xmuse 在监控下完成剩余拆分。

P1（自迭代或下一轮）：

- 完成 orchestrator → 门面 + execution.py / projection / 各子模块 的迁移。
- 完成 controller → 门面 + drafter/reviewer/budget/aggregator/clarification/adapters 的迁移。
- 删除 orchestrator/controller 内已委托的旧方法。

非目标：

- 不重写状态机（state_machine.py 维持现状）。
- 不引入完整事件驱动重构（C 选项已被否决）。
- 不动 `xmuse/hermes_hardening.py` / `xmuse/master_loop.py`（僵尸代码评估留给下一轮）。

## 3. 设计原则（覆盖整个迁移）

1. **门面 = 装配 + 路由**：`PlatformOrchestrator` / `SelfEvolutionController` 类只做依赖注入 + 事件路由 + 委托。新代码不再向门面类新增私有方法。
2. **子模块 = 纯函数 + 数据类**：除非有不可避免的状态（cursor / cache），子模块以模块级函数提供能力；状态走显式参数。
3. **每个 IO 端口只能有一个适配器**：`feature_lanes.json` 只能由 `LanesReader` 读，`chat.db` 只能由 `ChatReader` 读。任何其他模块必须经它们走。
4. **改一个文件 = 改一个职责**：每个新文件 ≤ 500 行；超过就再拆。
5. **A2A 接口先于实现**：消息 dataclass + Transport 抽象今晚定型，今晚只实现 SubprocessTransport，但 A 阶段加 MCPTransport / SSETransport / WebSocketTransport 不改 executor。

## 4. 子模块边界（platform/）

### 4.1 `platform/orchestrator.py`（门面，目标 ~300 行）

```python
class PlatformOrchestrator:
    def __init__(self, *, lanes_path, xmuse_root, mcp_port, runtime, ...)
    async def reconcile_status_changes() -> None
    async def dispatch_lane(lane_id: str) -> None
    async def on_lane_reviewed(lane_id: str) -> None
    async def on_lane_rejected(lane_id: str) -> None
```

规则：**不允许新增私有方法**。所有逻辑委托给下列子模块。

### 4.2 `platform/execution/executor.py`

```python
async def run_execution_god(
    *, lane: dict, god_picker: GodPicker, transport: Transport,
    recovery: RecoveryManager, prompt_builder: Callable, sm: LaneStateMachine,
) -> ExecuteResponse

def is_spawn_transient(exc: BaseException) -> bool
def spawn_result_transient(result: SpawnResult) -> bool
```

### 4.3 `platform/execution/review.py`

```python
async def run_review_god(
    *, lane: dict, god_picker: GodPicker, transport: Transport,
    recovery: RecoveryManager, sm: LaneStateMachine,
) -> ReviewVerdict

def infer_review_fallback(stdout: str) -> tuple[str, str, str]
def review_infra_failure_reason(result: SpawnResult) -> str | None
def review_fallback_rework_reason(stdout: str) -> str | None
def review_fallback_positive_reason(stdout: str) -> str | None
```

### 4.4 `platform/execution/gate.py`

```python
async def run_gate(*, lane: dict, gate_runner: GateRunner, sm: LaneStateMachine) -> bool
def get_changed_paths(worktree: Path) -> list[str]
```

### 4.5 `platform/execution/merger.py`

```python
async def auto_merge(
    *, lane: dict, worktree: Path, sm: LaneStateMachine, verdict_store: VerdictStore,
) -> bool
```

### 4.6 `platform/selection/god_picker.py`

```python
class GodPicker:
    def __init__(self, *, runtime_mode: str, execution_gods: list[GodConfig], review_gods: list[GodConfig])
    def pick_execution(self, lane_id: str) -> GodConfig
    def pick_review(self, lane_id: str) -> GodConfig
    @property
    def runtime_mode(self) -> str
```

mixed 模式的 round-robin cursor 在此类内部维护。

### 4.7 `platform/prompts/builders.py`

```python
def build_execution_prompt(lane: dict) -> str
def build_review_prompt(lane: dict) -> str
def build_review_verdict(lane: dict) -> ReviewVerdict  # ReviewVerdict from platform/messages.py
```

纯函数，无 IO。`ReviewVerdict` 统一定义在 `platform/messages.py`，builders 和 Transport 共享同一个类。

### 4.8 `platform/projection/dependents.py`

```python
async def reproject_dependents_if_needed(
    lane_id: str, *, sm: LaneStateMachine, graph_store: LaneGraphStore,
) -> None

def aggregate_status(lanes: list[dict], graph_id: str) -> AggregatedStatus
```

### 4.9 `platform/verdicts/writer.py`

```python
def stable_verdict_id_for_lane(lane_id: str) -> str
def ingest_merge_verdict(lane_id: str, summary: str, *, store: VerdictStore) -> None
def ingest_rework_verdict(lane_id: str, summary: str, *, store: VerdictStore) -> None
def gate_report_ref_for_lane(lane_id: str, *, store: VerdictStore) -> str | None
```

## 5. 子模块边界（self_evolution/）

### 5.1 `self_evolution/controller.py`（门面，目标 ~400 行）

```python
class SelfEvolutionController:
    def __init__(self, *, store, lanes_reader, chat_reader, decomposer, budget, ...)
    def aggregate_run_terminal(graph_id: str) -> RunTerminalAggregation
    def build_evidence_bundle(...) -> StructuredEvidenceBundle
    def draft_evolution_proposal(...) -> EvolutionProposal
    def review_proposal(...) -> ReviewVerdict
    def guardrail_check(...) -> GuardrailReport
    def land_evolution_run(...) -> EvolutionLineageRecord
    def record_clarification_request(...) -> ClarificationRequest
    def resolve_clarification(...) -> ClarificationResolution
    def expire_clarification(...) -> ClarificationRequest
```

规则：所有方法体 ≤ 5 行，纯委托。

### 5.2 `self_evolution/proposal/drafter.py`

```python
def draft(
    *, evidence: StructuredEvidenceBundle, target_track: str,
    decomposer: TrackDecomposer, store: SelfEvolutionStore,
) -> EvolutionProposal

def dedup_signal_refs(refs: list[str]) -> list[str]
def has_duplicate_evolution(proposal: EvolutionProposal, *, store: SelfEvolutionStore) -> bool
```

### 5.3 `self_evolution/proposal/reviewer.py`

```python
def review(proposal: EvolutionProposal, *, store: SelfEvolutionStore) -> ReviewVerdict
def guardrail_check(proposal: EvolutionProposal, *, store: SelfEvolutionStore) -> GuardrailReport
def land(proposal: EvolutionProposal, *, store: SelfEvolutionStore, lanes_reader: LanesReader) -> EvolutionLineageRecord
```

### 5.4 `self_evolution/budget/window.py`

```python
class BudgetWindow:
    def __init__(self, *, store: SelfEvolutionStore)
    def for_track(self, track: str) -> EvolutionBudgetWindow
    def consume(self, window_id: str, lanes_count: int) -> EvolutionBudgetWindow
    def get(self, window_id: str) -> EvolutionBudgetWindow
```

### 5.5 `self_evolution/evidence/aggregator.py`

```python
def aggregate_run_terminal(graph_id: str, *, lanes_reader: LanesReader) -> RunTerminalAggregation
def build_evidence_bundle(
    *, aggregation: RunTerminalAggregation, store: SelfEvolutionStore,
) -> StructuredEvidenceBundle
```

### 5.6 `self_evolution/clarification/lifecycle.py`

```python
def record(request: ClarificationInput, *, store: SelfEvolutionStore) -> ClarificationRequest
def resolve(id: str, resolution: str, *, store: SelfEvolutionStore) -> ClarificationResolution
def expire(id: str, *, store: SelfEvolutionStore) -> ClarificationRequest
def resume_lanes(graph_id: str, *, lanes_reader: LanesReader) -> list[str]
```

### 5.7 `self_evolution/adapters/lanes_reader.py`

唯一 `feature_lanes.json` 入口。

```python
class LanesReader:
    def __init__(self, lanes_path: Path)
    def list_lanes(self, *, status: str | None = None) -> list[dict]
    def get_lane(self, lane_id: str) -> dict | None
    def lineage_lane_ids(self, graph_id: str) -> list[str]
    def open_lineages(self, lane_by_id: dict) -> list[dict]
    def blocked_object_for_lane(self, lane: dict) -> dict | None
    def final_action_hold_for_lane(self, lane: dict) -> dict | None
```

### 5.8 `self_evolution/adapters/chat_reader.py`

唯一 `chat.db` 入口。

```python
class ChatReader:
    def __init__(self, db_path: Path)
    def get_resolution(self, id: str) -> Resolution
    def get_proposal(self, id: str) -> Proposal
    def list_conversations(self) -> list[Conversation]
```

## 6. 消息契约（为 A2A 阶段铺路）

### 6.1 消息 dataclass（`platform/messages.py`）

```python
@dataclass(frozen=True)
class ExecuteRequest:
    lane_id: str
    prompt: str
    worktree: Path
    capabilities: list[str]
    god_config: GodConfig
    mcp_url: str | None
    env_overrides: dict[str, str]

@dataclass(frozen=True)
class ExecuteResponse:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    transport_error: str | None = None

@dataclass(frozen=True)
class ReviewRequest:
    lane_id: str
    prompt: str
    worktree: Path
    evidence_refs: list[str]
    god_config: GodConfig
    mcp_url: str | None

@dataclass(frozen=True)
class ReviewVerdict:
    passed: bool
    verdict: str
    feedback: str
    raw_output: str
```

### 6.2 Transport 协议

```python
class Transport(Protocol):
    async def send_execute(self, req: ExecuteRequest) -> ExecuteResponse: ...
    async def send_review(self, req: ReviewRequest) -> ReviewVerdict: ...
```

### 6.3 `SubprocessTransport`（今晚唯一实现）

包装现有 `AgentSpawner`。根据 `god_config.runtime` 决定调用 `codex exec` 或 `claude -p`。Request 是 fully-resolved 的，Transport 只做"发出去、收回来"。

### 6.4 A 阶段扩展点

A 阶段新增 `MCPTransport`（长命 god session 走 MCP tool call / SSE）。executor / review 模块零改动——只在门面 `__init__` 里注入不同 Transport 实例。

序列化格式：**JSON**。传输通道分层：短命 god 走 SubprocessTransport（stdin/stdout），长命 god 走 MCPTransport（SSE）。触发模式：**Pull**（orchestrator 唯一触发者）。

## 7. 测试策略

### 7.1 现有集成测试保留

- `tests/test_xmuse_platform_orchestrator.py` — 端到端状态机流转（dispatch → executed → reviewed → merged）。迁移期间每步 commit 后必须 green。
- `tests/test_xmuse_platform_state_machine.py` — 状态机本身不动，测试不变。
- controller 侧等效集成测试同理保留。

### 7.2 强制新增单测（历史 bug 来源）

| 文件 | 覆盖目标 | 理由 |
|---|---|---|
| `tests/test_platform_review_fallback.py` | `review.infer_review_fallback` / `review_fallback_rework_reason` / `review_fallback_positive_reason` / `review_infra_failure_reason` | review-rework 死循环的直接原因是 fallback 解析逻辑误判 |
| `tests/test_platform_god_picker.py` | `GodPicker.pick_execution` / `pick_review` 在 mixed / codex / claude 三种 runtime 下的行为；round-robin cursor 推进 | 最近 mixed 模式刚改过，且 health-swap 依赖它 |
| `tests/test_platform_projection_dependents.py` | `reproject_dependents_if_needed` 对 feature_group=None / 多未合并依赖 / 已合并依赖 的处理 | feature_group=None 已经吃过亏导致 lane 永远 blocked |

### 7.3 其他子模块测试策略

- `prompts/builders.py`：纯函数，加 3-5 个 snapshot 测试即可。
- `verdicts/writer.py`：纯 store 写入，加 2-3 个 round-trip 测试。
- `execution/executor.py` / `execution/merger.py`：通过现有集成测试覆盖；单独单测可选。
- `self_evolution/adapters/*`：加 fixture-based 单测（用 tmp_path 写 json / sqlite）。

### 7.4 覆盖率目标

每个新纯函数模块 ≥ 80% 行覆盖。集成测试套件在整个迁移期间保持 green。

## 8. 迁移路径

### 8.1 Step 1: `platform/prompts/builders.py`

- **新建**: `src/xmuse_core/platform/prompts/__init__.py`, `src/xmuse_core/platform/prompts/builders.py`
- **修改**: `orchestrator.py`（删除 `_build_execution_prompt` / `_build_review_prompt` / `_build_review_verdict`，改为 import 委托）
- **测试**: `tests/test_platform_prompt_builders.py`（3-5 个 snapshot 测试）
- **Diff 规模**: <300 行
- **验证门**: `pytest tests/test_platform_prompt_builders.py tests/test_xmuse_platform_orchestrator.py -q` 全绿
- **PR title**: `refactor(platform): extract prompt builders to submodule`

### 8.2 Step 2: `platform/selection/god_picker.py`

- **新建**: `src/xmuse_core/platform/selection/__init__.py`, `src/xmuse_core/platform/selection/god_picker.py`
- **修改**: `orchestrator.py`（删除 `_pick_execution_god` / `_pick_review_god` / `_mixed_cursor` / god 列表初始化，改为注入 GodPicker）
- **测试**: `tests/test_platform_god_picker.py`（mixed/codex/claude 三模式 + round-robin cursor）
- **Diff 规模**: 300-500 行
- **验证门**: `pytest tests/test_platform_god_picker.py tests/test_xmuse_platform_orchestrator.py -q` 全绿
- **PR title**: `refactor(platform): extract GodPicker to selection submodule`

### 8.3 Step 3: `platform/verdicts/writer.py`

- **新建**: `src/xmuse_core/platform/verdicts/__init__.py`, `src/xmuse_core/platform/verdicts/writer.py`
- **修改**: `orchestrator.py`（删除 `_stable_verdict_id_for_lane` / `_ingest_merge_verdict_for_lane` / `_ingest_rework_verdict_for_lane` / `_gate_report_ref_for_lane`）
- **测试**: `tests/test_platform_verdicts_writer.py`（2-3 个 round-trip 测试）
- **Diff 规模**: <300 行
- **验证门**: `pytest tests/test_platform_verdicts_writer.py tests/test_xmuse_platform_orchestrator.py -q` 全绿
- **PR title**: `refactor(platform): extract verdict writer to submodule`

### 8.4 Step 4: `platform/projection/dependents.py`

- **新建**: `src/xmuse_core/platform/projection/__init__.py`, `src/xmuse_core/platform/projection/dependents.py`
- **修改**: `orchestrator.py`（删除 `_reproject_dependents_if_needed` + 相关 helper）
- **测试**: `tests/test_platform_projection_dependents.py`（feature_group=None / 多依赖 / 已合并依赖）
- **Diff 规模**: 300-500 行
- **验证门**: `pytest tests/test_platform_projection_dependents.py tests/test_xmuse_platform_orchestrator.py -q` 全绿
- **PR title**: `refactor(platform): extract projection/dependents submodule`

### 8.5 Step 5: `platform/execution/{executor,review,gate,merger}.py` + `platform/messages.py`

- **新建**: `src/xmuse_core/platform/execution/__init__.py`, `executor.py`, `review.py`, `gate.py`, `merger.py`, `src/xmuse_core/platform/messages.py`
- **修改**: `orchestrator.py`（删除全部 `_run_execution_god*` / `_run_review_god*` / `_run_gate*` / `_auto_merge*` / fallback 系列方法；orchestrator 变为 ~300 行门面）
- **测试**: `tests/test_platform_review_fallback.py`（强制单测）+ 现有集成测试
- **Diff 规模**: >1000 行（核心重构步骤）
- **验证门**: `pytest tests/ -k "platform" -q` 全绿
- **PR title**: `refactor(platform): extract execution lifecycle + Transport abstraction`

### 8.6 Step 6: controller 侧子模块

按依赖顺序：adapters → evidence/aggregator → budget → proposal/drafter → proposal/reviewer → clarification → controller 门面化。

- **新建**: `adapters/lanes_reader.py`, `adapters/chat_reader.py`, `evidence/aggregator.py`, `budget/window.py`, `proposal/drafter.py`, `proposal/reviewer.py`, `clarification/lifecycle.py`
- **修改**: `controller.py`（逐步委托，最终 ~400 行）
- **测试**: `tests/test_self_evolution_adapters.py`（fixture-based）+ 现有集成测试
- **Diff 规模**: >1000 行
- **验证门**: `pytest tests/ -k "self_evolution or engine" -q` 全绿
- **PR title**: `refactor(self_evolution): decompose controller into submodules`

### 8.7 Step 7: 清理

- **修改**: `orchestrator.py`（删除已委托的旧方法残留）、`controller.py`（同上）
- **验证门**: `pytest -q` 全套绿 + `ruff check .` 无 unused import
- **PR title**: `chore: remove delegated stubs from orchestrator + controller`

## 9. 今晚交付清单

- [ ] 本 spec 已 commit
- [ ] Step 1（prompts/builders.py）— 代码 + 测试 + commit
- [ ] Step 2（selection/god_picker.py）— 代码 + 测试 + commit
- [ ] Step 3（verdicts/writer.py）— 代码 + 测试 + commit
- [ ] Steps 4-7 通过 chat→proposal→lanes 注入 xmuse 自迭代队列（一个 resolution，4 条依赖链 lane）
- [ ] Health watcher 确认 runner 在手动 steps 1-3 期间保持稳定

## 10. 风险与回滚

### 10.1 Test-mock churn

现有测试 monkeypatch orchestrator 的私有方法（如 `_call_claude`、`_run_execution_god`）。迁移期间这些方法会移到子模块。

**缓解**：迁移期间在 `platform/__init__.py` 保留 re-export；旧测试的 monkeypatch target 通过 re-export 继续生效。Step 7 清理时一并更新测试 target。

### 10.2 Mid-migration partial state

orchestrator 半委托状态（部分方法已移、部分还在）必须端到端可用。

**缓解**：每步是独立可提交的 PR；集成测试在每步 commit 后运行。如果某步 break，revert 该步即可，不影响已完成的步骤。

### 10.3 xmuse 自迭代 steps 4-7 质量风险

xmuse 自迭代可能产出不符合 spec 的代码。

**缓解**：
- 每条 lane 有 `gate_profiles: ["xmuse-core"]`，gate runner 会跑 `pytest + ruff`。
- review-god 会审查代码是否符合 spec 中的接口签名。
- 如果 lane 失败 3 次，自动标记 `failed`，不会合并。人工介入修复。

### 10.4 A2A 过早抽象

如果 Transport 最终只有 SubprocessTransport 一个实现，抽象就是开销。

**缓解**：Transport Protocol + dataclass 总共 <50 行代码。即使最终只有一个实现，可读性收益（显式 Request/Response 边界）也值得。

## 11. 给 A 阶段（A2A 完善）的承诺

A 阶段将继承以下已定型接口：

- **ExecuteRequest / ExecuteResponse / ReviewRequest / ReviewVerdict** dataclass 已存在于 `platform/messages.py`。A 阶段只需新增 Transport 实现（MCPTransport / SSETransport），不改 executor / review 模块。
- **GodPicker**（`platform/selection/god_picker.py`）是唯一 runtime 亲和性决策点。A 阶段可扩展其策略（如 health-aware swap、per-lane runtime override）。
- **prompts/builders.py** 是唯一 lane prompt 模板所在地。A 阶段可按 runtime 差异扩展 prompt 变体（如 codex 不需要 `--output-format json` 包装）。
- **Transport Protocol** 的 `send_execute` / `send_review` 签名已固定。A 阶段新增通道只需实现这两个方法。
- **触发模式**：Pull（orchestrator 唯一触发者）。A 阶段不改变此模式；长命 god session 的 push 模式留待 A2 子阶段。
- **序列化**：JSON。所有 Transport 实现统一用 JSON 序列化 Request/Response。

## 13. B 阶段（A2A 协议完善）决策记录

B 阶段分 4 个子阶段，依赖链 B1 → B2 → B3 → B4。

### B1：GodManifest + 能力注册

```python
@dataclass(frozen=True)
class GodManifest:
    name: str                          # "execute-codex", "review-claude"
    runtime: str                       # "codex" | "claude"
    capabilities: list[str]            # ["execute", "review", "brainstorm", "gate"]
    supported_request_versions: dict[str, int]  # {"ExecuteRequest": 2, "ReviewRequest": 1}
    max_concurrency: int
    health_endpoint: str | None        # 长命 god 可选
```

注册方式：短命 god 从 `xmuse/god_manifests/*.json` 加载；长命 god 连接后 push manifest。

### B2：schema 版本协商

策略：**additive-only 字段裁剪**。v2 Request 发给只支持 v1 的 god 时，strip 新增字段。破坏性变更 = 新 major version，不降级，直接 fail。

### B3：死信队列

存储：SQLite `dead_letters` 表（id / request_type / request_json / failure_reason / retry_count / created_at / status）。MCP tool：`get_dead_letters` / `replay_dead_letter`。orchestrator 不再自己做 retry——只关心"成功 or 进了 DLQ"。

### B4：多 god 协作

- **vote 模式**：N 个 reviewer 独立 review → per-lane `vote_policy`（majority / unanimous / weighted），默认 majority。
- **peer 模式**：单轮（A 出方案 → B 评审 → approve 或 A 修改后直接提交）。最多 2 轮，无死循环风险。

## 12. 给 D 阶段（前端探索）的影响

- Frontend dashboard 的 `/api/dashboard/features/{feature_group}` 和 lane-graph 端点依赖 lane 状态读取。迁移完成后，`LanesReader` 成为唯一读取入口，dashboard API 可直接复用它，不再需要自己解析 `feature_lanes.json`。
- Chat-driver 和 peer-chat decomposer（已切换到 codex gpt-5.4）与 controller 同级但独立。它们的 runtime 选择由 `XMUSE_CHAT_DRIVER_RUNTIME` / `XMUSE_PEER_CHAT_RUNTIME` 环境变量控制，与 god_picker 是不同关注点。
- 前端 chat 界面消费的 `/api/chat/*` 端点不受本次重构影响——ChatStore 接口不变。
- 未来前端如果需要实时 lane 状态推送（WebSocket），可以在 `LanesReader` 上加 change-notification hook，而不是在 orchestrator 里加。
