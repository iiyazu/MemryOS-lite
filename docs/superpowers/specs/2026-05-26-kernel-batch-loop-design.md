# Kernel Batch Loop (v1) — Design Spec

## Problem

MemoryOS v3 architecture has a core memory layer (`CoreMemoryBlock`) that is never populated. No component actively decides "this information is worth remembering long-term." The result: `build_context()` always returns an empty core layer, losing user preferences, identity, and important decisions across conversation windows.

## Solution

A lightweight kernel that runs after every N messages, makes a single LLM call to decide what to remember, and writes to core memory / archival storage.

## Architecture

```
ingest(session_id, message)
  → store message
  → len(messages) % KERNEL_BATCH_SIZE == 0?
    → yes: kernel_step(session_id)
    → no: return

kernel_step(session_id):
  1. batch = last KERNEL_BATCH_SIZE messages from store
  2. core_snapshot = render_core_memory_blocks()
  3. prompt = system_prompt + core_snapshot + batch transcript
  4. response = llm.invoke(prompt)  # single DeepSeek call
  5. actions = parse_json(response)  # 3-tier fallback
  6. for action in actions: execute(action, source_refs=batch_message_ids)
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MEMORYOS_KERNEL_BATCH` | `off` | `off` / `v1` |
| `MEMORYOS_KERNEL_BATCH_SIZE` | `12` | Messages per batch trigger |
| `MEMORYOS_KERNEL_CORE_TOKEN_CAP` | `1500` | Max total tokens across all core blocks |

## Actions

| Action | Target | Fields |
|--------|--------|--------|
| `core_memory_append` | CoreMemoryBlock | `label`, `content` |
| `core_memory_replace` | CoreMemoryBlock | `label`, `old_content`, `new_content` |
| `core_memory_delete` | CoreMemoryBlock | `label` |
| `archival_write` | ArchivalMemory | `content`, `memory_type` |
| `noop` | — | — |

## Core Memory Block Schema

Pre-seeded canonical blocks (created on first kernel_step if absent):

| Label | Purpose | limit_tokens |
|-------|---------|--------------|
| `persona` | Who the user is (name, role, background) | 300 |
| `preferences` | How they like things (tools, style, habits) | 300 |
| `context` | Current life situation (location, projects, goals) | 400 |
| `instructions` | How they want the agent to behave | 200 |

The kernel can also create custom-labeled blocks for domain-specific content.

## LLM Prompt

```
你是 MemoryOS 的记忆管理 kernel。分析最近的对话，决定是否需要更新长期记忆。

## 当前 Core Memory
{core_snapshot}

## 最近对话
{batch_transcript}

## 规则
- 只记录对未来对话有价值的信息（偏好、身份、重要决策、关键事实）
- 已有相同信息 → 不重复写入
- 信息过时（用户说了新的）→ core_memory_replace
- 闲聊、确认语、纯技术输出 → noop
- 具体项目细节、会议结论、有时间性的事件 → archival_write
- label 必须是: persona / preferences / context / instructions 或自定义

返回 JSON（无 markdown fencing）:
{"actions": [{"type": "core_memory_append", "label": "...", "content": "..."}, ...]}
如果无需操作: {"actions": [{"type": "noop"}]}
```

## Source Provenance

Kernel auto-constructs `SourceRef` from batch message IDs. LLM does not handle attribution.

```python
source_refs = [
    SourceRef(source_id=msg.id, source_type="message")
    for msg in batch_messages
]
```

## JSON Parsing (3-tier fallback)

1. Extract from ```json fences via regex
2. Attempt `json.loads()` on raw response
3. If all fail → treat as noop, log raw response as trace event

## Error Handling

- `kernel_step()` wrapped in try/except — never blocks ingest
- Each action executed independently; one failure doesn't abort others
- Failed actions logged as trace events with error details
- Token cap enforcement: if append would exceed cap, truncate or skip

## Token Cap Enforcement

Before executing `core_memory_append`:
```python
current_total = sum(block.current_tokens for block in live_blocks)
if current_total + new_tokens > KERNEL_CORE_TOKEN_CAP:
    # skip or truncate
```

## Integration Points

| Component | Change |
|-----------|--------|
| `engine.py` ingest() | Add kernel trigger check at end |
| `config.py` | Add 3 new settings |
| `kernel_loop.py` (new) | KernelBatchLoop class |
| `core_memory.py` | No changes (existing API sufficient) |
| `context_composer.py` | No changes (already reads core blocks) |

## Eval Plan

### Regression guard
- LME 20 cases + LoCoMo 20 cases with kernel enabled
- Score must not drop below 100% / 70%

### Core memory specific cases (new)
1. **Preference recall after rotation** — user states preference early, verify it persists via core memory after 24+ messages
2. **Update propagation** — "I moved to Beijing" after "I live in Shanghai", verify replace fires
3. **Noise filtering** — 12 messages of routine work, verify noop
4. **Multi-session stability** — core memory persists across sessions
5. **Token cap** — repeated appends stay within limit

## File Changes

| File | Type |
|------|------|
| `src/memoryos_lite/kernel_loop.py` | New |
| `src/memoryos_lite/engine.py` | Modify (ingest trigger) |
| `src/memoryos_lite/config.py` | Modify (3 settings) |
| `tests/test_kernel_loop.py` | New |
| `benchmarks/core_memory/` | New directory |
