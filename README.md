# MemoryOS Lite

面向长对话的 Eval 驱动、源归因 Agent/RAG 记忆原型。

MemoryOS Lite 探索如何将长对话摄入、分页压缩为可审计的记忆页、在 token 预算内检索、
修补，并通过确定性源归因检查进行评估。这是一个后端/Agent 应用原型，不是生产级记忆平台。

## 动机

长对话在答案无法追溯到源消息时会以难以调试的方式失败。MemoryOS Lite 的核心问题是
**源归因漂移**：记忆系统可能检索到宽泛的页面甚至生成看似合理的答案，但丢失了支撑它的
确切消息。本原型将此转化为 eval 问题——分别追踪页级重叠、消息级证据命中和最终源准确率。

## 核心指标

| 指标 | SQLite cosine | Qdrant ANN |
|------|--------------|------------|
| Hard eval（确定性） | 1.00/1.00 | 1.00/1.00 |
| LongMemEval source_hit | 92%（46/50） | 92%（46/50） |
| LongMemEval answer_accuracy（LLM judge） | 76%（38/50） | **80%（40/50）** |
| 全量测试 | 275 pass | 275 pass |

## 架构

```
消息摄入 → ContextRotGuard → PagingAgent → MemoryPages
                                                ↓
任务请求 → DynamicBudget → ContextBuilder ← HybridSearcher
                                ↓
                        ContextPackage（token 预算内）
                                ↓
        memory_think → memory_action → memory_observe → 回答/END
```

**核心抽象：**

| 概念 | OS 类比 | 职责 |
|------|---------|------|
| Context Window | RAM | 活跃工作记忆 |
| Memory Pages | 分页存储 | 压缩的历史状态 |
| ContextRotGuard | OOM killer | 在腐化前触发分页 |
| ContextBuilder | 缺页处理器 | 在预算内召回相关页 |
| HybridSearcher | 页表查找 | BM25 + embedding 检索 |

**结构化 Agent 节点：**

| 节点 | 职责 | LLM? |
|------|------|------|
| `memory_think` | 分类意图为 memorize/recall/patch/none | 是（或 scripted fallback） |
| `memory_action` | 确定性 dispatch 到记忆工具 | 否 |
| `memory_observe` | 解析工具输出，生成摘要 | 否 |

## 主要特性

- **自动分页** — ContextRotGuard 在 token 预算超限时触发分页；支持启发式或 LLM 分页
- **混合检索** — BM25 词法 + embedding 余弦相似度，通过 RRF 融合
- **Token 预算上下文构建** — 动态预算分配：固定核心 profile、近期消息、检索页
- **冲突检测** — slot/否定启发式标记与现有记忆矛盾的修补
- **源可追溯** — 上下文包中每个事实都追溯到源消息
- **结构化 Agent** — Think-Act-Observe 循环，确定性 dispatch，有界工具调用
- **评估体系** — 确定性 recall/source 检查 + 可选 LLM-as-judge 语义评分
- **可观测性** — Prometheus 指标：分页、检索、上下文构建延迟和预算利用率

## 快速开始

```bash
uv venv --python 3.11 && source .venv/bin/activate
uv sync
uv run memoryos demo run          # 基础 demo
uv run memoryos demo agent        # 确定性 LangGraph demo，无需 API key
```

### API 服务

```bash
uv run memoryos api --reload
# 或 Docker
make up
```

### 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions` | 创建会话 |
| POST | `/sessions/{id}/ingest` | 摄入消息 |
| POST | `/sessions/{id}/page` | 触发分页 |
| POST | `/sessions/{id}/build-context` | 构建上下文包 |
| POST | `/memory/search` | 混合检索 |
| GET | `/sessions/{id}/trace` | 审计追踪 |
| GET | `/metrics` | Prometheus 指标 |

## 配置

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DATA_DIR` | SQLite 数据库和页目录 | `.memoryos` |
| `OPENAI_API_KEY` | LLM 分页 + embedding | — |
| `DEEPSEEK_API_KEY` | DeepSeek chat LLM | — |
| `MEMORYOS_PAGING_MODE` | `heuristic` / `llm` | `heuristic` |
| `ROT_SAFE_BUDGET` | 分页触发阈值 | 2400 tokens |
| `HARD_LIMIT` | 绝对上下文上限 | 8000 tokens |
| `QDRANT_URL` | 可选 Qdrant ANN 后端 | — |

安全默认值为离线模式：`demo agent`、`eval run` 和公开 eval `--no-llm-answer`
不调用任何外部 API。真实 API 调用通过设置和命令显式启用。

## 评估

确定性 eval 比较 4 个 baseline：

```bash
uv run memoryos eval run --baseline all
```

LLM-as-judge 语义准确率（需要 `DEEPSEEK_API_KEY`）：

```bash
uv run memoryos eval run --llm-judge
```

公开 benchmark（LongMemEval / LoCoMo）：

```bash
uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --limit 50 --llm-answer --llm-judge
```

## 原型边界

- LangGraph agent 是实验性 demo，不是生产编排
- 启发式分页是确定性 fallback，不是完整语义压缩
- 冲突检测是一阶 slot/否定启发式
- SQLite embedding 检索是 Python 侧余弦评分，不是 ANN
- FastAPI 无认证、限流或生产所有权模型

## 开发

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
make lint
```

## 技术栈

- Python 3.11+ / uv
- FastAPI + Uvicorn
- SQLAlchemy + Alembic (SQLite)
- LangChain + LangGraph
- tiktoken, rank-bm25, fastembed
- Qdrant（可选 ANN 向量检索后端）
- Prometheus client
- Docker + docker-compose

## License

MIT
