# Hermes Loop 初始化指南

## 你是哪个节点？

开始前请确认你的角色，然后读取对应 prompt：

```bash
cat .hermes-loop/prompts/god.md
cat .hermes-loop/prompts/plan_agent.md
cat .hermes-loop/prompts/execute_agent.md
cat .hermes-loop/prompts/review_agent.md
```

## 启动步骤

1. 读 `.hermes-loop/contracts/state_machine.json`
2. 读 `.hermes-loop/state.json`
3. God 节点再读 `.hermes-loop/blueprint.md`
4. 按 `state.json.current_state` 执行当前状态

## 当前状态对应关系

| current_state | 执行节点 | 输入文件 | 产出文件 |
|---|---|---|---|
| `GOD_DISPATCH` | God | `blueprint.md` + `state.json` | `god_dispatch.json` |
| `PLAN_STORM` | Plan Agent | `god_dispatch.json` | `brainstorm.md` |
| `PLAN_DRAFT` | Plan Agent | `brainstorm.md` | `spec.md`, `plan.md` |
| `PLAN_SELF_REVIEW` | Plan Agent | `spec.md` + `plan.md` | `plan_review.md`, `plan_final.md` |
| `EXECUTE` | Execute Agent | `plan_final.md` | `result.md` |
| `EXECUTE_SELF_REVIEW` | Execute Agent | `result.md` | `execute_review.md` |
| `REVIEW` | Review Agent | `result.md` + `god_dispatch.json` | `review_verdict.json` / `ack.json` / `escalate.json` |
| `ACK` | Review Agent | `ack.json` | `ack.json` → God |
| `GOD_ADVANCE` | God | `ack.json` | `state.json` update |
| `GOD_ADJUST` | God | `escalate.json` | `blueprint.md` update |

## 核心约束

- 当前计划只来自 `blueprint.md` 和 `state.json`。
- 不要把旧 process docs 当成当前计划。
- 每次状态推进都要更新 `state.json`。
