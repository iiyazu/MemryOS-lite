# phase: phase-7

# Brainstorm: Phase 7 — Benchmark + Evaluation Compatibility

## 任务
### Phase 7 — Benchmark + Evaluation Compatibility

Target state: `bench-candidate`

Tasks:

- Make hard eval, LongMemEval, and LoCoMo runnable in v3 mode.
- Report legacy and v3 side by side.
- Separate answer quality from retrieval/memory diagnostics.

Acceptance:

- Legacy metrics remain available.
- New v3 metrics do not change old field meanings.
- Reports include recall hit, archival passage hit, archival document hit, core usage, budget drop, and answer quality.
- Reports include kernel a

## 方案 A: 扩展现有 benchmark harness
在 public_benchmarks.py 添加 v3 诊断字段，保持 v1/v2 兼容。
- 优点: 最小改动
- 缺点: harness 已经很复杂
- 复杂度: 低

## 方案 B: 独立 v3 benchmark 模块
新建 benchmarks/v3_harness.py，不碰旧代码。
- 优点: 隔离好
- 缺点: 重复逻辑
- 复杂度: 中

## 推荐: 方案 A
扩展现有 harness，添加 v3 composer/kernel 诊断字段。
