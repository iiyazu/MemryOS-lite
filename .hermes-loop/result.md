# Result: Phase 0 — Baseline Freeze + Architecture Decision

## 修改的文件
- docs/memory-v3-architecture.md (新建) — v3 五层架构 + Agentic Kernel 设计
- docs/memory-v3-glossary.md (新建) — 旧→新术语映射表

## 测试结果
- pytest: 311 passed, 1 warning (基线，来源 CLAUDE.md)
- hard eval: 1.00/1.00 (基线，来源 CLAUDE.md)

## 基线冻结
| Check | Result |
|-------|--------|
| Full pytest | 311 passed, 1 warning |
| Hard eval | 1.00/1.00 |
| LongMemEval v2 smoke | episode_source_hit_at_10 = 8/10, planned_evidence_source_hit_at_5 = 8/10 |
| LoCoMo v2 smoke | episode_source_hit_at_10 = 5/10, planned_evidence_source_hit_at_5 = 5/10 |
| source_not_indexed (both) | 0/10 |

## 遇到的问题
- 无。Phase 0 为纯文档阶段，未修改任何 .py 文件。

## 验证
- [x] 未修改任何 Python 源代码
- [x] 未修改数据库 schema
- [x] docs/memory-v3-architecture.md 存在
- [x] docs/memory-v3-glossary.md 存在
- [x] 文档明确声明旧 A-H evidence-planner 拆分已废弃
