# Agentic Memory Roadmap

MemoryOS Lite 当前是 eval-driven、source-attributed Agent/RAG memory prototype。
路线图描述研究方向，不承诺生产能力或具体发布日期。

## 已收束基线

- 默认 v3 layered composer 与 v2 episode-first recall。
- SQLite authority、可重建派生索引和来源证明。
- Core、recall、archival、recent 分层预算与可解释丢弃。
- Agent kernel 保持 opt-in，不成为记忆存储 authority。

## 后续重点

1. **Evidence planning**：提高 temporal、多会话和冲突场景下的检索稳定性，同时保留逐项来源与预算解释。
2. **Answer use**：在检索指标之外独立测量回答是否正确使用证据、引用来源并在无证据时拒答。
3. **Memory governance**：强化 core/archival 候选的审批、冲突、历史和删除语义，禁止无来源事实静默晋升。
4. **Scale evidence**：扩大固定 benchmark slice，报告 case-level movement、延迟和资源边界，而不是只报告聚合分数。
5. **Integration hardening**：保持 loopback HTTP 契约小而稳定；消费者拥有自身工作流 authority，MemoryOS 只提供不可信的来源证据。

任何默认切换或兼容删除都必须由实现、迁移测试、来源证明测试和新鲜 benchmark 共同支持。
