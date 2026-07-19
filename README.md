# MemoryOS Lite

[![CI](https://github.com/iiyazu/MemryOS-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/iiyazu/MemryOS-lite/actions/workflows/ci.yml)
[License: MIT](LICENSE)

面向长对话的 eval-driven、source-attributed Agent/RAG memory prototype。

MemoryOS Lite 研究如何把长期对话中的记忆摄入、检索、上下文组装和来源证明做成可测、可追溯的闭环。它是原型，不是生产级 MemoryOS：当前服务没有完整的远程认证、多租户、限流或生产 ownership model。

## 当前基线

- 默认 `MEMORYOS_MEMORY_ARCH=v3`，使用 layered context composer；`v1` 仅作为显式兼容路径。
- 默认 `MEMORYOS_RECALL_PIPELINE=v2`，使用 episode-first evidence recall；可显式选择 `v1`。
- Agent kernel 默认关闭，仅通过 `MEMORYOS_AGENT_KERNEL=v1` 启用实验路径。
- SQLite 是权威存储；page/trace 文件和可选 Redis/Qdrant 都是派生或实验能力。
- 当前测试集合为 789 项；以新鲜命令结果而不是文档中的历史通过数判断状态。

```text
ingest(message)
  -> authoritative Message
  -> episode / page / item / archival derivatives

build_context(task)
  -> v3 ContextComposer
  -> v2 RecallPipeline
  -> bounded ContextPackage with source evidence and diagnostics
```

主要对象包括 `Message`、`Episode`、`MemoryPage`、`MemoryItem`、`CoreMemoryBlock`、`ArchivalDocument` / `ArchivalPassage` / `ArchivalMemory` 和 `ContextPackage`。

## 快速开始

```bash
# Local API, SQLite/BM25 and offline FastEmbed Hybrid retrieval.
uv sync --frozen --all-groups --extra full-local
uv run memoryos api --reload
```

`full-local` 保留 SQLite、BM25、FastEmbed、RRF、paging 和 external-governance，且不安装
远程 provider/graph stack。需要 LangGraph demo、远程 LLM/Qdrant 或公开 benchmark 时显式安装：

```bash
uv sync --frozen --all-groups --extra remote
uv run memoryos demo run
uv run memoryos demo agent
```

`demo agent` 使用确定性 scripted 路径，不需要 API key，但仍依赖可选的 LangGraph runtime。
缺少可选依赖时命令返回稳定 capability error；不会改变 SQLite authority 或离线 API 行为。

### 分发边界

`memoryos-lite` 核心包只包含 API、SQLite/BM25 和基础存储。`full-local` 是 xmuse
companion 使用的离线完整能力：FastEmbed、ONNX、RRF、paging 和 external-governance；
模型缓存由 companion 单独证明，不混入 Python 依赖包。`remote` 与 `benchmark` 则显式
安装 LangChain、LangGraph、Qdrant 和远程 provider 相关依赖。

在 Linux CPython 3.11 的冻结依赖测量中，移除 remote/benchmark 栈后（不含模型）Python
依赖 payload 从 286,143,166 B 降至 243,892,461 B，减少 42,250,705 B（14.76%）。该结果
没有达到 25% 的目标；保留的 ONNX/FastEmbed 是 full-local hybrid 检索的必要下限，因此
没有通过关闭 semantic retrieval 来换取更小资产。后续发行应继续报告组成与实测值，而非
把这个例外表述成达标。

主要 HTTP 接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/sessions` | 创建会话 |
| `POST` | `/sessions/{id}/ingest` | 摄入消息 |
| `POST` | `/sessions/{id}/page` | 显式分页 |
| `POST` | `/sessions/{id}/build-context` | 构建上下文包 |
| `POST` | `/archives/ingest` | 摄入可归因归档文档 |
| `POST` | `/archives/attachments` | 将归档关联到会话 |
| `POST` | `/memory/search` | 检索记忆 |
| `GET` | `/sessions/{id}/trace` | 查看调试 trace |
| `GET` | `/metrics` | Prometheus metrics |

## 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATA_DIR` | `.memoryos` | SQLite 与派生调试文件目录 |
| `MEMORYOS_MEMORY_ARCH` | `v3` | `v3` 或兼容 `v1` composer |
| `MEMORYOS_RECALL_PIPELINE` | `v2` | `v2` 或兼容 `v1` recall |
| `MEMORYOS_AGENT_KERNEL` | `off` | `off` 或实验 `v1` kernel |
| `MEMORYOS_PAGING_MODE` | `off` | 显式启用分页策略 |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | unset | 可选真实模型提供方 |
| `QDRANT_URL` | unset | 可选向量检索后端 |

完整设置以 `src/memoryos_lite/config.py` 为准。

## 验证

```bash
TMPDIR=/tmp uv run pytest -q
uv run ruff check .
uv run mypy src
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

公开 benchmark 需要本地数据集；命令和指标解释见 `docs/public-benchmark-diagnosis.md`。

## 文档

- `docs/source-guide.md`：当前源码与数据流。
- `docs/store-interface.md`：SQLite authority 和存储接口。
- `docs/specs/memoryos-service-contract.md`：HTTP 服务契约。
- `docs/archive-rag-boundary.md`：archive/source-proof 边界。
- `docs/known-issues.md`：当前限制。
- `docs/public-benchmark-diagnosis.md`：评估口径。
- `docs/agent-answer-diagnostics.md`：确定性回答诊断。
- `docs/agentic-memory-roadmap-zh.md`：当前研究路线。
- `docs/implementation-history-summary.md`：已收束的历史决策。

历史计划不属于运行时契约；需要追溯时使用 Git history。
