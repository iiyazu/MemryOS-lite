# MemoryOS Lite

[![CI](https://github.com/iiyazu/MemryOS-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/iiyazu/MemryOS-lite/actions/workflows/ci.yml)
[License: MIT](LICENSE)

面向长对话的 eval-driven、source-attributed Agent/RAG memory prototype。

MemoryOS Lite 研究如何把长期对话中的记忆摄入、检索、上下文组装和来源证明做成可测、可追溯的闭环。它是原型，不是生产级 MemoryOS：当前服务没有完整的远程认证、多租户、限流或生产 ownership model。

## 当前基线

- 默认 `MEMORYOS_MEMORY_ARCH=v3`，使用 layered context composer；`v1` 仅作为显式兼容路径。
- 默认 `MEMORYOS_RECALL_PIPELINE=v2`，使用 episode-first evidence recall；可显式选择 `v1`。
- Agent kernel 默认关闭；`MEMORYOS_AGENT_KERNEL=external` 时本服务只产出带来源的维护建议（`/sessions/{id}/advisories`），由宿主 agent 决定是否采纳。
- 记忆策展（curator）默认关闭；`MEMORYOS_CURATOR_ENABLED=true` 时后台 worker 从消息流抽取带来源证明的持久记忆，并通过 `/sessions/{id}/advisories?version=2`（`memoryos_external_advisories/v2`）暴露，同时抑制启发式维护建议。每条记忆的引文必须是原消息的逐字子串，否则拒收；默认由 `topic_key` + 版本号确定性汇总新旧版本，LLM 只输出 add/noop。
- 模块会话（`scope: {"type": "module", "id": ...}`）面向"一个 Agent 负责一个模块"的宿主：摄入带类型的活动，策展出模块决定和教训（错题本），并按需返回确定性的续命包 `module_pack/v1`，见下文"模块记忆"。
- SQLite 是权威存储；page/trace 文件和可选 Redis/Qdrant 都是派生或实验能力。
- 以新鲜命令结果而不是文档中的历史通过数判断状态。

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
uv sync --frozen --no-dev --extra full-local
uv run --no-sync memoryos api --reload
```

`full-local` 保留 SQLite、BM25、FastEmbed、RRF、paging 和 external-governance，且不安装
远程 provider/graph stack。需要 LangGraph demo、远程 LLM/Qdrant 或公开 benchmark 时显式安装：

```bash
uv sync --frozen --no-dev --extra remote
uv run --no-sync memoryos demo run
```

`demo run` 依赖可选的 LangGraph runtime；缺少可选依赖时命令返回稳定 capability
error，不会改变 SQLite authority 或离线 API 行为。

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
| `POST` | `/sessions` | 创建会话；可带 `scope` 创建模块会话 |
| `POST` | `/sessions/{id}/ingest` | 摄入消息；`metadata` 按 `memoryos_activity/v1` 校验，不合规返回 422 |
| `POST` | `/sessions/{id}/page` | 显式分页 |
| `POST` | `/sessions/{id}/build-context` | 构建上下文包；`response_profile: "module_pack/v1"` 返回续命包 |
| `POST` | `/archives/ingest` | 摄入可归因归档文档 |
| `POST` | `/archives/attachments` | 将归档关联到会话 |
| `POST` | `/memory/search` | 检索记忆 |
| `GET` | `/sessions/{id}/trace` | 查看调试 trace |
| `GET` | `/sessions/{id}/advisories` | 维护建议；`?version=2` 返回策展记忆（v2），`?version=3` 返回带 scope 的策展记忆（v3） |
| `GET` | `/metrics` | Prometheus metrics |

### 模块记忆（错题本与续命包）

模块会话只在 `POST /sessions` 时通过 `scope: {"type": "module", "id": "<module_id>"}`
声明；MemoryOS 只保存并回显 scope，不解释模块归属。

**活动元数据（`memoryos_activity/v1`）**：`metadata.activity_type` 取 `message`、
`review_objection`、`gate_failure` 或 `contract_revision`。任何会话都拒收未知类型；模块会话
还要求 `activity_type`、等于 scope id 的 `module_id`、非负整数 `activity_seq`，
`contract_revision` 另需 `contract_id` 与正整数 `contract_version`。门禁日志全文入库，
curator 提示词只截取开头和结尾。

**错题本**：模块会话里的教训（`memory_kind=lesson`）必须至少引用一条 `review_objection`
或 `gate_failure`，否则拒收。同一错误再次出现时，curator 用同一个 `topic_key` 重新 add 并
引用新消息；`occurrences` 统计新引用的复核意见和门禁失败消息数（按消息 id 去重，普通消息
不计入）。记忆版本号取消息的 `activity_seq`。

**续命包（`module_pack/v1`）**：会话被压缩、进程被杀或重启后，负责人调用
`build-context` 并指定 `response_profile: "module_pack/v1"`（`budget` 默认 1500，上限
4000）。包体由附在模块会话上的归档文档确定性拼装，不做检索、不调用 LLM：

- `contracts`：每个 `contract_id` 只取最新版本，只给指针（id、版本、sha256、一行摘要），
  全文由宿主自己读取；
- `lessons`：每个 `topic_key` 只取最高版本，按 `occurrences` 从多到少、再按新旧排序；
- `decisions`：决定和事实，每个 `topic_key` 只取最高版本，从新到旧。

每条都是可复证的归档文档；预算放不下的条目计入 `omitted`。非模块会话请求该 profile 返回
422。`possible_conflict_with`（不同 key 但文本相近的条目）默认关闭，见
`MEMORYOS_MODULE_PACK_CONFLICT_THRESHOLD`。

**advisories v3**（`memoryos_external_advisories/v3`）：在 v2 的基础上携带 scope，模块会话
的教训和决定分别以 `module_lesson`、`module_decision` 暴露；示例见
`docs/contracts/memoryos_external_advisories_v3.example.json`。

## 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATA_DIR` | `.memoryos` | SQLite 与派生调试文件目录 |
| `MEMORYOS_MEMORY_ARCH` | `v3` | `v3` 或兼容 `v1` composer |
| `MEMORYOS_RECALL_PIPELINE` | `v2` | `v2` 或兼容 `v1` recall |
| `MEMORYOS_AGENT_KERNEL` | `off` | `off`，或 `external` 维护建议模式 |
| `MEMORYOS_PAGING_MODE` | `off` | 显式启用分页策略 |
| `MEMORYOS_CURATOR_ENABLED` | `false` | 启用 LLM 记忆策展与后台 worker |
| `MEMORYOS_CURATOR_WINDOW_MESSAGES` | `12` | 每次策展窗口的消息数 |
| `MEMORYOS_CURATOR_IDLE_FLUSH_S` | `20.0` | 不足一窗时的空闲刷新等待秒数 |
| `MEMORYOS_CURATOR_POLL_S` | `2.0` | 后台 worker 轮询间隔 |
| `MEMORYOS_CURATOR_MAX_ACTIVE_IN_PROMPT` | `40` | 提示词中携带的活跃记忆上限 |
| `MEMORYOS_CURATOR_CONSOLIDATION` | `deterministic` | `deterministic`：按 `topic_key` 保留最新版本；`llm`：早期由 LLM 指定被取代记忆的流程 |
| `MEMORYOS_MODULE_PACK_CONFLICT_THRESHOLD` | unset | 设为 FastEmbed 余弦阈值后，`module_pack/v1` 标注疑似冲突；默认关闭（RoomMem 上全部是误报） |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `OPENCODE_API_KEY` | unset | 可选真实模型提供方；`MEMORYOS_LLM_PROVIDER=opencode` 走 OpenCode Go（默认 `muse-spark-1.3-contributor`，Responses API），目前只用于 curator 与 RoomMem |
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

记忆策展有两套自带数据集的评测，默认调用配置的真实模型（`--fake-llm` 用确定性替身跑通流程）：

```bash
# RoomMem：多 Room 记忆。split dev=rm01-06, test=rm07-12, trap=rm13-16
uv run memoryos eval roommem --split dev --arm raw_project --arm curated --arm oracle \
  --embedding fastembed --out artifacts/roommem
# ModuleMem：模块续命包与错题本。split dev=mm01-04, test=mm05-08
uv run memoryos eval modulemem --split dev --arm pack --arm recent --arm full_history \
  --embedding fastembed --out artifacts/modulemem
```

RoomMem 的 arm 有 `raw`、`raw_project`、`oracle`、`curated`、`full_context`；ModuleMem 的
arm 有 `pack`、`oracle_pack`、`recent`、`retrieval`、`full_history`。`--answerer-llm`、
`--judge-llm`、`--curator-llm` 接受 `provider:model[@wire]`。结果写入 `--out` 下的
`summary.md`。

## 文档

- `docs/source-guide.md`：当前源码与数据流。
- `docs/store-interface.md`：SQLite authority 和存储接口。
- `docs/specs/memoryos-service-contract.md`：HTTP 服务契约。
- `docs/archive-rag-boundary.md`：archive/source-proof 边界。
- `docs/known-issues.md`：当前限制。
- `docs/public-benchmark-diagnosis.md`：评估口径。
- `docs/agentic-memory-roadmap-zh.md`：当前研究路线。
- `docs/implementation-history-summary.md`：已收束的历史决策。

历史计划不属于运行时契约；需要追溯时使用 Git history。
