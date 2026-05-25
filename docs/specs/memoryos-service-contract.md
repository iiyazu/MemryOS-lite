# MemoryOS Lite — Service Contract Specification

Version: 0.1.0 | Date: 2026-05-25

## 一、概述

本文档定义 MemoryOS Lite 中间件对外暴露的服务契约。消费者包括 xmuse 控制面代理、
外部 RAG 应用和未来的 archive-rag 扩展。契约覆盖服务接口、HTTP API、错误语义和
扩展点。

---

## 二、服务接口契约 (MemoryOSService)

`MemoryOSService` 是唯一的服务门面。所有状态变更和查询必须经过此类。

| 方法 | 签名 | 保证 |
|------|------|------|
| `create_session` | `(title: str) -> Session` | 幂等创建，返回含 `ses_*` ID 的 Session |
| `ingest` | `(session_id, MessageCreate) -> IngestResponse` | 原子写入消息，返回 token 计数和分页信号 |
| `page` | `(session_id) -> MemoryPage \| None` | 触发分页压缩，无需压缩时返回 None |
| `build_context` | `(session_id, task, budget?, retrieval_query?, include_global_core?) -> ContextPackage` | 在 budget 内组装上下文包，不修改存储 |
| `search` | `(query, top_k, session_id?, limit?) -> list[SearchHit]` | 只读检索，跨会话或限定会话 |
| `search_items` | `(query, top_k, session_id?) -> list[SearchHit]` | 细粒度 MemoryItem 级检索 |

### 不变量

1. `ingest` 写入后立即可被同会话的 `build_context` / `search` 读取。
2. `build_context` 是纯读操作，不产生副作用。
3. 所有 ID 格式为 `{prefix}_{hex12}`，由服务端生成，客户端不可指定。
4. `session_id` 不存在时抛出 `ValueError`（HTTP 层映射为 404）。

---

## 三、HTTP API 契约

Base path: `/` | Content-Type: `application/json`

| Method | Path | Request Body | Response | 说明 |
|--------|------|-------------|----------|------|
| GET | `/health` | — | `{"status":"ok"}` | 存活探针 |
| POST | `/sessions` | `CreateSessionRequest` | `Session` | 创建会话 |
| POST | `/sessions/{id}/ingest` | `MessageCreate` | `IngestResponse` | 写入消息 |
| POST | `/sessions/{id}/page` | — | `MemoryPage \| null` | 触发分页 |
| POST | `/sessions/{id}/build-context` | `BuildContextRequest` | `ContextPackage` | 组装上下文 |
| POST | `/memory/search` | `SearchRequest` | `list[{page, score, reason}]` | 全局/会话检索 |
| GET | `/memory/pages/{id}` | — | `MemoryPage` | 加载单页 |
| GET | `/sessions/{id}/trace` | — | `list[TraceEvent]` | 调试追踪 |
| GET | `/metrics` | — | Prometheus text | 可观测性 |

### 核心 Schema 摘要

```jsonc
// CreateSessionRequest
{ "title": "string (default: Untitled session)" }

// MessageCreate
{ "role": "user|assistant|system|tool", "content": "string", "metadata": {} }

// IngestResponse
{ "message": Message, "should_page": bool, "session_token_count": int }

// BuildContextRequest
{ "task": "string", "budget": int|null, "retrieval_query": str|null,
  "include_global_core": bool }

// SearchRequest
{ "query": "string", "top_k": int, "session_id": str|null, "limit": int|null }
```

---

## 四、错误契约

| HTTP Status | 含义 | 重试语义 |
|-------------|------|----------|
| 200 | 成功 | — |
| 404 | session/page 不存在 | 不可重试，需先创建资源 |
| 422 | 请求体校验失败 (Pydantic) | 不可重试，修正请求后重发 |
| 500 | 内部错误（存储/LLM 超时） | 可重试，建议指数退避 max 3 次 |
| 503 | 服务不可用（启动中/依赖不可达） | 可重试，等待 health 恢复 |

### 错误响应格式

```json
{ "detail": "human-readable error message" }
```

### LLM 超时处理

`page` 和 `build_context` 可能触发 LLM 调用。超时由 `MEMORYOS_LLM_TIMEOUT_S`
控制（默认 30s）。超时时服务返回 500，消费者应重试或降级为无 LLM 路径。

---

## 五、中间件集成点

### xmuse 代理集成

xmuse slave 通过 HTTP 或直接 Python import 两种方式接入：

```python
# 方式 A: HTTP (推荐用于隔离 worktree)
import httpx
resp = httpx.post(f"{MEMORYOS_URL}/sessions/{sid}/build-context",
                  json={"task": "...", "budget": 4096})

# 方式 B: 进程内 (同 worktree)
from memoryos_lite.engine import MemoryOSService
svc = MemoryOSService()
pkg = svc.build_context(session_id=sid, task="...")
```

### 外部消费者集成

任何能发 HTTP JSON 请求的客户端均可接入。认证层当前不存在（原型阶段），
生产化时应在反向代理层添加 Bearer token 校验。

---

## 六、Archive-RAG 扩展点 (预留)

archive-rag 特性合并后将新增以下端点，当前为占位定义：

| Method | Path | 说明 |
|--------|------|------|
| POST | `/archives/ingest` | 上传文档到归档存储 |
| POST | `/sessions/{id}/attach-archive` | 将归档文档关联到会话 |
| POST | `/archives/search` | 跨归档语义检索 |

服务层将新增：

```python
class MemoryOSService:
    def archive_ingest(self, doc: ArchiveDocument) -> ArchiveRef: ...
    def attach_archive(self, session_id: str, archive_id: str) -> None: ...
    def archive_search(self, query: str, top_k: int) -> list[ArchiveHit]: ...
```

这些方法遵循与现有契约相同的错误语义和 ID 生成规则。

---

## 七、缓存透明性

### 原则

消费者不感知缓存层的存在。DerivedCache（Redis）是内部优化，不改变任何
API 响应的语义或结构。

### 保证

1. 缓存命中与缓存未命中返回相同的响应体（字段、值、顺序可能不同但语义等价）。
2. 缓存失效时自动回退到 SQLite 权威存储，不返回错误。
3. 无 cache-control 头暴露给消费者。
4. `ingest` 写入后缓存异步失效，后续读取保证一致性（read-after-write）。

### 内部分层（消费者无需关心）

```
Consumer -> API -> MemoryOSService -> [DerivedCache?] -> MemoryStore (SQLite)
```

---

## 八、版本演进策略

- 当前版本 `0.1.0`，API 无版本前缀（原型阶段）。
- 破坏性变更通过新端点路径引入，旧端点标记 deprecated 并保留至少一个版本周期。
- Schema 新增字段使用 Optional + default，保持向后兼容。
