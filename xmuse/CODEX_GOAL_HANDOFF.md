# Codex 监控交接文档

> 生成时间: 2026-05-29 00:30 Asia/Shanghai
> 用途: 给 Codex /goal 提供完整上下文
> 有效期: 10 小时

## 1. 项目概况

仓库: `/home/iiyatu/projects/python/memoryOS`
分支: `feat/phase-2.5-3-retrieval-agent`
平台: xmuse — 自主软件开发控制平面

核心循环:
```
chat → proposal → resolution → projection → feature_lanes.json → platform_runner → execute-god → review-god → gate → merge
```

## 2. 当前运行状态

| 组件 | 状态 |
|---|---|
| platform_runner | PID ~20940, codex-only, max-concurrent=8, auto-evolve, decomposer=peer-chat |
| GOD runtime | codex gpt-5.5 |
| 非 GOD runtime | codex gpt-5.4 (peer-chat decomposer + chat-driver) |
| Claude CLI | 暂不可用（CC API 问题），不要使用 |
| MCP server | 端口 8100 |
| Chat API | 端口 8201 |
| Dashboard API | 端口 8200 |
| Lane 状态 | done=80, merged=39, failed=13, exec_failed=4, gate_failed=3, gated=1, dispatched=1 |

## 3. Phase 1 任务：注入 spec 给 xmuse

### 目标

将 `docs/superpowers/specs/2026-05-29-orchestrator-controller-decoupling-design.md` 的 Steps 4-7 通过 xmuse 的标准 chat→proposal→lanes 路径注入执行。

### 步骤

1. 确保 chat_api 在线（端口 8201）。如果没在线：
   ```bash
   nohup uv run python xmuse/chat_api.py > /tmp/chat_api.log 2>&1 &
   ```

2. 确保 platform_runner 在线。如果没在线或已过期：
   ```bash
   # 先杀旧的
   pkill -TERM -f platform_runner 2>/dev/null; sleep 3; pkill -9 -f platform_runner 2>/dev/null
   # 重启（10h 匹配 goal 时长）
   nohup env XMUSE_GOD_RUNTIME=codex XMUSE_CODEX_MODEL=gpt-5.5 XMUSE_NON_GOD_CODEX_MODEL=gpt-5.4 XMUSE_PEER_CHAT_RUNTIME=codex XMUSE_CHAT_DRIVER_RUNTIME=codex uv run python xmuse/platform_runner.py --max-hours 10 --max-concurrent 8 --auto-evolve --decomposer peer-chat > /tmp/runner.log 2>&1 &
   ```

3. 找到或创建一个 chat conversation：
   ```bash
   curl -s http://localhost:8201/api/chat/conversations | python3 -m json.tool | head -20
   ```
   如果没有 conversation，创建一个：
   ```bash
   curl -s -X POST http://localhost:8201/api/chat/conversations -H 'Content-Type: application/json' -d '{"title": "C-phase steps 4-7 injection"}'
   ```

4. 发送注入消息（用实际 conversation_id 替换 `{CID}`）：
   ```bash
   curl -s -X POST http://localhost:8201/api/chat/conversations/{CID}/messages \
     -H 'Content-Type: application/json' \
     -d '{
       "author": "Operator",
       "role": "human",
       "content": "@architect-god 请读 docs/superpowers/specs/2026-05-29-orchestrator-controller-decoupling-design.md Section 8.4-8.7，将 Steps 4-7 拆解为可并行执行的 feature lanes。依赖关系：Step4(projection) 和 Step6-adapters 可并行；Step5(execution) 依赖 Step4；Step6 剩余依赖 adapters；Step7(清理) 依赖 Step5+Step6 全部。每条 lane prompt 必须自包含并引用 spec section 路径。gate_profiles: [\"xmuse-core\"]。"
     }'
   ```

5. 等待 chat-driver tick 触发 architect-god 回复（约 60-120s）。检查回复：
   ```bash
   curl -s http://localhost:8201/api/chat/conversations/{CID}/messages | python3 -c "import sys,json;msgs=json.load(sys.stdin);[print(f'{m[\"author\"]}: {m[\"content\"][:200]}') for m in msgs[-5:]]"
   ```

6. 如果 architect-god 产出了 proposal（回复里包含 `[proposal]`），approve 它：
   ```bash
   # 先找 proposal id
   curl -s http://localhost:8201/api/chat/proposals | python3 -c "import sys,json;ps=json.load(sys.stdin);[print(f'{p[\"id\"]}: {p[\"summary\"][:100]}') for p in ps if p.get('status')=='pending']"
   # approve
   curl -s -X POST http://localhost:8201/api/chat/proposals/{PROPOSAL_ID}/approve
   ```

7. Proposal approve 后，projection 会自动将 lanes 写入 `feature_lanes.json`，runner 会自动 dispatch。

### 验证注入成功

```bash
python3 -c "
import json
d=json.load(open('xmuse/feature_lanes.json'))
new=[l for l in d['lanes'] if isinstance(l,dict) and 'projection' in l.get('feature_id','') or 'execution' in l.get('feature_id','') or 'controller' in l.get('feature_id','')]
for l in new[-10:]:
    print(f\"  {l.get('status'):10s} {l.get('feature_id')[:80]}\")
"
```

## 4. Phase 2 任务：每 20 分钟监控

### 检查项

每 20 分钟执行以下检查：

```bash
# 1. runner 是否存活
pgrep -af platform_runner || echo "RUNNER DEAD"

# 2. lane 状态概览
python3 -c "
import json
from collections import Counter
d=json.load(open('xmuse/feature_lanes.json'))
c=Counter(l.get('status','?') for l in d['lanes'] if isinstance(l,dict))
for k,v in c.most_common(): print(f'  {k}: {v}')
active=[l for l in d['lanes'] if isinstance(l,dict) and l.get('status') in ('dispatched','executed','gated','reviewed')]
print(f'active: {len(active)}')
for l in active:
    print(f\"    {l.get('status'):10s} {l.get('feature_id')[:70]} retry={l.get('retry_count',0)}\")
"

# 3. codex 进程数
pgrep -c -f "codex exec" || echo "0"

# 4. 最近 runner 日志（最后 10 行）
tail -10 /tmp/runner*.log 2>/dev/null | grep -E "ERROR|WARN|Dispatch|merged|failed" | tail -10
```

### 异常处理

| 异常 | 处理 |
|---|---|
| runner 死了 | 重启（见 Phase 1 步骤 2） |
| lane retry_count >= 3 且仍 dispatched | 标记为 failed，避免无限重试 |
| codex rate limit（日志里 `rate_limit`） | 正常，recovery manager 会自动退避重试，不需干预 |
| 所有 lane 都 done/merged/failed，无 active | 任务完成，可以结束监控 |
| chat-driver 没有触发（architect-god 没回复） | 手动 tick：`curl -s -X POST http://localhost:8201/api/chat/tick` |
| 有价值的 failed lane 需要重试 | 重置为 pending（见下方命令），runner 会重新 dispatch |

### 重置 failed lane 为 pending（允许重试）

仅对属于 `orchestrator_decoupling` 或 `a2a_` track 的 failed lane 执行。不要重置旧的 failed lane。

```bash
python3 -c "
import json
from pathlib import Path
p = Path('xmuse/feature_lanes.json')
d = json.loads(p.read_text())
n = 0
for l in d['lanes']:
    if not isinstance(l, dict): continue
    if l.get('status') not in ('failed', 'exec_failed', 'gate_failed'): continue
    fid = l.get('feature_id', '')
    # 只重置本次 session 相关的 lane
    if not any(k in fid for k in ('c-phase', 'orchestrator', 'decoupling', 'a2a', 'projection', 'execution', 'adapters')): continue
    l['status'] = 'pending'
    l['retry_count'] = 0
    l.pop('dispatched_at', None)
    l.pop('god_runtime', None)
    l['manual_recovery'] = 'reset failed lane for retry'
    n += 1
    print(f'  reset: {fid[:70]}')
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
print(f'total reset: {n}')
"
```

限制：每个 lane 最多重置 2 次。如果同一个 lane 已经被重置过 2 次仍然 fail，不再重置，标记为永久失败。

### 标记失败 lane 的方法

```bash
python3 -c "
import json
from pathlib import Path
p = Path('xmuse/feature_lanes.json')
d = json.loads(p.read_text())
for l in d['lanes']:
    if isinstance(l, dict) and l.get('status') == 'dispatched' and (l.get('retry_count',0) or 0) >= 3:
        l['status'] = 'failed'
        l['failure_reason'] = 'max retries exceeded, marked by monitor'
        print(f'marked failed: {l.get(\"feature_id\")}')
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
"
```

## 5. 关键文件路径

| 文件 | 用途 |
|---|---|
| `xmuse/feature_lanes.json` | lane 执行队列（authoritative） |
| `xmuse/platform_runner.py` | 主 runner 入口 |
| `xmuse/chat_api.py` | chat HTTP API |
| `xmuse/mcp_server.py` | MCP server |
| `src/xmuse_core/platform/orchestrator.py` | lane 生命周期编排 |
| `src/xmuse_core/self_evolution/peer_chat_decomposer.py` | 拆解器 |
| `docs/superpowers/specs/2026-05-29-orchestrator-controller-decoupling-design.md` | 要注入的 spec |

## 6. 硬约束

- **不要使用 claude CLI**（CC API 暂不可用）
- **不要修改 orchestrator.py 或 controller.py**（subagent 可能正在改它们）
- **不要 force push 或 reset**
- **不要启动超过 8 个并发 codex exec**
- 如果 runner 需要重启，使用上面的精确命令
- 监控期间如果发现代码问题，可以修复并 commit，但不要做大规模重构
