# xmuse Chat-First Frontend Vision

> Date: 2026-05-28 (session 2, Layer 5 — frontend contract)
> Status: design contract for the multi-GOD chat-first frontend
> Companion to: `xmuse/FRONTEND_API.md`, `xmuse/FRONTEND_API_INCREMENTAL.md`

This document is the **frontend-first** specification of the xmuse user
experience. It defines what the user sees, the routes they navigate, and the
data shapes the frontend expects from the backend. It is intentionally
written before all backend layers it depends on; the backend Layers 1-4
listed at the end are the implementation steps required to make this
frontend possible.

The frontend at `C:\Users\iiyatu\AppData\Roaming\Open Design\namespaces\release-stable-win\data\projects\2e36b78c-feca-4c9e-94d2-de7a84be2ebc\frontend`
should consume this contract as its source of truth.

## North-Star UX

```
┌─────────────────────────────────────────────────────────────────────────┐
│ xmuse                                              [⚙ settings]  [👤]  │
├──────────┬──────────────────────────────────────────┬───────────────────┤
│ THREADS  │  GROUP CHAT: redesign auth flow          │   WORKLIST        │
│          │                                           │                   │
│ + new    │  [👤 Operator]                           │  graph_authority  │
│  chat    │  We need OAuth2 for the API.             │   ◉ design ✓      │
│          │                                           │   ◉ impl   ●      │
│ ──────── │  [🤖 architect-god]                       │   ◉ tests  ⏵      │
│ ▶ active │  Should it support refresh tokens? Or    │                   │
│   • auth │  simple bearer only for v1?               │  review_plane     │
│   • dash │                                           │   ◉ impl   ⏵      │
│          │  [👤 Operator]                           │                   │
│ ──────── │  Refresh tokens. @review-god any concerns?│  → open dashboard │
│ • merged │                                           │                   │
│  • lane1 │  [🤖 review-god]                          │                   │
│  • feat2 │  Recommend rate-limiting refresh attempts │                   │
│          │  to avoid token-spray attacks.            │                   │
│          │                                           │                   │
│ ──────── │  ┌──────────────────────────────────────┐ │                   │
│ PARTIC.  │  │ [proposal] Add OAuth2 with refresh   │ │                   │
│          │  │ tokens (3 lanes)                     │ │                   │
│ 🤖 arch  │  │ [Approve] [Narrow] [Reject]          │ │                   │
│ 🤖 review│  └──────────────────────────────────────┘ │                   │
│ 🤖 exec  │                                           │                   │
│ + add god│  ┌──────────────────────────────────────┐ │                   │
│          │  │ Type a message...    @ ↩             │ │                   │
└──────────┴──────────────────────────────────────────┴───────────────────┘
```

Three columns:

- **Left rail** — thread list + participants of the focused thread.
- **Center** — the group chat itself. Inline approval cards. Inline mentions.
- **Right rail** — *worklist*: lightweight, cc-style; click jumps to dashboard.

Dashboard lives at a separate route, opened in a new tab or replacing the
center pane (user choice).

## Routing

| Route | Purpose |
|---|---|
| `/` | Redirect to most-recent-active conversation, or onboarding if none |
| `/chat` | Conversation index (left rail standalone) |
| `/chat/:conversation_id` | Group chat (the main UX) |
| `/chat/new` | New-thread wizard (pick title + optional initial GOD set) |
| `/dashboard` | Dashboard home (features grid) |
| `/dashboard/features` | Feature list, filterable by track / status / conversation |
| `/dashboard/features/:feature_group` | Feature detail + lane graph |
| `/dashboard/lane-graphs/:graph_id` | LaneGraph node-link view |
| `/dashboard/lanes/:feature_id` | Single lane detail (logs, gate report, verdict) |
| `/dashboard/audit` | Self-evolution lineage timeline |
| `/dashboard/clarifications` | Open ClarificationRequest queue |
| `/settings/role-templates` | Role-template editor (predefined + user-authored) |

## Key UI Behaviors

### Creating a group chat

`POST /api/chat/conversations` with optional `initial_participants`:

```ts
type CreateConversationRequest = {
  title: string;
  // If omitted, backend defaults to architect+review+execute GODs:
  initial_participants?: ParticipantInit[];
};

type ParticipantInit = {
  role: string;                    // "architect" | "review" | "execute" | <custom>
  cli_kind: "claude" | "codex";
  model?: string;                  // "haiku" | "sonnet" | "opus" | "gpt-5.5"
  role_template_id?: string;       // references RoleTemplate; required if role is custom
  display_name?: string;           // shown in chat (default: "<role>-god")
};
```

The "+ new chat" button opens a small wizard:

1. Title field (required)
2. Toggle "use defaults (architect/review/execute)" — checked by default
3. If unchecked, show a participant picker (model + role + template chooser)

### Adding/removing GODs in an existing chat

Left-rail "Participants" section has `+ add god` button:

`POST /api/chat/conversations/{conversation_id}/participants` with `ParticipantInit`.

`DELETE /api/chat/conversations/{conversation_id}/participants/{participant_id}` removes (and stops the long-running CLI session if any).

### Sending a message

`POST /api/chat/threads/{conversation_id}/messages` (existing), with optional metadata:

```ts
type AddMessageRequest = {
  message: string;
  // If non-empty, GODs whose role is in this list receive the message
  // through their inbox. If empty, default routing applies (architect handles
  // unaddressed messages, @mentions in text override).
  mentions?: string[];
};
```

### Receiving GOD replies

Two delivery modes; UI must handle both:

1. **Polling** (current MVP): UI polls `/api/chat/conversations/{id}/messages?since={message_id}`
2. **Streaming** (future): WebSocket at `/api/chat/conversations/{id}/stream`
   pushing `MessageEvent` JSON envelopes. Until WebSocket lands, UI uses
   polling at 2-3 s intervals while the chat tab is focused, and 30 s when
   backgrounded.

### Inline approval card

When a GOD's reply has `envelope_type == "proposal"`, the message bubble
renders an action card:

```ts
type ProposalCard = {
  proposal_id: string;
  scope_summary: string;
  feature_count: number;
  lane_count: number;
  feature_groups: string[];      // distinct feature_group values
  candidate_graph_url: string;   // /dashboard/lane-graphs/<preview-id>
};
```

Card actions:

- **Approve** → `POST /api/chat/proposals/{proposal_id}/approve` with the
  current operator as `approved_by`. On success, the chat shows a system
  message: "Approved → opened LaneGraph (<id>) — see worklist".
- **Narrow** → opens a small dialog asking for narrowing constraints
  (free text), then `POST /api/chat/proposals/{proposal_id}/narrow` (new
  endpoint). The architect-god is then re-pinged with the constraints.
- **Reject** → `POST /api/chat/proposals/{proposal_id}/reject` with reason.

### Verdict cards (review-god output)

When a review-god's reply has `envelope_type == "verdict"`, render a smaller
card showing decision (approve/narrow/reject) with the rationale text, and
no actions (review verdicts are advisory in chat; the human still presses
the proposal card's button).

### @mention autocomplete

When the user types `@` in the message composer, show a dropdown of the
conversation's participants. Selecting one inserts `@<role>` (or
`@<display_name>` for custom roles).

## Worklist Component (Right Rail)

Compact, cc-style. Groups by feature; each lane shown as a single line.

### Data source

`GET /api/chat/conversations/{conversation_id}/worklist`:

```ts
type WorklistResponse = {
  conversation_id: string;
  features: WorklistFeature[];
  schema_version: "1";
};

type WorklistFeature = {
  feature_group: string;          // "graph_authority" or "graph_authority/ingest-pipeline"
  graph_id: string;
  lanes: WorklistLane[];
  status_summary: WorklistStatusCounts;
};

type WorklistLane = {
  feature_id: string;
  title: string;                  // short label; falls back to feature_id
  effective_status: EffectiveLaneStatus;
  // optional UX hints:
  retry_count?: number;
  has_blocked_clarification?: boolean;
};

type WorklistStatusCounts = {
  total: number;
  ready: number;
  dispatched: number;
  executed: number;
  under_review: number;
  merged: number;
  failed: number;
};
```

### Rendering rules

- Each `WorklistLane` is one row, max width 30 chars + status icon.
- Status icons:
  - `ready` → ◌ (empty circle)
  - `dispatched` / `executed` / `under_review` → ⏵ (animated/spin)
  - `merged` → ✓ (green)
  - `failed` / `gate_failed` / `exec_failed` / `terminated` → ✗ (red)
  - `awaiting_final_action` → ◉ (filled, attention)
  - `requeued` → ↻
- Group header shows `<feature_group> [merged/total]`.
- Long lists: collapse merged groups by default; expand on click.
- Click a row → navigate to `/dashboard/lanes/:feature_id` (open in side panel
  or new tab; user setting).
- Click group header → `/dashboard/features/:feature_group`.
- Worklist polls the same endpoint at 5 s intervals while chat is open.

### What the worklist must NOT show

- Full prompts, gate command output, review summaries — those belong on
  the dashboard. Worklist is a glance, not a reader.
- Logs.
- Lane metadata internals (`graph_version`, `dispatched_at`, etc.).

## Dashboard

### `/dashboard` (home)

Three top-level cards:

- **Features** — count of merged/in-flight/failed across all conversations
- **Self-evolution chain** — recent lineage entries + active budget window
- **Open clarifications** — count of `ClarificationRequest`s

### `/dashboard/features`

Filterable table:

```ts
type DashboardFeature = {
  feature_group: string;
  graph_id: string;
  conversation_id: string;
  resolution_id: string;
  blueprint_track: string | null;       // single track or "<track>/<feature>"
  status: "planning" | "in_progress" | "merged" | "blocked" | "failed";
  lane_count: number;
  merged_lane_count: number;
  failed_lane_count: number;
  created_at: string;
  updated_at: string;
};

type DashboardFeaturesResponse = {
  schema_version: "1";
  features: DashboardFeature[];
};
```

Filters: `?track=…`, `?status=…`, `?conversation_id=…`.

### `/dashboard/features/:feature_group`

Detail page composed of:

- **Header** — feature_group + status + linked conversation
- **Lane graph** — node-link diagram (one per lane, edges from `depends_on`)
- **Lane table** — same lanes as the graph, sorted by topological order
- **Verdicts** — for each merged lane, the linked ReviewVerdict
- **Open clarifications** — if any lane is `blocked_for_input`

### `/dashboard/lane-graphs/:graph_id`

Pure node-link view (D3 / vis-network / Reaflow — frontend's choice).
Click a node → `/dashboard/lanes/:feature_id`.

```ts
type LaneGraphResponse = {
  graph_id: string;
  resolution_id: string;
  conversation_id: string;
  version: number;
  status: "planned" | "running" | "merged" | "halted";
  lanes: LaneGraphNode[];
  schema_version: "1";
};

type LaneGraphNode = {
  feature_id: string;
  title: string | null;
  feature_group: string | null;
  effective_status: EffectiveLaneStatus;
  depends_on: string[];
  priority: number;
  capabilities: string[];
};
```

### `/dashboard/lanes/:feature_id`

Single lane:

- prompt
- current status (raw + effective)
- depends_on chain (clickable)
- gate report (link to artifact)
- review verdict (if any)
- spawn log (latest stdout/stderr)
- retry/review_retry counts
- timestamps

Most fields already returned by `GET /api/lanes/{feature_id}`.

### `/dashboard/audit` and `/dashboard/clarifications`

Already covered in `FRONTEND_API_INCREMENTAL.md` session 2. Frontend just
needs to render the existing `/api/self-evolution/audit` and
`/api/self-evolution/clarifications` payloads.

## Role Templates

`/settings/role-templates` is a CRUD page.

```ts
type RoleTemplate = {
  id: string;
  slug: string;                  // "architect" | "review" | "execute" | "<user-slug>"
  display_name: string;          // "Architect GOD"
  prompt: string;                // multi-line; rendered as markdown in the editor
  cli_kind: "claude" | "codex";
  default_model: string;
  predefined: boolean;           // true for the 3 builtins
  created_at: string;
  updated_at: string;
};

// Endpoints
GET    /api/chat/role-templates
POST   /api/chat/role-templates
PUT    /api/chat/role-templates/{id}
DELETE /api/chat/role-templates/{id}
```

Predefined templates (read-only on frontend, marked with a 🔒):

- `architect` — "Drafts proposals, decomposes work, mentions other GODs."
- `review` — "Verifies proposals/code; emits approve/narrow/reject."
- `execute` — "Implements lanes inside the worktree, no shell escape."

Custom templates are user-editable and can be picked when creating a chat
or adding a GOD.

## Settings Surface

- `/settings/role-templates`
- `/settings/runtime` — view current runner state, restart toggles
  (read-only for v1; later: start/stop runner)
- `/settings/preferences` — UI toggles (dashboard pane mode, polling
  intervals, dark theme)

## Polling vs Streaming

For v1 the frontend polls; intervals:

| Surface | Interval (focused tab) | Interval (background) |
|---|---|---|
| Chat messages | 3 s | 30 s |
| Worklist | 5 s | 30 s |
| Dashboard features list | 10 s | 60 s |
| Single lane / verdict | 10 s | none |
| Self-evolution audit | 30 s | 5 min |
| Clarifications | 10 s | 60 s |

When WebSocket lands, frontend should subscribe to the
`/api/chat/conversations/{id}/stream` topic and stop polling for that
conversation; worklist stays on polling until a parallel stream lands.

## Type Definitions Summary (frontend imports)

The frontend `lib/api-types.ts` should export at minimum:

```ts
export {
  EffectiveLaneStatus,
  Lane,
  DashboardMetrics,
  // s2:
  parseFeatureGroup,
  // s2:
  ChatMessage,
  Conversation,
  Proposal,
  Resolution,
  // Layer 1 (this doc):
  Participant,
  ParticipantInit,
  RoleTemplate,
  CreateConversationRequest,
  AddMessageRequest,
  // Layer 2 (this doc):
  WorklistResponse,
  WorklistFeature,
  WorklistLane,
  WorklistStatusCounts,
  // Layer 3 (this doc):
  DashboardFeature,
  DashboardFeaturesResponse,
  // Layer 4 (this doc):
  LaneGraphResponse,
  LaneGraphNode,
};
```

```ts
export type Participant = {
  participant_id: string;
  conversation_id: string;
  role: string;                       // slug
  display_name: string;
  cli_kind: "claude" | "codex";
  model: string;
  role_template_id: string | null;
  status: "active" | "stopped";
  last_seen_at: string | null;
  created_at: string;
};
```

## What the Backend Owes (Layer 1-4 dependencies)

The frontend cannot ship without these endpoints. They are the implementation
order on the backend side after this document is approved.

### Layer 1 — Participants + Role Templates

- New tables: `participants`, `role_templates` in `xmuse/chat.db`
- `RoleTemplateStore` + `ParticipantStore` modules
- Endpoints:
  - `POST /api/chat/conversations` extended with `initial_participants`
  - `GET    /api/chat/conversations/{id}/participants`
  - `POST   /api/chat/conversations/{id}/participants`
  - `DELETE /api/chat/conversations/{id}/participants/{pid}`
  - `GET    /api/chat/role-templates`
  - `POST   /api/chat/role-templates`
  - `PUT    /api/chat/role-templates/{id}`
  - `DELETE /api/chat/role-templates/{id}`
- ChatDriver reads conversation participants instead of hardcoded
  `_ROLE_PROMPTS`.
- Default conversation seeds 3 builtin participants when
  `initial_participants` is missing.

### Layer 2 — Worklist Endpoint

- `GET /api/chat/conversations/{id}/worklist` projecting
  `feature_lanes.json` filtered by `conversation_id` + grouped by
  `feature_group`.

### Layer 3 — Feature Read Model

- `GET /api/dashboard/features` joining `feature_lanes.json` + `lane_graphs/`
  by `graph_id`. Status derived from lane normalized statuses.
- `GET /api/dashboard/features/{feature_group}` returning detail.

### Layer 4 — LaneGraph Read Endpoint

- `GET /api/dashboard/lane-graphs/{graph_id}` returning nodes + edges +
  current status of each node.
- `GET /api/dashboard/lanes/{feature_id}` already exists as
  `/api/lanes/{feature_id}`; rename or alias.

### Layer 5 — Streaming (post-v1)

- WebSocket `/api/chat/conversations/{id}/stream`
- WebSocket `/api/dashboard/lanes/{feature_id}/stream` for live spawn
  output.

## What the Frontend Should Not Do (v1)

- Direct DB reads.
- Maintain its own state machine for lanes (always trust
  `effective_status`).
- Show full prompts/logs in the chat UI.
- Implement role-prompt editing inline in chat (use settings page).
- Implement WebSocket fallbacks more complex than "if disconnect, fall back
  to polling".

## Acceptance Checklist

The chat-first frontend is delivered when:

1. User can `POST /chat/new`, see the conversation immediately, with the
   3 default GODs in the participant list.
2. User typing a plain message gets a reply from architect-god.
3. User typing `@review` gets a reply from review-god.
4. Architect-god can emit a proposal envelope rendered as an inline
   approval card.
5. Pressing "Approve" closes the card, system message confirms, and a new
   feature appears in the worklist within 5 s.
6. Worklist groups by feature_group; clicking a row navigates to lane
   detail.
7. `/dashboard/features` lists every feature ever created; clicking opens
   a lane-graph view.
8. `/settings/role-templates` lists 3 builtins + any custom templates;
   custom templates can be created/edited/deleted; created templates
   appear in the new-chat wizard.
9. All 3 polling intervals respect tab visibility.
10. Frontend never crashes when backend serves a status the type union
    doesn't enumerate (treated as opaque string).
