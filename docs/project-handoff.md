# MemoryOS Lite — 会话间交接文档

最后更新：2026-05-17

## 项目定位

MemoryOS Lite 是一个 eval 驱动的 Agent/RAG 记忆原型，面向长对话的摄入、分页压缩、
token 预算内检索、修补和源归因评估。用于后端/Agent 应用面试展示，不是生产级记忆平台。

**仓库：** `git@github.com:iiyazu/MemryOS-lite.git`
**分支：** `feat/phase-2.5-3-retrieval-agent`（已推送，待创建 PR）
**PR 链接：** https://github.com/iiyazu/MemryOS-lite/pull/new/feat/phase-2.5-3-retrieval-agent

---

## 当前状态

### 已完成

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1-2 | 基础 ingest/page/retrieve/eval 框架 | ✅ 已在 origin/main |
| Phase 2.5 | Eval budget bug fix, fastembed 本地 embedding | ✅ 在 PR 分支 |
| Phase 2.6 | Multi-query expansion, rewrite/rerank, source_hit 16%→92% | ✅ 在 PR 分支 |
| Phase 3 | Answer accuracy baseline (76-80%), structured Think-Act-Observe agent | ✅ 在 PR 分支 |
| README | 中文重写，反映最终架构和指标 | ✅ 在 PR 分支 |

### 核心指标

| 指标 | SQLite cosine | Qdrant ANN |
|------|--------------|------------|
| Hard eval（确定性） | 1.00/1.00 | 1.00/1.00 |
| LongMemEval source_hit | 92% (46/50) | 92% (46/50) |
| LongMemEval answer_accuracy | 76% (38/50) | 80% (40/50) |
| LoCoMo source_hit | 50% (25/50) | — |
| LoCoMo answer_accuracy | 24% (12/50) | — |
### 未完成 / 已知问题

1. **PR 未创建** — 分支已推送，需手动在 GitHub 创建（无 `gh` CLI）
2. **Embedding 维度修复未 commit** — `store.py` 中 `EMBEDDING_DIM` 改为动态适配
   （384/1536），代码已改但未 commit
3. **Qdrant+fastembed eval 性能问题** — 每个 case 550 条消息 × 50 pages 的
   ingest+page 循环中 fastembed embedding 计算导致单 case 约 5 分钟，50 case 需 4 小时。
   之前 80% 结果实际是 embedding 跳过（维度不匹配）只用 BM25 的结果
4. **LoCoMo 表现弱** — 24% answer accuracy，已知问题
5. **memory_think_node 无真实 LLM** — 当前 fallback 为 action="none"，未接入 DeepSeek

---

## 架构

```
消息摄入 → ContextRotGuard → PagingAgent → MemoryPages
                                                ↓
任务请求 → DynamicBudget → ContextBuilder ← HybridSearcher (BM25 + embedding RRF)
                                ↓
                        ContextPackage（token 预算内）
                                ↓
router → tool_agent → memory_think → memory_action → memory_observe → build_context → answer/END
```

### 关键文件

| 文件 | 职责 |
|------|------|
| `src/memoryos_lite/engine.py` | 核心服务：ingest, page, build_context, create_item |
| `src/memoryos_lite/agent_graph.py` | LangGraph agent：router, tool loop, Think-Act-Observe |
| `src/memoryos_lite/store.py` | SQLite 存储层，EmbeddingType 维度验证 |
| `src/memoryos_lite/retrieval/hybrid.py` | BM25 + embedding RRF 融合检索 |
| `src/memoryos_lite/retrieval/providers/fastembed_client.py` | 本地 embedding (384 dims) |
| `src/memoryos_lite/retrieval/providers/qdrant.py` | Qdrant ANN 向量存储 |
| `src/memoryos_lite/retrieval/query_rewriter.py` | Multi-query expansion |
| `src/memoryos_lite/public_benchmarks.py` | LongMemEval/LoCoMo eval adapter |
| `src/memoryos_lite/llm_judge.py` | LLM-as-judge 语义评分 |
| `src/memoryos_lite/cli.py` | Typer CLI：demo, eval, api |

---

## 常用命令

```bash
# 开发
uv sync
uv run pytest -q                    # 全量测试 (275 pass)
uv run ruff check src/              # lint
uv run memoryos demo agent          # 确定性 demo，无需 API key

# Eval
uv run memoryos eval run --case-set hard --baseline memoryos_lite
uv run memoryos eval run --baseline all

# 公开 benchmark（需要 DEEPSEEK_API_KEY）
uv run memoryos eval public --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 --llm-answer --llm-judge

# Qdrant 模式
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
QDRANT_URL=http://localhost:6333 uv run memoryos eval public ...
```

---

## 环境变量

| 变量 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek chat LLM（answer, judge, rewrite, rerank） |
| `OPENAI_API_KEY` | OpenAI embedding（可选，默认用 fastembed） |
| `QDRANT_URL` | Qdrant 向量数据库（可选，默认 SQLite cosine） |
| `MEMORYOS_REWRITE_ENABLED` | 启用 query rewrite |
| `MEMORYOS_RERANK_ENABLED` | 启用 rerank |

---

## 工作规则

- 检查 `git status` 后再编辑
- 不调用真实 OpenAI/DeepSeek 除非明确要求
- 先跑窄测试，再跑全量
- 不夸大 LoCoMo 或 agent 质量
- 确定性 demo/eval 路径不调用外部 API

---

## Git 状态

```
分支: feat/phase-2.5-3-retrieval-agent (55+ commits ahead of origin/main)
未 commit 的修改:
  - src/memoryos_lite/store.py (EMBEDDING_DIM 动态适配)
  - src/memoryos_lite/retrieval/__init__.py
  - src/memoryos_lite/retrieval/embedding.py
  - src/memoryos_lite/tools.py
未跟踪文件:
  - src/memoryos_lite/agent_answer_eval.py
  - src/memoryos_lite/retrieval/item_searcher.py
  - src/memoryos_lite/retrieval/providers/qdrant.py
  - tests/test_agent_answer_eval.py
  - tests/test_cli_agent_answer_eval.py
  - tests/test_item_retrieval.py
  - tests/test_item_tools.py
```

---

## 下一步可选方向

1. **Answer accuracy 优化** — 调查 11 个 fail case，改进 context→answer 投影
2. **memory_think_node 接入真实 LLM** — DeepSeek structured output 替代 fallback
3. **Core Memory hot layer** — 高频访问事实单独存储
4. **fastembed eval 性能** — batch embedding 或跳过 eval 中的 embedding
5. **LoCoMo 改进** — 当前 24%，需分析失败模式
