export type LaneStatus =
  | "pending"
  | "dispatched"
  | "executed"
  | "gated"
  | "reviewed"
  | "merged"
  | "exec_failed"
  | "gate_failed"
  | "rejected"
  | "reworking"
  | "failed"
  | "aborted";

export type Lane = {
  feature_id: string;
  task_type: "execute";
  status: LaneStatus;
  prompt: string;
  branch?: string;
  capabilities: string[];
  gate_profile?: string;
  priority: number;
  source?: string;
  retry_count?: number;
  worktree?: string;
  base_head_sha?: string;
  depends_on?: string[];
  gate_report?: GateReport;
  god?: string;
  decision_reason?: string;
  elapsed?: string;
};

export type GateReport = {
  feature_id: string;
  passed: boolean;
  blocking_passed: boolean;
  nonblocking_failures: string[];
  profile_ids: string[];
  resolution_reasons: Record<string, string[]>;
  warnings: string[];
};

export type KnowledgeEntry = {
  id: string;
  pit: string;
  root_cause: string;
  trigger: string;
  fix: string;
  prevention: string;
  source: string;
  lesson: string;
};

export type KnowledgeMatch = {
  score: number;
  entry: KnowledgeEntry;
};

export type KnowledgeSearchResult = {
  query: string;
  matches: KnowledgeMatch[];
};

export type ToolName =
  | "list_lanes"
  | "enqueue_lane"
  | "get_status"
  | "abort_lane"
  | "get_error_knowledge"
  | "get_logs"
  | "get_lane"
  | "get_gate_report"
  | "get_diff"
  | "query_knowledge"
  | "update_lane_status";

export type XmuseApi = {
  listLanes(args?: { status?: LaneStatus | "all" }): Promise<Lane[]>;
  getLane(args: { lane_id: string }): Promise<Lane | undefined>;
  getGateReport(args: { lane_id: string }): Promise<GateReport>;
  getDiff(args: { lane_id: string }): Promise<{ diff: string; returncode: number }>;
  queryKnowledge(args: { query: string; top_k: number }): Promise<KnowledgeSearchResult>;
};
