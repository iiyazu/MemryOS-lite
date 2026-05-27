import type { LaneStatus } from "@/lib/types";

export function statusTone(status: LaneStatus) {
  if (["reviewed", "merged", "gated"].includes(status)) return "ok";
  if (["gate_failed", "exec_failed", "rejected", "failed"].includes(status)) return "bad";
  if (["dispatched", "executed", "reworking"].includes(status)) return "accent";
  return "warn";
}
