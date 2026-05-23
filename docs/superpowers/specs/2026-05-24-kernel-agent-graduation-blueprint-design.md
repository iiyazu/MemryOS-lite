# MemoryOS Lite 毕业级 Kernel Agent Blueprint 设计

日期：2026-05-24
状态：God 自审通过，已作为 Phase 14 蓝图修订依据
设计目标：在现有 MemoryOS Lite v3 架构上，构建一个 Letta-style、可审计、可验证、可通过公开 benchmark 治理的最小完整 agent memory control plane。

## 1. 目标与边界

本设计采用“架构毕业优先，评测毕业作为硬验收”的目标口径。

### 1.1 目标

- 形成完整的 kernel agent loop：
  `context -> tool selection -> policy -> approval -> execute -> verify -> tool return -> continuation`。
- 复用现有 `core memory`、`recall`、`archival memory`、`context composer` 和 lifecycle 能力，而不是重建一套平行 memory 系统。
- kernel 被显式启用后，内部默认运行受约束的 hybrid tool selection。
- 用 LongMemEval 和 LoCoMo 验证 source-grounded 行为，但不让 benchmark gold 信息污染 memory 写入。

### 1.2 非目标

- 不将 MemoryOS Lite 描述为生产级 MemoryOS。
- 不直接复刻或依赖 Letta runtime。
- 不在第一轮开放破坏性 memory delete/deprecate 工具。
- 不把 kernel maintenance 直接变成默认 public benchmark 路径。
- 不允许以同一 repair slice 的提升作为毕业或 promotion 证据。

### 1.3 默认行为

- 外部默认仍保持 kernel opt-in；不得因本设计自动改变默认开关。
- 当 kernel 已启用时，kernel 内部默认开启 tool selection。
- 默认 public benchmark 保持不受 maintenance 写入影响；kernel repair eval 必须显式启用。

## 2. 设计原则

### 2.1 以项目既有抽象为主

MemoryOS 当前已有足以承载 kernel 的分层基础：

- `RecallPipeline` 提供历史对话证据；
- `V3ContextComposer` 组装 core / recall / archival / recent；
- `CoreMemoryService` 提供 source-backed core block lifecycle；
- `MemoryLifecycleService` 提供 archival/core promotion 入口；
- `MemoryStore` 提供 history、passage、attachment 与 scope eligibility；
- `SimpleAgentStepRunner` 和 `SimpleToolExecutionManager` 提供最小 kernel 起点。

新 kernel 应升级控制面与服务边界，不应绕开这些能力直接在 kernel 文件中持续扩张 store mutation。

### 2.2 借用 Letta 语义，不复制 Letta 体量

从 Letta 借用：

- agent step loop 和 continuation；
- tool rule / approval pending 边界；
- approval response 与 pending tool call 的绑定；
- tool executor 路由；
- tool-return message 持久化；
- core/archival memory 工具由管理服务执行；
- component-level context accounting。

不引入：

- 完整 Letta agent runtime；
- 多租户、server job、streaming、client tool、sandbox 等超出本项目毕业目标的能力。

### 2.3 Benchmark 只能评估，不能指导写入

公开 benchmark 中的 expected answer、expected source ids、gold-derived failure labels 属于 eval-only sidecar。它们可以用于报告、分类、验收，不得进入 agent 可见记忆或可执行 tool request。

## 3. 总体架构

### 3.1 主循环

```text
User Turn / Trigger
  -> V3ContextComposer.build()
  -> ToolSelectionRouter
       deterministic candidate routing
       optional LLM choice within candidates
       deterministic fallback
  -> ToolPolicyEngine
  -> ApprovalLedger
  -> ToolExecutionManager
  -> Domain Executor / Existing Memory Service
  -> VerificationService
  -> ToolReturnRecord + Kernel Trace
  -> ContinuationController
  -> next step | pause | stop | escalate
```

### 3.2 组件职责

#### `KernelStepRunner`

- 编排单个或有限多个 kernel steps。
- 读取 context、selection、policy、approval、execution、verification、continuation 结果。
- 持久化 trace 与 tool-return message。
- 不直接实现 core/archival 领域写入规则。

#### `ToolSelectionRouter`

- 先通过 deterministic routing 生成候选工具和理由。
- kernel 启用后，默认允许 LLM 在候选集合中选择工具并填参。
- LLM 不得选择候选集合之外的工具。
- LLM 失败、超时或输出非法时，回退到 deterministic result 或不执行工具。

#### `ToolPolicyEngine`

- 对候选调用决策：`allow`、`deny`、`require_approval`。
- 决策必须说明 matched rule、scope 条件、provenance 条件与 denial reason。
- 写工具默认需要 approval，除非被明确定义为低风险且满足强 source refs 的确定性写入。

#### `ApprovalLedger`

- 持久化 pending/approved/denied/executed 状态。
- approval 必须绑定：
  `step_id`、`tool_call_id` 或稳定 request fingerprint、`tool_name`、arguments、session/scope、source refs。
- 重放只有在绑定完全匹配时有效。
- 重复 approval 对已执行调用只能 idempotent skip，不能重复 mutation。

#### `ToolExecutionManager`

- 按注册表将 tool call 路由到 executor。
- 输出统一结构化执行结果。
- 对返回 payload 进行有界化处理，避免 tool return 无界占用 context。

#### Domain Executors

- `ArchivalToolExecutor`：archive write/attach 等；依赖 archival store/service。
- `CorePromotionExecutor`：只创建或应用 source-backed promotion candidate；依赖 `MemoryLifecycleService` 和 `CoreMemoryService`。
- `RecallSearchExecutor`：只读检索；依赖 recall/search 服务。
- `MaintenanceNoteExecutor`：记录诊断维护 artifact；不得伪装为用户记忆。

#### `VerificationService`

- 对写操作验证真实落库结果：
  history、source refs、scope eligibility、passage/attachment、v3 context 可见性。
- 输出正面或负面 verification result。
- 验证失败不抹去已经发生的 execution；必须留下可审计失败记录。

#### `ContinuationController`

- 第一轮支持 `stop`、`pause`、`continue`、`escalate`。
- 受 step 上限约束，禁止无限工具循环。
- `compact` 仅保留契约入口，后续再实现。

## 4. 核心数据契约

### 4.1 `ToolCallRecord`

必须包含：

- `step_id`
- `tool_call_id`
- `request_fingerprint`
- `tool_name`
- `arguments`
- `session_id`
- `identity_scope`
- `source_refs`
- `selection_origin`: `deterministic | llm | fallback`
- `candidate_reason`

### 4.2 `ApprovalRecord`

必须包含：

- tool call 的完整绑定信息；
- `status`: `pending | approved | rejected | expired | executed | skipped`;
- actor 与 reason；
- requested/resolved timestamps；
- replay/idempotency metadata。

### 4.3 `ToolExecutionResult`

必须包含：

- `status`: `success | error`;
- `tool_name`;
- bounded `result`;
- `error`;
- `source_refs`;
- `verification`，若该工具要求写后验证。

### 4.4 `VerificationResult`

必须包含：

- `status`: `verified | failed | not_required`;
- `ok`;
- `checks`；
- `failure_reason`；
- 与 tool call、approval、written resource 的绑定信息。

### 4.5 `KernelTraceEvent`

至少支持：

- `kernel_step_started`
- `tool_candidates_generated`
- `tool_selected`
- `tool_policy_decision`
- `approval_pending`
- `approval_granted`
- `approval_replay_denied`
- `tool_denied`
- `tool_executed`
- `tool_verified`
- `tool_replay_skipped`
- `continuation_decided`
- `kernel_step_completed`

## 5. Hybrid Tool Selection

### 5.1 默认策略

kernel 启用后默认执行 hybrid selection：

1. deterministic router 查看 current task、v3 context、allowed tool registry 和可见 diagnostics。
2. router 输出候选工具集合及每个候选的约束。
3. LLM selector 只能在候选集合内选择一个或不选择，并生成参数草案。
4. schema validation、policy 和 provenance validation 重新检查参数。
5. 任一步失败则 fallback 或停止，不允许自由执行未知工具。

### 5.2 输入边界

LLM selector 可见：

- user/message input；
- v3 selected context；
- tool descriptions 与 policy summaries；
- model-visible retrieval/verification trace。

LLM selector 不可见、不可用于写入：

- expected answer；
- expected source ids；
- benchmark judge labels；
- gold-derived failure target。

## 6. 工具分级开放

### 6.1 Level 1: Write-Safe Tools

- `archive_write`
- `archive_attach`
- `core_promotion_request`

约束：

- 写入需要 source refs 或 approved approval；
- `core_promotion_request` 只生成 candidate，不直接覆写 core block；
- 每次写入必须有 verification。

### 6.2 Level 2: Read/Search Tools

- `recall_search`
- `archive_search`

约束：

- 只读；
- 返回内容受 token budget 与 scope 限制；
- 返回来源必须可追溯；
- 检索结果可参与后续 tool selection，但不得自动写 memory。

### 6.3 Level 3: Controlled Core Edit Tools

- `core_memory_append`
- `core_memory_replace`

约束：

- 强制 approval；
- source-backed；
- read-only block fail-closed；
- replace 必须精确匹配且保留 before/after history；
- 不在前两级完成前开放。

### 6.4 禁止工具

第一轮不允许：

- destructive delete/deprecate；
- 直接绕过 lifecycle 的 store mutation；
- benchmark-targeted repair write；
- 未注册或 LLM 自行构造的工具名。

## 7. Error Handling 与安全语义

### 7.1 Policy 与 Approval

- `tool_denied`：不执行，不写 memory，不产生成功 tool return。
- `approval_pending`：暂停当前 loop，新的 normal turn 不得覆盖 pending action。
- `approval_replay_denied`：任一 binding 不匹配立即拒绝。
- `tool_replay_skipped`：已执行调用的重复 approval 只记录幂等跳过。

### 7.2 Execution 与 Verification

- `tool_executed(status=error)`：记录失败 tool return，不记录 verified success。
- `tool_executed(status=success)` 后必须执行配置的 verification。
- `tool_verified(ok=false)` 表示真实 mutation 或其可见性未被验证；该 action 不可计入完成证据。
- verification failure 必须持久化，不得静默省略。

### 7.3 Continuation

- approval pending 时为 `pause`。
- 合法 tool result 后可 `continue` 进入下一步。
- 达到 step limit 为 `stop/max_steps`。
- policy/provenance/verification 异常可 `escalate`。

## 8. Anti-Contamination 与 Eval 设计

### 8.1 Gold Isolation

以下字段只能出现在 eval sidecar、报告与验收工件中：

- expected answer；
- expected source ids；
- gold failure class；
- gold-derived repair target；
- case-id 特判规则。

可执行 proposal 必须声明：

```text
gold_fields_used = false
```

如果 proposal 不能仅从 model-visible artifacts 生成，则只能成为 diagnostic-only artifact，不得进入 kernel execution。

### 8.2 Eval 模式

#### Default Public Eval

- kernel maintenance 默认不参与；
- 保持与历史 v3 baseline 可比；
- 验证 default-off 行为不被新 kernel 污染。

#### Opt-In Repair Smoke

- 显式启用 kernel maintenance；
- 允许在固定 slice 上观察 wiring 和 failure-class movement；
- 独立 `DATA_DIR`；
- 不作为质量 promotion 证据。

#### Graduation Validation

- 使用 clean-store 或 held-out case 集；
- 运行 LoCoMo 和 LongMemEval full-chain LLM judge；
- 同时报 judged pass 与 source-grounded pass；
- 只有该层证据可以支持毕业判断。

## 9. 分阶段蓝图

### K0: Kernel Contract Freeze

目标：

- 冻结 tool call、approval、tool return、verification 与 trace 契约。

交付：

- schemas/interfaces；
- deterministic fixtures；
- serialization/replay contract tests。

不做：

- 新工具执行；
- benchmark quality claim。

### K1: Audited Control Plane

目标：

- 将现有 `archive_write` 贯穿可信 loop。

交付：

- approval ledger binding；
- execution/verification positive and negative traces；
- bounded tool return；
- replay/idempotency tests。

验收：

- 单工具真实 store/history/scope/v3 visibility 闭环；
- kernel 外部默认行为不变。

### K2: Hybrid Tool Selection

目标：

- kernel 内默认开启受约束 tool selection。

交付：

- deterministic candidate router；
- LLM selector adapter；
- fallback 与 illegal-tool denial；
- selection trace。

验收：

- LLM 不可越权选择候选外工具；
- 没有 gold-field 输入；
- deterministic test path 可复现。

### K3: Graduated Memory Tools

目标：

- 在 service boundary 下逐级开放 memory tools。

子阶段：

- K3a：write-safe tools；
- K3b：read/search tools；
- K3c：controlled core edits。

验收：

- 每个工具都有 registry、policy、executor、verification 和 integration tests；
- 不出现 ad hoc direct store write 扩散。

### K4: Maintenance Planner And Repair Eval

目标：

- 从 model-visible diagnostics 生成可审计 maintenance proposal。

交付：

- proposal model；
- eval sidecar 与 executable payload 分离；
- opt-in repair smoke；
- gold leakage tests。

验收：

- same-slice 只报告 smoke；
- proposal 能证明 `gold_fields_used=false`。

### K5: Graduation Governance

目标：

- 判断 kernel agent loop 是否达到毕业级。

交付：

- clean-store / held-out gate；
- case movement report；
- source-grounding report；
- promotion/hold/continue-targeted decision。

验收：

- LoCoMo 不被 LongMemEval 掩盖；
- 未解释 pass-to-fail 阻止毕业；
- source-miss judge-pass 风险显式报告；
- kernel 默认策略变更需单独批准。

## 10. 测试策略

### 10.1 Contract Tests

- fingerprint 稳定且可重放；
- approval binding 严格；
- result/verification/trace 可序列化；
- unsupported tools fail-closed。

### 10.2 Kernel Loop Tests

- clean stop；
- pending approval pause；
- approved execution exactly once；
- replay skip；
- verification success/failure；
- bounded max steps。

### 10.3 Memory Integration Tests

- archival write -> history -> passage -> scoped v3 context；
- attachment scope eligibility；
- core promotion candidate 不直接 mutate core；
- read tools 无 side effects；
- controlled core edit 的 approval/source/read-only 约束。

### 10.4 Eval Tests

- default public path 不出现 kernel maintenance；
- opt-in trace 可见；
- executable payload gold isolation；
- repair smoke 标签准确；
- clean-store/held-out graduation gate。

## 11. 毕业标准

必须同时满足：

- **架构完整**：启用 kernel 后，hybrid tool selection 与完整 audited action loop 可运行。
- **边界清晰**：kernel 编排与 memory domain services 分离。
- **写入可信**：所有 mutation 有 provenance、history、verification、trace。
- **循环有界**：approval、replay、continuation 与 max-step 可控。
- **工具分级**：至少完成 write-safe 与 read/search；controlled core edit 只有通过安全 gate 后才计入毕业。
- **评测可信**：无 gold leakage；repair smoke 与 promotion evidence 明确分离。
- **结果可解释**：LoCoMo 与 LongMemEval 均有 source-grounded case-level 报告。

## 12. 与 Hermes Active Blueprint 的接入策略

本 spec 是毕业级路线图主文档，不直接覆盖当前 active blueprint。

接入方式：

1. 在 phase-local amendment 中记录 K0-K5 映射、kernel/eval hard boundaries 和对当前 Phase 14 的影响。
2. 当前 Phase 14 只吸收 K1 中与 `archive_write` verification、approval binding、negative verification 相关的最小要求。
3. God 在 Phase 14 review/ACK 或 adjustment 时决定是否将现有 Phase 15-18 显式映射或重排为 K2-K5。
4. 未经 reviewed amendment，不自动改变 `state.json` 或默认 runtime flags。

## 13. 决策记录

- 采用 layered graduation roadmap，而非一次性扩展 tool surface。
- 外部 kernel 仍 opt-in；kernel 内部默认启用 hybrid tool selection。
- hybrid selection 采用 deterministic router + constrained LLM selector + deterministic fallback。
- memory tools 分级开放。
- default public benchmark 不直接消费 kernel maintenance；新增 opt-in repair eval。
- same-slice repair 只作为 structural smoke；毕业结论依赖 clean-store 或 held-out validation。
