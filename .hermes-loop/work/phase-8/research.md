# phase: phase-8

# Research: Legacy Adapter + Deprecation Decision

## 任务
### Phase 8 — Legacy Adapter + Deprecation Decision

Target state: `default-candidate` or remain `opt-in-v3`

Tasks:

- Decide whether v3 is ready to become default.
- Shrink adapters around the old Episode/Page/Item/ContextBuilder paths.
- Remove or mark obsolete docs.
- Update README, source guide, store interface, and roadmap.

Acceptance:

- God issues a default/defer/deprecate decision.
- If v3 is not ready, keep it opt-in and return to the relevant phase.
- Documentation keeps only the rea

## 预研笔记
- 旧 Episode/Page/Item/ContextBuilder 路径需要 adapter 收缩
- v3 稳定后逐步让旧路径进入 deprecated
- 保守策略: 先 shadow, 再 bench-candidate, 最后 default-candidate
- 参考: Letta 的 compatibility 表格
