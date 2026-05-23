#!/usr/bin/env bash
set -u

PHASE_ID="phase-11"
PHASE_DIR=".hermes-loop/work/${PHASE_ID}"
EVAL_DIR=".memoryos/evals"
RUN_TS="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$PHASE_DIR" "$EVAL_DIR"

write_heartbeat() {
  local heartbeat_path="$1"
  local benchmark="$2"
  local run_id="$3"
  local command_text="$4"
  local start_time="$5"
  local partial_path="$6"
  local final_path="$7"
  local status="$8"

  python3 - "$heartbeat_path" "$PHASE_ID" "$benchmark" "$run_id" "$command_text" \
    "$start_time" "$partial_path" "$final_path" "$status" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    heartbeat_path,
    phase,
    benchmark,
    run_id,
    command,
    start_time,
    partial_path,
    final_path,
    status,
) = sys.argv[1:]

now = datetime.now(timezone.utc)
active_path = Path(final_path) if Path(final_path).exists() else Path(partial_path)
rows = []
file_size = 0
file_mtime = ""
if active_path.exists():
    file_size = active_path.stat().st_size
    file_mtime = datetime.fromtimestamp(
        active_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()
    try:
        payload = json.loads(active_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, dict)]
    except Exception:
        rows = []

verdicts = [str(row.get("verdict", "")).lower() for row in rows]
answer_modes = sorted({str(row.get("answer_mode", "")).lower() for row in rows})
answer_mode = answer_modes[0] if len(answer_modes) == 1 else ("mixed" if answer_modes else "")
last_case_id = str(rows[-1].get("case_id", "")) if rows else ""
pass_count = verdicts.count("pass")
fail_count = verdicts.count("fail")

heartbeat = {
    "phase": phase,
    "run_id": run_id,
    "benchmark": benchmark,
    "status": status,
    "command": command,
    "start_time": start_time,
    "last_seen": now.isoformat(),
    "partial_path": partial_path,
    "final_path": final_path,
    "rows_done": len(rows),
    "last_case_id": last_case_id,
    "pass": pass_count,
    "fail": fail_count,
    "answer_mode": answer_mode,
    "judge_done": pass_count + fail_count,
    "judge_total": 30,
    "file_mtime": file_mtime,
    "file_size": file_size,
}

path = Path(heartbeat_path)
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(heartbeat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
tmp.replace(path)
PY
}

run_eval() {
  local benchmark="$1"
  local data_path="$2"
  local run_id="$3"
  local comparison_report="$4"
  local heartbeat_path="$5"
  local log_path="$6"

  local suffix="$benchmark"
  local partial_path="${EVAL_DIR}/${run_id}_${suffix}.partial.json"
  local final_path="${EVAL_DIR}/${run_id}_${suffix}.json"
  local command_text="MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark ${benchmark} --data-path ${data_path} --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report ${comparison_report} --run-id ${run_id}"
  local start_time
  start_time="$(date -u +%Y-%m-%dT%H:%M:%S%z)"

  write_heartbeat "$heartbeat_path" "$benchmark" "$run_id" "$command_text" \
    "$start_time" "$partial_path" "$final_path" "started"

  (
    while true; do
      sleep 120
      write_heartbeat "$heartbeat_path" "$benchmark" "$run_id" "$command_text" \
        "$start_time" "$partial_path" "$final_path" "running"
    done
  ) &
  local heartbeat_pid="$!"

  MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
    --benchmark "$benchmark" \
    --data-path "$data_path" \
    --baseline memoryos_lite \
    --limit 30 \
    --llm-answer \
    --llm-judge \
    --comparison-report "$comparison_report" \
    --run-id "$run_id" \
    >"$log_path" 2>&1
  local eval_status="$?"

  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true

  if [ "$eval_status" -eq 0 ] && [ -s "$final_path" ]; then
    write_heartbeat "$heartbeat_path" "$benchmark" "$run_id" "$command_text" \
      "$start_time" "$partial_path" "$final_path" "finished"
  else
    write_heartbeat "$heartbeat_path" "$benchmark" "$run_id" "$command_text" \
      "$start_time" "$partial_path" "$final_path" "failed"
  fi

  return "$eval_status"
}

LME_RUN_ID="phase11_lme30_handoff_${RUN_TS}"
LOCOMO_RUN_ID="phase11_locomo30_handoff_${RUN_TS}"
LME_HEARTBEAT="${PHASE_DIR}/eval_heartbeat_longmemeval.json"
LOCOMO_HEARTBEAT="${PHASE_DIR}/eval_heartbeat_locomo.json"
LME_LOG="${PHASE_DIR}/eval_longmemeval_30_${RUN_TS}.log"
LOCOMO_LOG="${PHASE_DIR}/eval_locomo_30_${RUN_TS}.log"

run_eval "longmemeval" "benchmarks/longmemeval/longmemeval.json" \
  "$LME_RUN_ID" \
  ".memoryos/evals/phase10_lme30_packets_20260522T202553Z_longmemeval.json" \
  "$LME_HEARTBEAT" "$LME_LOG" &
lme_pid="$!"

run_eval "locomo" "benchmarks/locomo/locomo10.json" \
  "$LOCOMO_RUN_ID" \
  ".memoryos/evals/phase10_locomo30_packets_20260522T202553Z_locomo.json" \
  "$LOCOMO_HEARTBEAT" "$LOCOMO_LOG" &
locomo_pid="$!"

wait "$lme_pid"
lme_status="$?"
wait "$locomo_pid"
locomo_status="$?"

python3 - "$PHASE_DIR" "$RUN_TS" "$lme_status" "$locomo_status" \
  "$LME_HEARTBEAT" "$LOCOMO_HEARTBEAT" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

phase_dir, run_ts, lme_status, locomo_status, lme_hb, locomo_hb = sys.argv[1:]
summary_path = Path(phase_dir) / f"eval_parallel_30_summary_{run_ts}.json"

def read(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"missing": True, "path": path}
    return json.loads(p.read_text(encoding="utf-8"))

summary = {
    "phase": "phase-11",
    "run_timestamp": run_ts,
    "process_status": {
        "longmemeval": int(lme_status),
        "locomo": int(locomo_status),
    },
    "longmemeval": read(lme_hb),
    "locomo": read(locomo_hb),
}
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY

if [ "$lme_status" -ne 0 ] || [ "$locomo_status" -ne 0 ]; then
  exit 1
fi
