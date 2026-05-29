# xmuse Dashboard Frontend Design Spec

## Overview

Rebuild the xmuse dashboard frontend using Next.js 14 (App Router) + React + Tailwind CSS + Zustand, replacing the current vanilla HTML/JS implementation. The layout follows clowder-ai's AppShell three-column pattern.

## Tech Stack

- **Framework:** Next.js 14 (App Router)
- **UI:** React 18 + Tailwind CSS
- **State:** Zustand
- **Data fetching:** SWR (auto-refresh, revalidation)
- **Charts:** Recharts (for Metrics page)
- **Icons:** Lucide React
- **Package manager:** pnpm

## Layout Architecture

```
┌──────┬─────────────────┬────────────────────────────────────┐
│ Rail │    Sidebar       │          Main Content              │
│ 48px │    280px         │          flex-1                    │
│      │   (resizable)    │                                    │
│ Icon │                  │                                    │
│ Nav  │  Context-aware   │   Page-specific content            │
│      │  list panel      │                                    │
└──────┴─────────────────┴────────────────────────────────────┘
```

### ActivityRail (leftmost, 48px)

Fixed icon navigation bar:
- Chat icon → Lanes/Chat page
- BarChart icon → Metrics page
- AlertTriangle icon → Error Knowledge page
- Settings icon → Settings page
- Bottom: connection status indicator (green/red dot)

### Sidebar (280px, resizable)

Context-aware panel that changes content based on active page:
- **Lanes page:** Lane list with status avatars, search/filter
- **Metrics page:** Time range selector, filter controls
- **Error Knowledge page:** Search input, category filters
- **Settings page:** Settings section navigation

### Main Content

Page-specific content area:
- **Lanes/Chat:** Conversation-style message flow showing prompt → execution → gate results
- **Metrics:** Charts and stats cards
- **Error Knowledge:** 7-slot error cards with expandable details
- **Settings:** Form-based configuration panels

## Pages

### 1. Lanes / Chat (default)

Sidebar: Lane list items showing feature_id, status badge, branch name. Click to select.

Main: Conversation view for selected lane:
- User message bubble: the prompt
- System message: dependencies, worktree info
- Execution log: collapsible code block
- Gate result: pass/fail card with details
- Status: final done/failed indicator
- Bottom input bar: submit rework instructions or new commands

### 2. Metrics / Analytics

Sidebar: Time range picker (1h, 6h, 24h, 7d), status filter checkboxes.

Main:
- Summary cards row: total lanes, success rate, avg execution time, active sessions
- Line chart: lanes completed over time
- Bar chart: execution time per lane
- Pie chart: status distribution

### 3. Error Knowledge

Sidebar: Search input, scope filter (all / code / test / infra).

Main: Card grid of error entries, each showing:
- Title (pit summary)
- Root cause
- Trigger conditions
- Fix applied
- Lesson learned
- Expandable full 7-slot view

### 4. Settings

Sidebar: Section nav (General, Agents, MemoryOS, Theme).

Main:
- General: API URL, refresh interval, max concurrent
- Agents: agents.json editor (list of registered agents)
- MemoryOS: connection URL, status check
- Theme: dark/light toggle (dark default)

## Data Flow

```
xmuse Dashboard API (port 8200)
        ↓ HTTP
   SWR hooks (auto-refresh 5s)
        ↓
   Zustand stores
        ↓
   React components
```

### Stores

- `useLaneStore`: lanes array, selected lane ID, lane detail cache
- `useMetricsStore`: metrics data, time range
- `useErrorStore`: error entries, search query, filters
- `useSettingsStore`: API URL, theme, refresh interval
- `useConnectionStore`: API health status

## File Structure

```
xmuse/frontend/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── public/
├── src/
│   ├── app/
│   │   ├── layout.tsx          (root layout + AppShell)
│   │   ├── page.tsx            (redirect to /lanes)
│   │   ├── globals.css
│   │   ├── lanes/
│   │   │   └── page.tsx
│   │   ├── metrics/
│   │   │   └── page.tsx
│   │   ├── errors/
│   │   │   └── page.tsx
│   │   └── settings/
│   │       └── page.tsx
│   ├── components/
│   │   ├── AppShell.tsx
│   │   ├── ActivityRail.tsx
│   │   ├── Sidebar.tsx
│   │   ├── lanes/
│   │   │   ├── LaneList.tsx
│   │   │   ├── LaneItem.tsx
│   │   │   ├── ChatView.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   └── InputBar.tsx
│   │   ├── metrics/
│   │   │   ├── SummaryCards.tsx
│   │   │   └── Charts.tsx
│   │   ├── errors/
│   │   │   ├── ErrorCard.tsx
│   │   │   └── ErrorGrid.tsx
│   │   └── settings/
│   │       └── SettingsPanel.tsx
│   ├── stores/
│   │   ├── laneStore.ts
│   │   ├── metricsStore.ts
│   │   ├── errorStore.ts
│   │   ├── settingsStore.ts
│   │   └── connectionStore.ts
│   ├── hooks/
│   │   ├── useLanes.ts
│   │   ├── useMetrics.ts
│   │   └── useErrors.ts
│   └── lib/
│       └── api.ts              (fetch wrapper for dashboard API)
└── .env.local                  (NEXT_PUBLIC_API_URL=http://localhost:8200)
```

## Theme

Dark mode default. Color palette:
- Background: slate-900 / slate-950
- Sidebar: slate-800
- Cards: slate-800/slate-700
- Accent: cyan-400 (status indicators, active states)
- Success: emerald-500
- Error: red-500
- Warning: amber-500
- Text: slate-100 (primary), slate-400 (muted)

## API Integration

All data from existing `xmuse/dashboard_api.py` (port 8200):
- `GET /api/lanes` → lane list
- `GET /api/lanes/{id}` → lane detail + log + gate
- `POST /api/lanes` → create new lane
- `POST /api/lanes/{id}/approve` → approve lane
- `POST /api/lanes/{id}/reject` → reject lane
- `GET /api/errors` → error knowledge entries
- `GET /api/metrics` → execution statistics
- `GET /api/sessions` → active sessions

## Deployment

```bash
cd xmuse/frontend && pnpm install && pnpm dev
# → http://localhost:3000
```

Production: `pnpm build && pnpm start`
