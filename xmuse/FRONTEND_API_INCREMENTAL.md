# xmuse Frontend API Incremental Contract

更新日期: 2026-05-28

本文是 `xmuse/FRONTEND_API.md` 的增量契约，按当前工作树中的后端实现描述前端需要新增或修正的 API 认知。本文只描述前端直接消费的接口，不描述后端内部实现路线。

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
| Metrics | `ready` / `requeued` 已是 live 字段 |
| Sessions | GOD session registry list shape 已被 `/api/sessions` 直接透传 |
| Final action | `POST /api/lanes/{feature_id}/approve` 可 resolve `awaiting_final_action` |
| Read models | `/api/resolutions`、`/api/verdicts` live |
| Self-evolution | `/api/self-evolution` live，返回多个 read-model collection |
| Chat approval | proposal approval 会保存 LaneGraph snapshot 并投影 dependency-ready lanes |

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

Current endpoint does not return `conversations`, even though the self-evolution store has a conversations collection.

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

## Endpoint Existence Matrix

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
| `GET /api/metrics` | live |
| `GET /api/chat/threads` | live |
| `POST /api/chat/threads/{conversation_id}/messages` | live |
| `GET /api/lane-graphs` | not live |
| `GET /api/final-actions` | not live |
| `GET /api/audit-timeline` | not live |
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
};

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
