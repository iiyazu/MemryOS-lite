# Brainstorm: Phase 0 — Baseline Freeze + Architecture Decision

## 方案 A: 最小文档集
只写 2 个核心文件 + 记录基线。
- 优点: 快速，不引入多余结构
- 缺点: 后续 phase 可能缺乏参考
- 复杂度: 低

## 方案 B: 详细架构文档 + 目录结构
写完整的 v3 架构设计文档 + 术语表 + 目录规划 + 基线快照。
- 优点: 为 Phase 1 (Contracts) 提供完整参考
- 缺点: 耗时
- 复杂度: 中

## 推荐: 方案 A（最小但完整）
Phase 0 的目标是"冻结基线 + 声明方向"。详细设计留给 Phase 1。
只产出: architecture doc + glossary + baseline snapshot。

## 关键发现
- 当前 schema: Role, PageType, PatchOperation, MessageCreate, Message, Episode, Session, MemoryPageDraft...
- Episode 是 v2 的核心，需迁移为 RecallMemoryEntry
- Page/Item 混合了 summary/archive/semantic 角色
- 当前 ContextBuilder/RecallPipeline 是薄层，需重建为 Composer
