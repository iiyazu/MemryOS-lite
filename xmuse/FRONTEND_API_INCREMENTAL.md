# xmuse Frontend API Incremental Contract

更新日期: 2026-05-28 (session 2)

本文是 `xmuse/FRONTEND_API.md` 的增量契约，按当前工作树中的后端实现描述前端需要新增或修正的 API 认知。本文只描述前端直接消费的接口，不描述后端内部实现路线。

## What changed since session 1

| Area | Session-2 delta |
|---|---|
| Lane shape | `feature_group: string \| null` 新字段；带斜杠时表示 `<track>/<feature-name>` 二级分组 |
| Lane decomposition | 一个自演化 chain step 现在可能产出 1-N 条 lane，跨 feature 可并行，feature 内可有依赖 |
| Auto-evolution | 新增 watcher：merged graph 自动 spawn 下一轮，不再需要外部 driver |
| Budget window | 过期 window 不再阻塞新 chain，自动 mark `expired` 并 mint 新 window |
| GOD runtime | `claude` 已 supported (默认 sonnet `--bare`)，与 `codex` 等价交换 |
| Multi-track rotation | Architect 按蓝图 priority + landed-counts 选 track，不再固定单 track |
| Clarification | `blocked_for_input` 不再静默跳过，写为 `ClarificationRequest`，可用 `ClarificationResolution` 解锁 |
| Audit read model | `/api/self-evolution/audit` 提供按 lineage 联合 proposal/aggregation/conversation 的快照 |
| Endpoints (new) | `/api/self-evolution/audit`、`/api/self-evolution/conversations`、`/api/self-evolution/clarifications` |

## Base URLs

| Surface | Base URL | 当前状态 |
|---|---|---|
| Dashboard REST | `http://localhost:8200/api` | live |
| Chat REST | `http://localhost:8201/api/chat` | live |
| MCP JSON-RPC | `http://localhost:8100/mcp` | live |

## Contract Delta Summary

| Area | 增量变化 |
|---|---|
| Lane list/detail | `effective_status` 已是 live 字段，不再只是 reserved |
| Lane shape (s2) | `feature_group: string \| null` 新字段 |
| Metrics | `ready` / `requeued` 已是 live 字段 |
| Sessions | GOD session registry list shape 已被 `/api/sessions` 直接透传 |
| Final action | `POST /api/lanes/{feature_id}/approve` 可 resolve `awaiting_final_action` |
| Read models | `/api/resolutions`、`/api/verdicts` live |
| Self-evolution | `/api/self-evolution` live，返回多个 read-model collection |
| Self-evolution (s2) | watcher auto-spawn 一旦 graph merged；budget window 自动续期；track 自动轮转 |
| Chat approval | proposal approval 会保存 LaneGraph snapshot 并投影 dependency-ready lanes |
| Decomposition (s2) | 一个 chain step 可产出 1-N 条 lane，跨 feature 可并行，feature 内可有依赖 |

## Lane Status Contract

`GET /api/lanes` 和 `GET /api/lanes/{feature_id}` 当前都会返回：

- `status`: raw runtime 状态
- `effective_status`: mixed-run 归一化状态

前端显示、筛选、颜色映射使用 `effective_status`；调试视图可以同时展示 raw `status`。

当前归一化规则：

| Raw `status` | `effective_status` |
|---|---|
| missing / empty / `pending` | `ready` |
| `dispatched` | `dispatched` |
| `executed` | `executed` |
| `gated` | `under_review` |
| `reviewed` | `reviewed` |
| `awaiting_final_action` | `awaiting_final_action` |
| `merged` | `merged` |
| `done` | `merged` |
| `completed` | `merged` |
| `rejected` | `requeued` |
| `reworking` | `requeued` |
| `exec_failed` | `exec_failed` |
| `gate_failed` | `gate_failed` |
| `failed` with string `failure_reason` | that `failure_reason` |
| `failed` without string `failure_reason` | `terminated` |

Example:

```json
{
  "lanes": [
    {
      "feature_id": "legacy-done",
      "status": "done",
      "effective_status": "merged",
      "prompt": "ship it"
    },
    {
      "feature_id": "new-lane",
      "status": "pending",
      "effective_status": "ready",
      "prompt": "build it"
    }
  ]
}
```

## Metrics Delta

`GET /api/metrics`

Current response keys:

```ts
type DashboardMetrics = {
  total: number;
  done: number;
  ready: number;
  requeued: number;
  failed: number;
  pending: number;
  avg_time_seconds: number | null;
};
```

Example:

```json
{
  "total": 6,
  "done": 1,
  "ready": 1,
  "requeued": 1,
  "failed": 3,
  "pending": 2,
  "avg_time_seconds": 20.0
}
```

Metric semantics:

| Field | Meaning |
|---|---|
| `total` | all lane records in `feature_lanes.json` |
| `done` | normalized merged lanes, including legacy raw `done` / `completed` |
| `ready` | normalized ready lanes, currently raw `pending` |
| `requeued` | normalized rework/retry lanes |
| `failed` | terminal non-merged lanes |
| `pending` | backward-compatible derived bucket: `total - done - failed` |
| `avg_time_seconds` | average over lanes with explicit duration or start/completion timestamps |

The current endpoint does not return `terminal` or per-status arbitrary buckets.

## Sessions Delta

`GET /api/sessions`

The endpoint currently accepts/returns all supported file shapes. Frontend row identity order:

```ts
const sessionKey =
  session.god_session_id ?? session.session_id ?? session.feature_id;
```

GOD session registry shape is live:

```json
{
  "sessions": [
    {
      "god_session_id": "god-1",
      "role": "executor",
      "session_address": "xmuse://sessions/god-1",
      "session_inbox_id": "inbox-1",
      "status": "running",
      "pid": 456
    }
  ]
}
```

Full future-compatible type:

```ts
type GodSession = {
  god_session_id?: string;
  session_id?: string;
  feature_id?: string;
  role?: string;
  agent_name?: string;
  runtime?: string;
  session_address?: string;
  session_inbox_id?: string;
  assignment_feature_id?: string | null;
  status?: string;
  state?: string;
  pid?: number | null;
};
```

`feature_id` and `assignment_feature_id` are assignment fields, not stable session identity.

## Final Action Approval Delta

`POST /api/lanes/{feature_id}/approve`

Currently accepted lane states:

- `done`
- `merged`
- `awaiting_final_action`

For `awaiting_final_action`, the endpoint looks for a pending hold in `final_actions.json`.

| Hold action | Resulting lane `status` |
|---|---|
| `merge` | `merged` |
| `terminate` | `failed` |
| other / missing hold | `409` |

Response is the updated lane object and includes `effective_status`.

## Read Model Endpoints Delta

### `GET /api/resolutions`

Returns:

```ts
type ResolutionsResponse = {
  resolutions: Array<{
    resolution_id: string;
    conversation_id?: string;
    version?: number;
    status?: string;
    goal_summary?: string;
    approved_by?: string[];
    approval_mode?: string;
  }>;
};
```

Source file: `xmuse/read_models/resolutions.json`.

### `GET /api/verdicts`

Returns:

```ts
type VerdictsResponse = {
  verdicts: Array<Record<string, unknown>>;
};
```

Source file: `xmuse/read_models/verdicts.json`. Empty list is a valid current state.

## Self-Evolution Endpoint

`GET /api/self-evolution`

This endpoint is live in the current dashboard API. It reads `xmuse/self_evolution/*.json` and returns empty arrays for missing or malformed collections.

Response shape:

```ts
type SelfEvolutionResponse = {
  run_aggregations: RunTerminalAggregation[];
  evidence_bundles: StructuredEvidenceBundle[];
  proposals: EvolutionProposal[];
  review_decisions: EvolutionReviewDecision[];
  guardrail_decisions: EvolutionGuardrailDecision[];
  budget_windows: EvolutionBudgetWindow[];
  dedup_records: EvolutionDedupRecord[];
  lineage: EvolutionLineageRecord[];
};
```

Top-level collection names are stable for the current frontend. Individual item fields mirror `src/xmuse_core/self_evolution/models.py`.

Important fields by collection:

```ts
type RunTerminalAggregation = {
  aggregation_id: string;
  run_id: string;
  resolution_id: string;
  graph_id: string;
  status: "running" | "merged" | "terminated" | "blocked_for_input";
  terminal: boolean;
  reason: string;
  lane_counts: Record<string, number>;
  lane_statuses: Array<Record<string, unknown>>;
  open_lineages: Array<Record<string, unknown>>;
  blocked_objects: Array<Record<string, unknown>>;
  created_at: string;
};

type StructuredEvidenceBundle = {
  bundle_id: string;
  source_run_id: string;
  source_resolution_id: string;
  selection_policy_id: string;
  selection_policy_version: string;
  summary: string;
  run_terminal_status: "running" | "merged" | "terminated" | "blocked_for_input";
  verdict_refs: string[];
  gate_report_refs: string[];
  lineage_refs: string[];
  artifact_refs: string[];
  signal_refs: string[];
  primary_refs: string[];
  created_at: string;
};

type EvolutionProposal = {
  proposal_id: string;
  source_run_id: string;
  blueprint_set_id: string;
  target_track_ids: string[];
  status:
    | "drafting"
    | "awaiting_review"
    | "narrowed_for_redraft"
    | "approved"
    | "rejected"
    | "guardrail_blocked"
    | "landed";
  draft_version: number;
  author_session_id: string;
  scope_summary: string;
  why_now: string;
  evidence_bundle_id: string;
  candidate_graph: Record<string, unknown>;
  review_status: string;
  spawned_conversation_id?: string | null;
  spawned_resolution_id?: string | null;
  created_at: string;
};
```

Additional model fields:

```ts
type EvolutionReviewDecision = {
  decision_id: string;
  proposal_id: string;
  review_session_id: string;
  decision: "approve" | "narrow" | "reject";
  rationale: string;
  narrowing_decision?: Record<string, unknown> | null;
  created_at: string;
};

type EvolutionGuardrailDecision = {
  decision_id: string;
  proposal_id: string;
  action: "continue" | "hold" | "stop";
  rationale: string;
  source_run_id?: string | null;
  reason_codes: string[];
  budget_window_id?: string | null;
  dedup_key?: string | null;
  terminal_aggregation_ref?: string | null;
  checks: Record<string, boolean>;
  created_at: string;
};

type EvolutionBudgetWindow = {
  window_id: string;
  origin_run_id: string;
  started_at: string;
  expires_at: string;
  status: "active" | "expired";
  consumed_run_ids: string[];
};

type EvolutionDedupRecord = {
  dedup_key: string;
  signal_fingerprint: string;
  source_lineage_key: string;
  target_track_ids: string[];
  first_seen_at: string;
  last_seen_at: string;
  last_proposal_id: string;
  status: "continued" | "duplicate";
};

type EvolutionLineageRecord = {
  lineage_id: string;
  source_run_id: string;
  source_resolution_id?: string | null;
  evidence_bundle_id: string;
  evolution_proposal_id: string;
  review_decision_id: string;
  guardrail_decision_id: string;
  spawned_conversation_id: string;
  spawned_proposal_id: string;
  spawned_resolution_id: string;
  spawned_graph_id: string;
  blueprint_set_id: string;
  target_track_ids: string[];
  terminal_aggregation_ref?: string | null;
  created_at: string;
};
```

Current endpoint also returns two more collections (added since session 1):

- `clarification_requests` — open / resolved blocked-for-input records
- `clarification_resolutions` — submitted unblock information

See "Clarification Endpoints" below for dedicated read-model endpoints that
present these joined.

## Audit + Conversations + Clarifications (session 2)

Three dedicated read-model endpoints sit on top of the raw store. They
materialise into `xmuse/read_models/*.json` on demand and the dashboard
should prefer them over re-joining raw collections.

### `GET /api/self-evolution/audit`

Returns a per-lineage audit snapshot joining lineage record + proposal +
run-terminal aggregation + system-authored conversation.

```ts
type SelfEvolutionAuditEntry = {
  lineage_id: string;
  source_run_id: string;
  spawned_graph_id: string;
  spawned_resolution_id: string;
  spawned_conversation_id: string | null;
  blueprint_set_id: string;
  target_track_ids: string[];
  // joined data:
  proposal?: {
    proposal_id: string;
    scope_summary: string;
    target_track_ids: string[];
    status: "drafting" | "awaiting_review" | "approved" | "rejected" | "guardrail_blocked" | "landed";
    review_status: "approve" | "narrow" | "reject" | "awaiting_review";
    candidate_lane_count: number;
    feature_groups: string[];  // distinct feature_group values across candidate lanes
  };
  aggregation?: {
    aggregation_id: string;
    status: "running" | "merged" | "terminated" | "blocked_for_input";
    reason: string;
    terminal: boolean;
    lane_counts: Record<string, number>;
    blocked_object_count: number;
    final_action_hold_count: number;
  };
  conversation?: {
    conversation_id: string;
    title: string;
    created_by: string;
    created_at: string;
  };
  guardrail_decision?: {
    decision_id: string;
    action: "continue" | "hold" | "stop";
    rationale: string;
    reason_codes: string[];
  };
  created_at: string;
};

type SelfEvolutionAuditResponse = {
  schema_version: "1";
  generated_at: string;  // ISO 8601 UTC
  entries: SelfEvolutionAuditEntry[];
};
```

UI suggestion: render as a vertical timeline, newest first, expandable cards.

### `GET /api/self-evolution/conversations`

Returns system-authored conversations (the chat-plane handoff for each
landed self-evolution run) joined with the originating proposal so the UI can
show "this conversation targets blueprint track X".

```ts
type SelfEvolutionConversation = {
  conversation_id: string;
  proposal_id: string;
  source_run_id: string;
  created_by: string;
  created_at: string;
  // joined from proposal:
  target_track_ids: string[];
  scope_summary: string;
  spawned_resolution_id: string | null;
};

type SelfEvolutionConversationsResponse = {
  schema_version: "1";
  generated_at: string;
  conversations: SelfEvolutionConversation[];
};
```

### `GET /api/self-evolution/clarifications`

Returns clarification requests joined with their resolutions (if any) so the
UI can display a single timeline of "blocked → unblocked" events.

```ts
type ClarificationStatus = "open" | "resolved" | "abandoned";

type ClarificationRequest = {
  request_id: string;
  source_run_id: string;
  aggregation_id: string;
  blocked_objects: Array<{
    lane_id: string;
    missing_input: string;
    owner: string;
    resume_path: string;
  }>;
  missing_input_summary: string;
  owner: string;
  resume_path: string;
  status: ClarificationStatus;
  created_at: string;
  resolved_at: string | null;
};

type ClarificationResolution = {
  resolution_id: string;
  request_id: string;
  source_run_id: string;
  provided_information: string;
  provided_context: Record<string, unknown>;
  provided_by: string;
  spawned_conversation_id: string | null;
  spawned_resolution_id: string | null;
  spawned_graph_id: string | null;
  created_at: string;
};

type ClarificationLifecycleEntry = {
  request: ClarificationRequest;
  resolution: ClarificationResolution | null;
};

type ClarificationsResponse = {
  schema_version: "1";
  generated_at: string;
  clarifications: ClarificationLifecycleEntry[];
};
```

#### Where blocked runs come from

The watcher records a `ClarificationRequest` automatically when a run reaches
terminal status `blocked_for_input`. The frontend does not need to detect
the block itself — it appears in this endpoint within seconds of the watcher
tick.

#### Resolving a request (not yet exposed via REST)

There is currently no `POST /api/self-evolution/clarifications/{id}/resolve`
endpoint. Resolutions must be created out-of-band via
`SelfEvolutionController.resolve_clarification(...)`. A future endpoint
should accept `provided_information` + `provided_context` and return the
resulting `ClarificationResolution`.

## Multi-Lane Decomposition Delta (session 2)

A self-evolution chain step now produces 1-N lanes instead of always 1. This
changes how the dashboard should render lane lists and how it should infer
"which work belongs together".

### `feature_group`

Every lane on `GET /api/lanes` and `GET /api/lanes/{feature_id}` may carry a
`feature_group` field:

| Value shape | Meaning |
|---|---|
| `null` / missing | legacy lane or single-lane chain step |
| `"<track_id>"` | single-lane decomposer; this lane is the whole step for that blueprint track |
| `"<track_id>/<feature_name>"` | peer-chat decomposer; this lane belongs to a named feature inside that track |

UI suggestion: group lane cards by `feature_group`. When the value contains a
`/`, render as `<track>` (outer chip) + `<feature_name>` (inner chip).

Example:

```json
{
  "lanes": [
    {
      "feature_id": "self-evolution-graph_authority-res_xxx-ingest-pipeline-impl",
      "status": "dispatched",
      "effective_status": "dispatched",
      "feature_group": "graph_authority/ingest-pipeline",
      "depends_on": []
    },
    {
      "feature_id": "self-evolution-graph_authority-res_xxx-review-flow-impl",
      "status": "pending",
      "effective_status": "ready",
      "feature_group": "graph_authority/review-flow",
      "depends_on": []
    },
    {
      "feature_id": "self-evolution-graph_authority-res_xxx-review-flow-tests",
      "status": "pending",
      "effective_status": "ready",
      "feature_group": "graph_authority/review-flow",
      "depends_on": ["self-evolution-graph_authority-res_xxx-review-flow-impl"]
    }
  ]
}
```

### Decomposer mode (informational)

The runner is launched with one of
`--decomposer={single,deterministic-multi,peer-chat}`. The selected mode is
**not** exposed via the REST API; the frontend infers it from lane payloads:

- `feature_group` missing or equal to track id → single-lane mode
- `feature_group` equals track id and 3 lanes per spawn (design/impl/tests)
  → deterministic-multi
- `feature_group` of the form `<track>/<feature>` → peer-chat

A future endpoint `/api/runtime/info` may surface this directly.

### Dependency-ready projection

Only dependency-ready lanes appear on `GET /api/lanes` initially. As parents
merge, child lanes show up over time. The UI does NOT need to render
not-yet-projected lanes — these come from the LaneGraph snapshot, which is
not currently exposed (see "Endpoint Existence Matrix" for the gap).

## Auto-Evolution Delta (session 2)

The platform runner can be launched with `--auto-evolve`. With it on:

1. Every idle tick, the watcher scans `xmuse/lane_graphs/*.json`.
2. Any graph that has reached terminal status AND is not yet recorded as a
   `source_run_id` in `xmuse/self_evolution/lineage.json` triggers a fresh
   chain step.
3. The next chain step picks a target track via priority + landed-counts
   (least-landed wins).
4. Spawned graph + ready lanes appear immediately on the next
   `GET /api/lanes` and `GET /api/self-evolution` poll.

UI implication: the **lineage** read model under `GET /api/self-evolution`
grows over time without any user action. The dashboard should poll on a
modest cadence (e.g. every 5-10s while open) and visually diff `lineage`
to highlight new auto-spawned runs.

### Track distribution metric

`GET /api/self-evolution` already exposes `lineage`. To compute "which
blueprint tracks have advanced":

```ts
function trackCounts(self_evolution_payload): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const record of self_evolution_payload.lineage) {
    for (const track of record.target_track_ids ?? []) {
      counts[track] = (counts[track] ?? 0) + 1;
    }
  }
  return counts;
}
```

This is the source-of-truth for "blueprint progress" until a dedicated
endpoint is added.

## Budget Window Auto-Renewal (session 2)

`GET /api/self-evolution` returns a `budget_windows` collection. Multiple
windows can now coexist:

- one or more with `status="expired"` (closed past chains)
- at most one with `status="active"` (current chain)

The frontend should display the active window prominently and treat expired
windows as audit-only history.

```ts
type BudgetWindow = {
  window_id: string;
  origin_run_id: string;
  started_at: string;  // ISO 8601 UTC
  expires_at: string;
  status: "active" | "expired";
  consumed_run_ids: string[];
};
```

Display the active window's countdown to `expires_at`. When it expires the
backend will either mint a new one (next merged graph) or pause auto-spawning
silently.

## GOD Runtime Selection (session 2)

The runner now accepts `--god-runtime=claude` (default `codex`). When `claude`
is selected:

- `claude -p --bare --dangerously-skip-permissions --output-format json --model sonnet --mcp-config <tmp>` is invoked per execute/review.
- `XMUSE_CLAUDE_MODEL` env (e.g. `opus`, `haiku`) overrides the model.
- `XMUSE_CLAUDE_BARE=0` disables `--bare` if the GOD needs CLAUDE.md / hooks.

Frontend impact: none for now — but a future `/api/runtime/info` should
return the active runtime so the dashboard can label sessions correctly.

## Chat API Delta

### Proposal approval side effects

`POST /api/chat/proposals/{proposal_id}/approve`

In addition to returning the `StructuredResolution`, this endpoint currently performs these side effects:

1. Appends/updates `xmuse/read_models/resolutions.json`.
2. Saves a LaneGraph snapshot under `xmuse/lane_graphs/`.
3. Projects dependency-ready lanes into `xmuse/feature_lanes.json`.

Frontend can treat successful approval as the handoff point from chat plane into execution queue. After approval, refresh:

- `GET /api/resolutions`
- `GET /api/lanes`
- optionally `GET /api/metrics`

### Thread endpoints

`GET /api/chat/threads` and `POST /api/chat/threads/{conversation_id}/messages` remain the current `/chat` UI endpoints.

Thread message response:

```ts
type AddThreadMessageResponse = {
  thread_id: string;
  message: {
    id: string;
    role: "user";
    author: "Human operator";
    kind: "checkpoint";
    content: string;
  };
};
```

There is still no live backend stream for long-running GOD replies in the chat UI.

## Lane Graphs Endpoints (session 3)

Two new endpoints expose lane graph snapshots with their derived execution state.
These fill the `GET /api/lane-graphs` gap in the endpoint matrix.

### `GET /api/lane-graphs`

Returns all lane graph snapshots found under `xmuse/lane_graphs/*.json`, each
enriched with a `derived_state` block computed from the current lane execution
state (same logic as `GET /api/health`'s `graph_authority`).

```ts
type LaneGraphListEntry = {
  id: string;
  conversation_id: string;
  resolution_id: string;
  version: number;
  status: string;
  lanes: LaneNode[];
  derived_state: DerivedGraphState;
};

type DerivedGraphState = {
  status: "running" | "merged" | "terminated" | "blocked_for_input" | "unknown";
  terminal: boolean;
  reason: string;
  graph_lineage_status: string;
  lane_counts: Record<string, number>;
  lane_statuses: Array<{
    feature_id: string;
    raw_status: string;
    normalized_status: string;
    terminal: boolean;
    has_merge_verdict?: boolean;
  }>;
  open_lane_lineages: string[];
  failed_lineages: string[];
  merged_lineages: string[];
  unmerged_terminal_lineages: string[];
  blocked_objects: Array<{
    lane_id: string;
    missing_input: string;
    owner: string;
    resume_path: string;
  }>;
  final_action_holds: Array<{
    lane_id: string;
    action: string;
    verdict_id: string | null;
    summary?: string;
  }>;
};

type LaneGraphsResponse = {
  graphs: LaneGraphListEntry[];
  total: number;
};
```

Graphs are sorted newest-first by `id` (lexicographic).

### `GET /api/lane-graphs/{graph_id}`

Returns a single lane graph with its derived state, plus the most-recent
lineage record that spawned it and the most-recent run aggregation.

```ts
type LaneGraphDetailResponse = {
  graph: LaneGraphListEntry;
  lineage: EvolutionLineageRecord | null;
  aggregation: {
    aggregation_id: string | null;
    run_id: string | null;
    resolution_id: string | null;
    graph_id: string | null;
    status: string;
    terminal: boolean;
    reason: string | null;
    created_at: string | null;
  } | null;
};
```

Returns `404` when the graph file does not exist.

UI suggestion: use `GET /api/lane-graphs` as the primary graph list view.
Link each row to `GET /api/lane-graphs/{graph_id}` for the detail panel.
The `derived_state.status` field is the canonical display status for a graph.



| Endpoint | Current status |
|---|---|
| `GET /api/lanes` | live |
| `GET /api/lanes/{feature_id}` | live |
| `POST /api/lanes` | live |
| `POST /api/lanes/{feature_id}/approve` | live |
| `POST /api/lanes/{feature_id}/reject` | live |
| `GET /api/sessions` | live |
| `GET /api/errors` | live |
| `GET /api/resolutions` | live |
| `GET /api/verdicts` | live |
| `GET /api/self-evolution` | live |
| `GET /api/self-evolution/audit` | live (s2) |
| `GET /api/self-evolution/conversations` | live (s2) |
| `GET /api/self-evolution/clarifications` | live (s2) |
| `GET /api/metrics` | live |
| `GET /api/chat/threads` | live |
| `POST /api/chat/threads/{conversation_id}/messages` | live |
| `GET /api/lane-graphs` | live (s3) |
| `GET /api/lane-graphs/{graph_id}` | live (s3) |
| `GET /api/final-actions` | not live |
| `GET /api/audit-timeline` | not live (use `/api/self-evolution/audit` for self-evolution scope) |
| `POST /api/self-evolution/clarifications/{request_id}/resolve` | not live (use controller out-of-band) |
| `GET /api/runtime/info` | not live (decomposer mode / GOD runtime not exposed yet) |
| chat GOD stream / WebSocket | not live |

## Frontend Type Patch

Minimum delta for frontend type definitions:

```ts
export type EffectiveLaneStatus =
  | "ready"
  | "dispatched"
  | "executed"
  | "under_review"
  | "reviewed"
  | "awaiting_final_action"
  | "merged"
  | "requeued"
  | "terminated"
  | "exec_failed"
  | "gate_failed"
  | string;

export type Lane = {
  feature_id: string;
  status: string;
  effective_status: EffectiveLaneStatus;
  prompt?: string;
  task_type?: string;
  capabilities?: string[];
  priority?: number;
  depends_on?: string[];
  conversation_id?: string;
  resolution_id?: string;
  graph_id?: string;
  graph_version?: number;
  gate_profile?: string;
  gate_profiles?: string[];
  source_lane_id?: string;
  review_decision?: string;
  review_summary?: string;
  review_verdict_id?: string;
  final_action_hold_id?: string;
  failure_reason?: string;
  // session 2
  feature_group?: string | null;
};

export type FeatureGroupParts = {
  track: string;
  feature: string | null;
};

/** Parse `feature_group` into `<track>` / optional `<feature>`. */
export function parseFeatureGroup(value: string | null | undefined): FeatureGroupParts | null {
  if (!value) return null;
  const slash = value.indexOf("/");
  if (slash < 0) return { track: value, feature: null };
  return { track: value.slice(0, slash), feature: value.slice(slash + 1) };
}

export type DashboardMetrics = {
  total: number;
  done: number;
  ready: number;
  requeued: number;
  failed: number;
  pending: number;
  avg_time_seconds: number | null;
};
```
