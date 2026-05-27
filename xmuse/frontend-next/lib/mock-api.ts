import type { GateReport, KnowledgeEntry, KnowledgeSearchResult, Lane, LaneStatus, XmuseApi } from "@/lib/types";

const gateReport: GateReport = {
  feature_id: "error-knowledge-bounds",
  passed: false,
  blocking_passed: false,
  nonblocking_failures: [],
  profile_ids: ["xmuse-core"],
  resolution_reasons: { "xmuse-core": ["explicit_lane_profile"] },
  warnings: ["skipped missing pytest path in gate report"]
};

export const mockLanes: Lane[] = [
  {
    feature_id: "error-knowledge-bounds",
    task_type: "execute",
    status: "gate_failed",
    priority: 70,
    branch: "feat/error-knowledge-bounds",
    prompt: "Add size bounds and eviction for error knowledge storage",
    capabilities: ["code", "test"],
    gate_profile: "xmuse-core",
    retry_count: 1,
    depends_on: ["knowledge-query-ranking"],
    gate_report: gateReport,
    god: "Review God",
    decision_reason: "blocking gate failed: pytest path missing; rework requested with bounded JSON fixture",
    elapsed: "18m 42s"
  },
  {
    feature_id: "god-group-chat-timeline",
    task_type: "execute",
    status: "reviewed",
    priority: 92,
    branch: "feat/god-group-chat-timeline",
    prompt: "Render God/Human timeline with inline approvals and WebSocket append",
    capabilities: ["code", "test"],
    gate_profile: "xmuse-core",
    retry_count: 0,
    depends_on: [],
    god: "Review God",
    decision_reason: "approved after interaction model matched MemoryOS relay constraints",
    elapsed: "41m 08s"
  },
  {
    feature_id: "lane-concurrency-budget",
    task_type: "execute",
    status: "dispatched",
    priority: 86,
    branch: "feat/lane-concurrency-budget",
    prompt: "Expose master_loop concurrency and per-lane wakeup budget",
    capabilities: ["code", "test"],
    gate_profile: "xmuse-core",
    retry_count: 0,
    depends_on: ["feature-lanes-source"],
    god: "Planner God",
    decision_reason: "dispatch chosen because dependency source is stable and approval path is clear",
    elapsed: "07m 15s"
  },
  {
    feature_id: "diff-viewer-highlighting",
    task_type: "execute",
    status: "pending",
    priority: 64,
    branch: "feat/diff-viewer-highlighting",
    prompt: "Add unified diff highlighting to lane audit screen",
    capabilities: ["code"],
    gate_profile: "xmuse-ui",
    retry_count: 0,
    depends_on: [],
    god: "Design God",
    decision_reason: "waiting behind higher-priority observability lanes",
    elapsed: "-"
  }
];

export const mockKnowledge: KnowledgeEntry[] = [
  {
    id: "ek-001",
    pit: "mypy arg-type on Optional fields",
    root_cause: "Passing str | None to a parameter declared as str",
    trigger: "Optional field read directly from JSON lane metadata",
    fix: "Narrow with an explicit None guard before calling typed helper",
    prevention: "Keep strict optional checks on lane metadata adapters",
    source: "auto-mypy-lane-adapter",
    lesson: "Always narrow Optional before passing"
  },
  {
    id: "ek-014",
    pit: "ruff import order drift after codegen",
    root_cause: "Generated patch appended imports below local modules",
    trigger: "Adding diff parser utilities in an existing file",
    fix: "Run formatter after insertion and keep standard-library imports grouped",
    prevention: "Generate new helpers near existing import blocks",
    source: "auto-ruff-diff-viewer",
    lesson: "Patch imports deliberately, then format"
  },
  {
    id: "ek-021",
    pit: "gate report path missing",
    root_cause: "Worktree cleanup removed logs/gates before review fetch",
    trigger: "Review God asks get_gate_report after lane failed early",
    fix: "Return structured warning and preserve combined logs when report is absent",
    prevention: "Gate reads must tolerate missing artifact paths",
    source: "auto-gate-report",
    lesson: "Treat gate artifacts as nullable"
  }
];

export const mockDiff = `diff --git a/xmuse/error_knowledge.py b/xmuse/error_knowledge.py
@@ -42,7 +42,13 @@ class ErrorKnowledgeStore:
-    self.entries.append(entry)
+    if len(self.entries) >= self.max_entries:
+        self.entries = self.entries[-self.max_entries + 1:]
+    self.entries.append(entry)

@@ -91,6 +97,8 @@ def search(query: str, top_k: int):
+    if top_k < 1:
+        return []
     return sorted(matches, key=lambda item: item.score, reverse=True)[:top_k]`;

function matchesQuery(entry: KnowledgeEntry, query: string) {
  const haystack = [entry.id, entry.pit, entry.root_cause, entry.trigger, entry.fix, entry.prevention, entry.source, entry.lesson]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

export function createMockXmuseApi(): XmuseApi {
  return {
    async listLanes(args: { status?: LaneStatus | "all" } = {}) {
      if (!args.status || args.status === "all") return mockLanes;
      return mockLanes.filter((lane) => lane.status === args.status);
    },
    async getLane({ lane_id }) {
      return mockLanes.find((lane) => lane.feature_id === lane_id);
    },
    async getGateReport() {
      return gateReport;
    },
    async getDiff() {
      return { diff: mockDiff, returncode: 0 };
    },
    async queryKnowledge({ query, top_k }) {
      const matches: KnowledgeSearchResult["matches"] = mockKnowledge
        .filter((entry) => matchesQuery(entry, query))
        .slice(0, Math.max(0, top_k))
        .map((entry) => ({ score: entry.id === "ek-021" ? 3 : 2, entry }));
      return { query, matches };
    }
  };
}
