# MemoryOS Lite

面向长对话的 eval 驱动、源归因 Agent/RAG 记忆原型。

MemoryOS Lite 的核心目标是让长期对话里的“记忆命中”可测、可追溯、可调试。系统保留原始消息、分页摘要、原子 item、可选 episode-first recall，以及 opt-in v3 layered composer 诊断，并通过确定性 benchmark 检查证据是否真的回到上下文中。

这不是生产级 MemoryOS。它适合作为 agent 应用开发实习/面试项目，展示后端记忆管线、源归因评估、上下文预算控制和可审计 agent demo。

## 当前状态

- 默认 recall 路径仍是 `v1`，保持旧行为稳定。
- `v2` episode-first recall 通过 `MEMORYOS_RECALL_PIPELINE=v2` 显式启用。
- `v3` layered composer 处于 bench-candidate，必须通过 `MEMORYOS_MEMORY_ARCH=v3` 显式启用；它不是默认路径。
- agentic kernel 仍是 opt-in：`MEMORYOS_AGENT_KERNEL=v1`。
- 存储以 SQLite 为当前实现，Alembic 迁移到 `0006_add_archival_memory`。
- Qdrant 是可选 ANN/vector 实验后端，不是默认依赖。
- 最新验证：`uv run pytest -q` -> `352 passed, 1 warning`。
- hard eval：`1.00/1.00`。
- v2 smoke：LongMemEval `episode_source_hit_at_10 = 8/10`，LoCoMo `episode_source_hit_at_10 = 5/10`。
- v3 public smoke 已能输出 `memory_arch`、`v3_layer_counts`、`v3_budget_decisions`、`v3_diagnostics`；默认切换暂缓。

## 架构概览

```text
ingest(message)
  -> Message
  -> v1: page/item/recent-message context path
  -> v2 opt-in: Episode backfill/indexing

build_context(task)
  -> v1 ContextBuilder by default
  -> v2 RecallPipeline when MEMORYOS_RECALL_PIPELINE=v2
       QueryAnalyzer
       EpisodeSearcher
       Evidence planning
       ContextPackage(metadata diagnostics)
  -> v3 ContextComposer when MEMORYOS_MEMORY_ARCH=v3
       core / recall / archival / recent layers
       ContextPackage-compatible payload with v3 diagnostics
```

核心对象：

| 对象 | 职责 |
|---|---|
| `Message` | 原始对话轮次，所有证据的最终来源 |
| `Episode` | v2 的 raw-message retrieval 单元，一条消息一条 episode |
| `MemoryPage` | 分页压缩和审计 artifact |
| `MemoryItem` | 从 page 派生的语义支持/诊断单元 |
| `CoreMemoryBlock` | v3 always-in-context block，写入需要 source refs 或 approval |
| `ArchivalDocument` / `ArchivalPassage` / `ArchivalMemory` | v3 archival layer 的文档、检索 passage 和长期记忆单元 |
| `ContextPackage` | 预算内上下文、源证据和诊断 metadata |

## 文档

- `docs/public-benchmark-diagnosis.md`：当前 benchmark 口径和 v2 smoke 结果。
- `docs/source-guide.md`：源码导读和模块边界。
- `docs/store-interface.md`：SQLite store schema 和迁移说明。
- `docs/known-issues.md`：当前接受的限制和下一步修复方向。
- `docs/agentic-memory-roadmap-zh.md`：后续路线图。
- `docs/agent-answer-diagnostics.md`：deterministic agent answer diagnostics。

## 快速开始

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync
uv run memoryos demo run
uv run memoryos demo agent
```

`demo agent` 使用确定性 fake/scripted 路径，不需要 API key。

## API 服务

```bash
uv run memoryos api --reload
```

或使用 Docker：

```bash
make up
```

主要接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/sessions` | 创建会话 |
| `POST` | `/sessions/{id}/ingest` | 摄入消息 |
| `POST` | `/sessions/{id}/page` | 触发分页 |
| `POST` | `/sessions/{id}/build-context` | 构建上下文包 |
| `POST` | `/memory/search` | 检索记忆 |
| `GET` | `/sessions/{id}/trace` | 查看审计 trace |
| `GET` | `/metrics` | Prometheus metrics |

## 配置

| 变量 | 用途 | 默认值 |
|---|---|---|
| `DATA_DIR` | SQLite DB、page mirror、trace 文件目录 | `.memoryos` |
| `MEMORYOS_RECALL_PIPELINE` | `v1` 或 `v2` recall path | `v1` |
| `MEMORYOS_MEMORY_ARCH` | `v1` 或 opt-in `v3` context composer | `v1` |
| `MEMORYOS_AGENT_KERNEL` | `off` 或 opt-in `v1` kernel | `off` |
| `MEMORYOS_PAGING_MODE` | `heuristic` 或 `llm` | `heuristic` |
| `ROT_SAFE_BUDGET` | 分页触发阈值 | `2400` |
| `HARD_LIMIT` | 上下文硬上限 | `8000` |
| `OPENAI_API_KEY` | OpenAI chat/embedding 实验 | unset |
| `DEEPSEEK_API_KEY` | DeepSeek chat 实验 | unset |
| `QDRANT_URL` | 可选 Qdrant ANN 后端 | unset |

默认路径离线可跑；真实 LLM、embedding 或 Qdrant 都需要显式配置。

## 评估

内置确定性 eval：

```bash
uv run memoryos eval run --baseline all
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

公开 benchmark smoke：

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge

MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Agent answer diagnostics：

```bash
uv run memoryos eval agent-answer
```

## 开发

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
make lint
```

## 原型边界

- LangGraph agent 是 demo，不是完整生产 agent runtime。
- 启发式分页和冲突检测是确定性 fallback，不是完整语义记忆模型。
- v2 当前优化 evidence recall/planning，answer quality 仍需后续阶段处理。
- v3 当前用于 benchmark 诊断和 layered composer 实验，默认启用已暂缓。
- FastAPI 无认证、限流、多租户或生产 ownership model。

## License

MIT
