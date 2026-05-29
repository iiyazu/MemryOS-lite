# xmuse God Group Chat — Architecture Design Spec

## Overview

A GUI-based multi-agent orchestration interface where multiple AI agent instances ("Gods") coexist in a group chat. Gods are short-lived CLI processes that achieve continuity through MemoryOS memory relay. Humans participate as equal members, triggering workflows and approving decisions through natural conversation.

## Core Model: Memory Relay

Gods are NOT daemon processes. They are short-lived `codex exec` / `claude -p` invocations that achieve "always-on" appearance through MemoryOS context injection on each wake.

```
Wake → MemoryOS build_context → full state restored → process message → ingest → exit
Wake → MemoryOS build_context → continues seamlessly → process message → ingest → exit
```

- Idle God = no process, just a state record in Gateway
- Active God = Gateway spawns CLI process with MemoryOS context prepended
- God "speaks" = process stdout → Gateway → frontend WebSocket
- God "hibernates" = process exits naturally
- God "wakes" = Gateway spawns new process with full context

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js + WebSocket)                                  │
│  - Group chat UI (God + human messages)                          │
│  - God status panel (idle/thinking/waiting_approval)             │
│  - Approval cards (approve/reject buttons)                       │
│  - @mention addressing                                           │
└──────────────────────┬──────────────────────────────────────────┘
                       │ WebSocket
┌──────────────────────▼──────────────────────────────────────────┐
│  God Gateway (Python, FastAPI + WebSocket)                        │
│                                                                  │
│  Modules:                                                        │
│  ├── core: WebSocket mgmt, process lifecycle, message persist    │
│  ├── router: @mention routing, broadcast policy, God-to-God      │
│  ├── executor: parse God output, dispatch actions, lane trigger   │
│  └── approvals: queue pending approvals, relay human decisions   │
│                                                                  │
│  God Registry: id, runtime, role, capabilities, state, MCP tools │
│  Message Store: SQLite (all chat messages, searchable)           │
│  Action Queue: sequential execution (prevents conflicts)         │
└──────────────────────┬──────────────────────────────────────────┘
                       │ spawn per message
┌──────────────────────▼──────────────────────────────────────────┐
│  God Process (short-lived)                                        │
│                                                                  │
│  Prompt structure:                                               │
│  1. System: role definition + available actions                   │
│  2. MemoryOS: Pages + Core Memory + relevant Episodes            │
│  3. God task state: active_task, pending decisions, next_step    │
│  4. Chat history: last N messages from group                     │
│  5. Current trigger: the message that caused this wake           │
│                                                                  │
│  Output format (JSON structured):                                │
│  { "messages": [...], "actions": [...] }                         │
│  - messages: text to post in group chat                          │
│  - actions: dispatch_lane, request_approval, @mention,           │
│             write_decision, call_tool                             │
│                                                                  │
│  After exit:                                                     │
│  - Gateway ingests output into MemoryOS                          │
│  - Gateway executes actions sequentially                         │
│  - Gateway updates God state                                     │
└─────────────────────────────────────────────────────────────────┘
```

## God Task State (procedural memory)

MemoryOS handles declarative knowledge. Procedural state (what am I doing next) is stored as a MemoryOS Page with convention:

```
Page: "God-{id}/active_task"
Facts:
- current_task: "implementing feature X"
- next_step: "waiting for Builder-God to finish lane Y"
- pending_approvals: ["merge-request-42"]
- context: "dispatched 2 lanes, 1 done, 1 in progress"
```

Updated on every God exit. Retrieved on every God wake.

## Communication Model

**Chat messages:** All visible communication flows through Gateway (WebSocket hub). Gods, humans — all equal participants in the message stream.

**MCP capability layer:** Gods expose tools to each other via MCP. When God-A wants God-B to review code, it emits an action `call_tool(God-B, review_code, {diff, context})`. Gateway translates this into waking God-B with the tool call as input. MCP is for capability invocation, not messaging.

**Routing policy:**
- @God-A → wake God-A with the message
- No @mention → route to Architect-God (it decides whether to handle or delegate)
- God output contains @God-B → Gateway wakes God-B with that message
- Depth limit: max 5 God-to-God hops before requiring human input

## God Roles

| Role | Runtime | Responsibilities |
|------|---------|-----------------|
| Architect-God | Claude Code | Design decisions, review architecture, error lifecycle, delegation |
| Builder-God | Codex | Implement features, write code, run tests, dispatch lanes |
| Reviewer-God | Claude Code | Review Builder output, approve/reject, quality assessment |
| Ops-God | Codex | Monitor execution, handle failures, infrastructure, metrics |

Architect-God is the default recipient for unaddressed messages. It can delegate to other Gods by @mentioning them.

## Output Format

Gods output structured JSON (enforced via `--output-format json` for Claude Code, schema instruction for Codex):

```json
{
  "messages": [
    {"text": "I'll dispatch a lane for this feature.", "visible": true}
  ],
  "actions": [
    {"type": "dispatch_lane", "feature_id": "new-feature", "prompt": "..."},
    {"type": "request_approval", "description": "Merge feature X?", "options": ["approve", "reject"]},
    {"type": "mention", "god_id": "builder", "message": "Please implement this"},
    {"type": "write_decision", "title": "...", "summary": "...", "facts": ["..."]},
    {"type": "call_tool", "god_id": "reviewer", "tool": "review_code", "args": {...}}
  ],
  "task_state": {
    "current_task": "...",
    "next_step": "...",
    "pending": []
  }
}
```

Fallback: if output is not valid JSON, treat entire stdout as a plain chat message.

## MemoryOS Integration

Full utilization of MemoryOS capabilities:

| MemoryOS Feature | God Usage |
|-----------------|-----------|
| build_context | On every wake — retrieves relevant Pages, Episodes, Core Memory |
| ingest | On every exit — stores God's output as Episode |
| write_page | When God makes a decision or learns something |
| patch_page | When God updates its task state |
| Core Memory Blocks | Cross-God shared knowledge (project facts, conventions) |
| Archive RAG | Indexing md archives, external docs |
| Memory Lifecycle | Auto-pages long God conversations into knowledge |

## Error Knowledge Lifecycle

```
Error occurs
  → error_knowledge.json (7-slot entry)
  → MemoryOS ingest (Episode)

Same pattern ≥3 times
  → Architect-God identifies pattern
  → Dispatches extraction lane:
    → Workflow pattern → xmuse/skills/<name>.py (new Skill)
    → Automatable op → MCP tool in mcp_server.py
    → Knowledge/decision → MemoryOS write_page + md archive

Root cause fixed, no recurrence for 5+ lanes
  → Architect-God marks superseded
  → MemoryOS Page superseded_by new Page
```

## Concurrency & Safety

- **Action queue:** Gateway executes God actions sequentially (prevents conflicting merges/dispatches)
- **Rate limiting:** Per-God max 10 wakes/hour (configurable)
- **Depth limit:** God-to-God chains max 5 hops before human required
- **Conflict resolution:** If two Gods dispatch conflicting lanes, Gateway applies first-come-first-served + notifies the second God

## Human Interaction

- Human sends message → appears in chat like any other participant
- Human can @mention specific God
- God outputs `request_approval` → Gateway shows approval card in frontend
- Human clicks approve/reject → Gateway wakes requesting God with decision
- Human can type "stop" or "pause" → Gateway halts all God activity

## Frontend Requirements

Group chat UI with:
- Message stream (God messages with role avatar, human messages)
- God status indicators (idle/thinking/waiting)
- Approval cards inline in chat (approve/reject buttons)
- @mention autocomplete
- "New Lane" quick action (dispatches via Architect-God)
- God activity sidebar (which Gods are thinking, what they're working on)

## Milestones (lanes)

M1: Gateway core + single God + SQLite messages
M2: MemoryOS integration + God task state + continuity verification
M3: Multi-God + routing + action parsing + sequential queue
M4: Frontend group chat UI + approval cards + WebSocket
M5: MCP capability layer + error lifecycle + Architect-God ownership
