# Spec: Memory v3 Architecture Foundation

## 交付物
1. `docs/memory-v3-architecture.md` — v3 五层架构 + Agentic Kernel 设计文档
2. `docs/memory-v3-glossary.md` — 旧→新术语映射
3. 基线快照 — pytest + hard eval 结果

## 不改代码
Phase 0 只产出文档。不修改任何 .py / schema / migration。

## 架构文档结构
- 概述: MemoryOS v3 目标
- 五层架构: Message Log → Recall → Archival → Core → Composer
- Agentic Kernel: StepRunner, ToolPolicy, ApprovalGate, ToolExecutor, Continuation
- 兼容状态表: legacy-stable → shadow-write → shadow-read → opt-in-v3 → bench-candidate → default-candidate

## 术语对照表结构
| 旧 (v1/v2) | 新 (v3) | 说明 |
| Message | Message | 保持不变 |
| Episode | RecallMemoryEntry | v2 临时检索单元升级为正式 Recall 层 |
| MemoryPage / MemoryItem | ArchivalDocument / ArchivalPassage / ArchivalMemory | 拆分角色 |
| ContextBuilder / RecallPipeline | ContextComposer | 合并为单层组装器 |
| agent_graph | AgenticKernel | 升级为控制平面 |
