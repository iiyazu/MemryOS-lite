# MemoryOS Lite 源码导读

> 截至 M2-B 里程碑（2026-05-12），覆盖 M0 → M2-B 全部已完成工作。

---

## 一、项目定位

MemoryOS Lite 是面向长期运行 LLM Agent 的**上下文窗口记忆中间件**。核心隐喻：

> 把 LLM 上下文窗口当作 RAM，通过"分页"机制将过期对话压缩为外部记忆页，需要时再检索回来。

调用方（Agent 框架）只需与 `MemoryOSService` 交互三个动作：**ingest**（写入消息）→ **page**（触发分页压缩）→ **build_context**（组装上下文包）。

---

## 二、目录结构总览

```
src/memoryos_lite/
├── config.py            # 配置（45 行）
├── schemas.py           # 数据模型（184 行）
├── store.py             # 持久化层（363 行）
├── engine.py            # 核心业务逻辑（549 行）⭐
├── retrieval/           # 检索子系统（359 行）
│   ├── base.py          #   协议 + RRF 融合
│   ├── lexical.py       #   BM25 检索
│   ├── embedding.py     #   向量余弦检索
│   ├── hybrid.py        #   混合检索（RRF 融合）
│   └── providers/       #   Embedding 实现
│       ├── fake.py      #     确定性 hash embedder（测试）
│       └── openai.py    #     OpenAI text-embedding-3-small
├── graphs.py            # LangGraph 状态机（53 行）
├── tokenizer.py         # Token 计数（20 行）
├── api/app.py           # FastAPI REST 端点（105 行）
├── cli.py               # Typer CLI（128 行）
└── evals.py             # 基准测试框架（821 行）

tests/
├── conftest.py          # pytest fixture
├── test_engine.py       # 引擎单元测试（12 个）
├── test_evals.py        # 基准测试验证（27 个）
└── test_api.py          # API 集成测试

infra/
├── Dockerfile           # 多阶段 uv 构建
├── docker-compose.yml   # app + pgvector + redis
├── Makefile             # 14 个自文档化 target
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
└── alembic/             # 数据库迁移
    └── versions/0001_m2_baseline.py
```

---

## 三、核心数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        MemoryOSService                          │
│                                                                 │
│  ingest(msg)                                                    │
│    │                                                            │
│    ▼                                                            │
│  Store.add_message() ──► ContextRotGuard.should_page()          │
│                              │                                  │
│                    ┌─────────┴──────────┐                       │
│                    │ token_sum ≥ budget  │                       │
│                    └─────────┬──────────┘                       │
│                              ▼                                  │
│  page()                                                         │
│    │                                                            │
│    ▼                                                            │
│  PagingAgent.create_draft() ──► PageVerifier.verify()           │
│    │                                                            │
│    ▼                                                            │
│  Store.save_page() ──► _index_page_embedding()                  │
│                              │                                  │
│                              ▼                                  │
│                    EmbeddingClient.embed() → Store.set_page_embedding()
│                                                                 │
│  build_context(task, budget)                                    │
│    │                                                            │
│    ▼                                                            │
│  ContextBuilder.build()                                         │
│    ├── pin CORE_PROFILE pages                                   │
│    ├── select recent messages (within budget)                   │
│    └── HybridSearcher.search() → rank & fill remaining budget   │
│              │                                                  │
│              ├── LexicalSearcher (BM25)                         │
│              └── EmbeddingSearcher (cosine) ──► RRF fusion      │
│                                                                 │
│    ▼                                                            │
│  ContextPackage (返回给调用方)                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、逐模块详解

### 4.1 config.py — 配置中心

```python
class Settings(BaseSettings):
    # DSN 三级优先：DATABASE_URL > POSTGRES_* 拼接 > SQLite 回退
    database_url: str | None = None
    postgres_host: str | None = None
    ...
    rot_safe_budget: int = 2_400      # 分页触发阈值
    hard_limit: int = 8_000           # 绝对上限
    recent_message_limit: int = 8     # 保留近期消息数
    memoryos_paging_mode: str = "heuristic"  # heuristic | llm
```

**设计要点**：`sqlite_url` 属性实现了三级 DSN 解析，开发时零配置即可用 SQLite，生产切 Postgres 只需设环境变量。

---

### 4.2 schemas.py — 数据模型

| 模型 | 用途 |
|------|------|
| `Message` | 单条对话消息，带 token_count |
| `Session` | 会话容器 |
| `MemoryPageDraft` | PagingAgent 输出的草稿 |
| `MemoryPage` | 持久化的记忆页（继承 Draft，加 id/version/时间戳） |
| `MemoryPatch` | 对已有页的修改操作 |
| `ContextPackage` | build_context 的返回值，包含 token 预算审计 |
| `EvalCase` | 基准测试用例定义 |

**ID 生成**：`new_id("page")` → `page_43b3d2dda7e0`（前缀 + uuid4 前 12 位 hex）。

**PageType 枚举**：`CORE_PROFILE`（长期稳定信息）、`TASK_STATE`（当前任务）、`DECISION`（决策记录）、`SOURCE_SUMMARY`（对话摘要）、`TOOL_OBSERVATION`（工具输出）。

---

### 4.3 store.py — 持久化层

**双 dialect 透明**：同一套 SQLAlchemy ORM 模型同时支持 Postgres（pgvector）和 SQLite（JSON text）。关键是 `EmbeddingType` TypeDecorator：

```python
class EmbeddingType(TypeDecorator):
    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(1536))
        return dialect.type_descriptor(Text())
```

**核心方法**：

| 方法 | 作用 |
|------|------|
| `save_page(page)` | 写 JSON 文件 + DB 记录 |
| `set_page_embedding(page_id, vec)` | 更新 embedding 列 |
| `get_page_embeddings(page_ids)` | 批量查询 embedding（检索用） |
| `list_pages(session_id)` | 从 DB content_json 反序列化 |
| `add_trace(event)` | 写 trace 到 DB + JSONL 文件 |

**文件 + DB 双写**：页面内容同时存在 `pages/{session_id}/{page_id}.json` 和 `content_json` 列。DB 为权威源（`load_page` 优先读 `content_json`），文件用于人工检查。

---

### 4.4 engine.py — 核心引擎 ⭐

这是最重要的文件（549 行），包含 5 个核心类：

#### ContextRotGuard
```python
def should_page(self, messages) -> bool:
    return sum(m.token_count for m in messages) >= self.settings.rot_safe_budget
```
简单阈值判断。当会话 token 总量超过 `rot_safe_budget`（默认 2400），触发分页。

#### PagingAgent
两种模式：
- **heuristic**（默认）：规则提取 facts/decisions/open_questions，生成 `MemoryPageDraft`
- **llm**：调用 OpenAI structured output 生成草稿，失败时回退 heuristic

启发式逻辑：扫描消息内容，按关键词分类（"决定/选择/不做" → decisions，"?/？/如何" → open_questions，其余 → facts）。

#### ContextBuilder
在 token 预算内组装 `ContextPackage`：
1. 固定 pin `CORE_PROFILE` 页
2. 从后往前选近期消息
3. 用 `HybridSearcher` 检索相关记忆页填充剩余预算
4. 超预算的页记录到 `dropped_pages`（审计用）

#### MemoryOSService
主入口，编排所有组件。构造时：
- 构建 `HybridSearcher`（LexicalSearcher + 可选 EmbeddingSearcher）
- 当 `OPENAI_API_KEY` 存在时自动启用 `OpenAIEmbeddingClient`
- `page()` 保存后自动调用 `_index_page_embedding()` 写入向量

#### _index_page_embedding
```python
def _index_page_embedding(self, page):
    if self.embedding_client is None:
        return
    text = " ".join([page.title, page.summary, *page.facts, ...])
    vector = self.embedding_client.embed(text)
    self.store.set_page_embedding(page.id, vector)
```
失败时 trace `embedding_failed`，不阻塞主流程。

---

### 4.5 retrieval/ — 检索子系统

#### 协议层 (base.py)

```python
class Searcher(Protocol):
    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]: ...

class EmbeddingClient(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

`reciprocal_rank_fusion()` 实现 Cormack et al. RRF（k=60），输出带 `"rrf lexical=0.0164 embedding=0.0152"` 格式的 reason 字段。

#### LexicalSearcher (lexical.py)

- **分词器**：Latin 空格分词 + CJK 单字 + CJK 双字（bigram），支持中英混合查询
- **排序**：BM25Okapi（rank-bm25 库）
- **小语料库修复**：BM25Okapi 在 ≤2 文档时 IDF 为负，改用 query-vocab ∩ doc-vocab 判断是否有匹配，而非 `score > 0` 过滤

#### EmbeddingSearcher (embedding.py)

从 store 批量取 embedding → 计算 query embedding → 余弦相似度排序。纯 Python 实现（M5 再迁移到 pgvector KNN）。

#### HybridSearcher (hybrid.py)

```python
class HybridSearcher:
    def search(self, pages, query, top_k=5):
        lexical_hits = self.lexical.search(pages, query, top_k=per_source_k)
        embedding_hits = self.embedding.search(...) if self.embedding else []
        # 单源或双源都走 RRF
        return reciprocal_rank_fusion(ranked_lists, k=self.rrf_k, top_k=top_k)
```

优雅降级：无 embedding client 时退化为纯 BM25（通过 RRF 单源列表）。

#### Providers

| Provider | 用途 | 维度 |
|----------|------|------|
| `DeterministicEmbeddingClient` | 测试：SHA-256 hash → 1536 维 L2 归一化向量 | 1536 |
| `OpenAIEmbeddingClient` | 生产：text-embedding-3-small | 1536 |

---

### 4.6 graphs.py — LangGraph 状态机

```
ingest ──[should_page?]──► page ──► build_context ──► END
              │
              └──────────────────► build_context ──► END
```

薄封装层，将 `MemoryOSService` 的三步流程编排为 LangGraph 图。供 CLI demo 和未来 Agent 集成使用。

---

### 4.7 api/app.py — REST API

| 端点 | 方法 | 作用 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/sessions` | POST | 创建会话 |
| `/sessions/{id}/ingest` | POST | 写入消息 |
| `/sessions/{id}/page` | POST | 触发分页 |
| `/sessions/{id}/build-context` | POST | 组装上下文 |
| `/memory/search` | POST | 检索记忆页 |
| `/memory/pages/{id}` | GET | 加载单页 |
| `/sessions/{id}/trace` | GET | 查看 trace 日志 |

---

### 4.8 evals.py — 基准测试框架

821 行，包含 81 个确定性 eval case 和 4 种 baseline：

| Baseline | 策略 |
|----------|------|
| `naive_summary` | 全量拼接，超限截断 |
| `sliding_window` | 滑动窗口保留最近 N 条 |
| `vector_rag` | BM25 检索 top-k 消息 |
| `memoryos_lite` | 完整 ingest → page → build_context 流程 |

评估指标：`answer_accuracy`（expected/forbidden facts 命中）、`source_accuracy`（来源追溯正确率）、`context_tokens`（token 效率）。

---

### 4.9 基础设施

| 文件 | 要点 |
|------|------|
| `Dockerfile` | 多阶段 uv 构建，non-root，`/health` healthcheck |
| `docker-compose.yml` | app + pgvector:pg16 + redis:7-alpine，带 healthcheck 依赖 |
| `Makefile` | `make test/lint/fmt/up/down/eval/demo/api` 等 14 个 target |
| `ci.yml` | Python 3.11，ruff + format-check + mypy + pytest |
| `alembic/` | 单 revision `0001_m2_baseline` 覆盖全 schema |

---

## 五、里程碑回顾

| 里程碑 | 交付物 | 关键 commit |
|--------|--------|-------------|
| **M0** | 81 eval cases + 4 baselines 冻结 | — |
| **M1** | Docker + CI + Makefile + pre-commit | — |
| **M2-A** | Postgres + pgvector + Alembic migration | `0996404` |
| **M2-B** | retrieval 子包 + HybridSearcher 接入 + embedding-on-save | `7690553`, `3615395`, `5e6c61e` |

---

## 六、阅读建议

1. **入门**：从 `schemas.py` 开始，理解 Message → MemoryPage → ContextPackage 的数据流转
2. **核心逻辑**：读 `engine.py` 的 `MemoryOSService` 类，跟踪 `ingest → page → build_context` 三步
3. **检索细节**：`retrieval/base.py`（协议 + RRF）→ `lexical.py`（BM25）→ `hybrid.py`（融合）
4. **持久化**：`store.py` 的 `EmbeddingType` 和双 dialect 设计
5. **测试**：`test_engine.py` 的 12 个测试覆盖了所有核心路径，是理解行为的最佳文档
6. **基准**：`evals.py` 的 `_build_eval_cases()` 定义了 81 个 case，展示了系统要解决的真实场景

---

## 七、关键设计决策

| 决策 | 理由 |
|------|------|
| SQLite 开发 / Postgres 生产 | 零配置本地开发 + 生产级向量检索 |
| BM25 + Embedding RRF 融合 | 中文 BM25 覆盖精确匹配，embedding 覆盖语义相似 |
| Embedding 可选（graceful degradation） | 无 API key 时纯 BM25 仍可用 |
| Heuristic 分页为默认 | 离线可用、确定性、零成本；LLM 模式为可选增强 |
| content_json 为 DB 权威源 | 避免文件系统与 DB 不一致 |
| 每次 search 重建 BM25 索引 | M2 语料规模（≤百页）下开销可忽略，M5 再优化 |
| Query-vocab 交集替代 score>0 过滤 | 修复 BM25Okapi 小语料库 IDF 负值问题 |
