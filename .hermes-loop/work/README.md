# Hermes Loop — Work Directory

## Lane Model

```
execute_lane  → work/{current-phase}/  读写 src/ tests/ alembic/
plan_lane     → work/{next-phase}/     只写规划文件
research_lane → work/{future-phase}/   只写 research.md
review_lane   → work/{phase}/reviews/  只读，输出 reviews/*.md
```

## Per-Phase Artifacts

```
work/{phase-id}/
├── god_dispatch.json          God 分发任务 + 指标
├── brainstorm.md              brainstorming 方案对比
├── spec.md                    设计文档
├── plan.md                    实现步骤
├── plan_final.md              自审查后的最终计划
├── plan_review.md             自审查反馈
├── result.md                  执行报告
├── execute_review.md          内审报告
├── review_verdict.json        终审 verdict (FAIL)
├── ack.json                   验收确认 (PASS)
├── reflect_{phase-id}.md      God 反思
├── research.md                预研 (仅 research_lane)
└── reviews/                   并行审查输出 (仅 review_lane)
```

## Lane Rules

1. execute_lane: 唯一能写 src/ tests/ alembic/ docs/
2. plan_lane: PLAN_STORM/DRAFT/SELF_REVIEW only, no EXECUTE
3. research_lane: research.md only, no code
4. review_lane: read-only, output to reviews/
5. ACK → promote plan_lane → execute_lane
6. GOD_ADJUST → revalidate plan_lane
