# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

### Completed
- **M0**: Baseline frozen — 81 eval cases, 4 baselines (see `docs/baseline/results.md`)
- **M1**: Docker + docker-compose + Makefile + GitHub Actions CI + pre-commit
- **M2-A**: Postgres + pgvector + Alembic baseline migration (`0001_m2_baseline`)
- **M2-B**: Hybrid retrieval — `src/memoryos_lite/retrieval/` package (BM25 lexical + embedding cosine + RRF fusion) wired into `MemoryOSService`; embeddings computed on `page()` save; legacy `MemorySearcher` removed
- **M2-C**: DynamicBudget (adaptive context budget) + Prometheus observability (`/metrics` endpoint, 8 business metrics)
- **M3**: Conflict detection layer — `ConflictDetector` uses BM25 + negation heuristics to flag patches that contradict existing facts/decisions

### In Progress
- _(none — next milestone M4)_

### Next Steps (in order)
1. M4: LLM eval mode (GPT-as-judge for semantic accuracy)
2. M5: Performance / P95 latency optimization
3. M6: README rewrite + GitHub push + portfolio presentation

### Key Documents
- `memoryos-lite-design.md` — Full design rationale and 10-day milestone plan
- `docs/store-interface.md` — Authoritative DB schema, migration plan, env matrix
- `docs/baseline/results.md` — Frozen M0 benchmark numbers (the target to beat)

## Development Commands

```bash
# Core workflow
uv run pytest -q                           # 运行所有测试 (54 cases, ~60s)
uv run ruff check . && uv run ruff format --check .  # Lint + format check
uv run mypy src                            # 类型检查

# Convenience (via Makefile)
make test          # pytest
make lint          # ruff + mypy
make fmt           # auto-format
make up            # docker-compose up (app + postgres + redis)
make down          # docker-compose down
make eval          # 运行内置确定性 benchmark
make demo          # 端到端 demo
make api           # 本机跑 API（热重载）

# Direct CLI
uv run memoryos api --reload               # 启动 API 服务
uv run memoryos demo run                   # 运行端到端演示
uv run memoryos eval run --baseline all    # 运行基准测试
uv run alembic upgrade head                # 应用数据库迁移
```

使用 uv 管理依赖，要求 Python 3.11+。

## Architecture

面向长期运行 Agent 的上下文窗口记忆中间件。将 LLM 上下文窗口视为 RAM，通过分页机制将过期对话移入外部记忆页。

### 分层结构 (src/memoryos_lite/)

- **config.py** — Pydantic Settings，支持 DATABASE_URL / POSTGRES_* / SQLite 三级 DSN 解析
- **schemas.py** — 核心数据模型：Message、Session、MemoryPage、ContextPackage、MemoryPatch
- **store.py** — 混合持久化：Postgres+pgvector（生产）或 SQLite（开发）；`EmbeddingType` TypeDecorator 跨 dialect 透明处理 `vector(1536)` / JSON text；`content_json` 列为 DB-authoritative 内容源
- **engine.py** — 核心逻辑：ContextRotGuard、PagingAgent、ContextBuilder、MemoryOSService；检索通过 `retrieval.HybridSearcher` 注入；`page()` 保存后自动写 embedding（当 `EmbeddingClient` 可用时）
- **retrieval/** — 检索子包：
  - `base.py` — SearchHit, Searcher protocol, EmbeddingClient protocol, RRF fusion
  - `lexical.py` — BM25 via rank-bm25 (with query-vocab intersection gate to handle BM25Okapi's negative-IDF pathology on tiny corpora)
  - `embedding.py` — cosine similarity over stored embeddings
  - `hybrid.py` — RRF fusion of lexical + embedding, with graceful single-source fallback
  - `providers/fake.py` — 确定性 hash-based embedder (测试用)
  - `providers/openai.py` — OpenAI text-embedding-3-small wrapper
- **budget.py** — DynamicBudget：根据 session 状态（页面数、消息量、任务复杂度）自适应计算 context budget，范围 [rot_safe_budget, hard_limit]
- **conflict.py** — ConflictDetector：BM25 检索相关页面 + 否定模式匹配，检测 patch 与已有 facts/decisions 的语义冲突
- **observability.py** — Prometheus 业务指标（8 个 Counter/Histogram），通过 `/metrics` ASGI 端点暴露
- **graphs.py** — LangGraph 状态机：ingest → 条件分页 → build_context
- **tokenizer.py** — tiktoken 封装，带正则回退
- **api/app.py** — FastAPI REST 端点 + `/metrics` Prometheus endpoint
- **cli.py** — Typer CLI（`memoryos` 命令）
- **evals.py** — 内置基准测试框架（81 个确定性用例，多种 baseline）

### Infrastructure
- **Dockerfile** — multi-stage uv build, non-root, healthcheck via /health
- **docker-compose.yml** — app + pgvector/pgvector:pg16 + redis:7-alpine, healthchecks
- **Makefile** — 14 self-documenting targets (`make help`)
- **.github/workflows/ci.yml** — ruff + format-check + mypy + pytest on Python 3.11
- **.pre-commit-config.yaml** — ruff + trailing-whitespace + end-of-file + check-yaml
- **alembic/** — Alembic migrations; env.py reads DSN from Settings; revision 0001 is full baseline

### 核心抽象

- **MemoryOSService**（engine.py）：主入口，编排 ingest → page → build_context 流程
- **ContextRotGuard**：判断对话是否超出 token 预算，决定是否触发分页
- **PageDraftClient**（Protocol）：LLM 页面生成接口。OpenAIPageDraftClient 为具体实现
- **ContextPackage**：返回给调用方的组装上下文，包含 token 预算跟踪和来源追溯
- **Searcher**（Protocol, retrieval/base.py）：`search(pages, query, top_k) -> list[SearchHit]`
- **EmbeddingClient**（Protocol, retrieval/base.py）：`embed(text) -> list[float]`

### 数据流

消息被摄入 Session → ContextRotGuard 检查 token 预算是否超限 → PagingAgent 将旧消息压缩为 MemoryPage → ContextBuilder 在 token 预算内组装 ContextPackage（近期消息 + 检索到的记忆页）。

### Database

- **Postgres (prod)**: pgvector extension, `memory_pages.embedding vector(1536)`, `content_json` TEXT
- **SQLite (dev/test)**: embedding stored as JSON text, same ORM models via EmbeddingType TypeDecorator
- **Migration**: `alembic upgrade head` — single revision 0001 covers full schema
- **Tests**: use `create_all` on tmp_path SQLite (no migration needed)

## Configuration

关键配置（通过环境变量或 .env）：

| 变量 | 用途 | 默认值 |
|------|------|--------|
| DATABASE_URL | 完整 DSN（最高优先级） | — |
| POSTGRES_HOST/PORT/DB/USER/PASSWORD | 拼接 Postgres DSN | — |
| (无 Postgres 配置时) | 自动回退 SQLite | `.memoryos/memoryos.db` |
| OPENAI_API_KEY | LLM 分页 + embedding | — |
| MEMORYOS_MODEL | 分页用 LLM | gpt-4o-mini |
| MEMORYOS_EMBEDDING_MODEL | embedding 模型 | text-embedding-3-small |
| ROT_SAFE_BUDGET | 分页触发阈值 (tokens) | 2400 |
| HARD_LIMIT | 绝对上限 | 8000 |
| RECENT_MESSAGE_LIMIT | 保留近期消息数 | 8 |
| MEMORYOS_PAGING_MODE | heuristic / llm | heuristic |

## Linting

Ruff 规则：E, F, I, UP, B。行宽 100。目标 Python 3.11。mypy 忽略 pgvector 的 missing stubs。

## Conventions

- Commit messages: `type(scope): description` — e.g. `feat(M2-A): Postgres + pgvector + Alembic baseline`
- Branch: 当前在 `master`，计划 M6 推 GitHub 时切 `main`
- Tests: 所有 54 个测试必须在 SQLite 上通过；Postgres 验证通过 docker-compose
- CI: 每次 push 自动跑 ruff + format-check + mypy + pytest
