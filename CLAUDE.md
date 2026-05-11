# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
uv run pytest                              # 运行所有测试
uv run pytest tests/test_engine.py -k "test_name"  # 运行单个测试
uv run ruff check .                        # Lint 检查
uv run ruff format .                       # 格式化
uv run mypy src                            # 类型检查
uv run memoryos api --reload               # 启动 API 服务
uv run memoryos demo run                   # 运行端到端演示
uv run memoryos eval run --baseline all    # 运行基准测试
```

使用 uv 管理依赖，要求 Python 3.11+。

## Architecture

面向长期运行 Agent 的上下文窗口记忆中间件。将 LLM 上下文窗口视为 RAM，通过分页机制将过期对话移入外部记忆页。

### 分层结构 (src/memoryos_lite/)

- **config.py** — Pydantic Settings，支持环境变量（`get_settings()` 单例）
- **schemas.py** — 核心数据模型：Message、Session、MemoryPage、ContextPackage、MemoryPatch
- **store.py** — 混合持久化：SQLite（SQLAlchemy ORM）存储关系数据 + JSON 文件存储页面内容
- **engine.py** — 核心逻辑：ContextRotGuard（触发分页）、PagingAgent（创建页面）、MemorySearcher（BM25 检索）、ContextBuilder（token 预算组装）、MemoryOSService（主编排器）
- **graphs.py** — LangGraph 状态机：ingest → 条件分页 → build_context
- **tokenizer.py** — tiktoken 封装，带正则回退
- **api/app.py** — FastAPI REST 端点
- **cli.py** — Typer CLI（`memoryos` 命令）
- **evals.py** — 内置基准测试框架（81 个确定性用例，多种 baseline）

### 核心抽象

- **MemoryOSService**（engine.py）：主入口，编排 ingest → page → build_context 流程。
- **ContextRotGuard**：判断对话是否超出 token 预算，决定是否触发分页。
- **PageDraftClient**（Protocol）：LLM 页面生成接口。OpenAIPageDraftClient 为具体实现。
- **ContextPackage**：返回给调用方的组装上下文，包含 token 预算跟踪和来源追溯。

### 数据流

消息被摄入 Session → ContextRotGuard 检查 token 预算是否超限 → PagingAgent 将旧消息压缩为 MemoryPage → ContextBuilder 在 token 预算内组装 ContextPackage（近期消息 + 检索到的记忆页）。

## Configuration

关键配置（通过环境变量或 .env）：`MEMORYOS_DATA_DIR`、`MEMORYOS_MODEL`、`MEMORYOS_EMBEDDING_MODEL`、`MEMORYOS_ROT_SAFE_BUDGET`、`MEMORYOS_HARD_LIMIT`、`MEMORYOS_RECENT_MESSAGE_LIMIT`。

## Linting

Ruff 规则：E, F, I, UP, B。行宽 100。目标 Python 3.11。
