#!/usr/bin/env bash
set -u

PHASE_ID="phase-17"
PHASE_DIR=".hermes-loop/work/${PHASE_ID}"
EVAL_DIR=".memoryos/evals"
BASELINE_RUN_ID="phase17_locomo10_baseline_r3"
REPAIR_RUN_ID="phase17_locomo10_kernel_repair_smoke_r3"
BENCHMARK="locomo"
DATA_PATH="benchmarks/locomo/locomo10.json"
LIMIT="10"

mkdir -p "$PHASE_DIR" "$EVAL_DIR"

write_heartbeat() {
  local heartbeat_path="$1"
  local run_id="$2"
  local command_text="$3"
  local start_time="$4"
  local partial_path="$5"
  local final_path="$6"
  local status="$7"
  local summary_path="${8:-}"

  python3 - "$heartbeat_path" "$PHASE_ID" "$BENCHMARK" "$run_id" "$command_text" \
    "$start_time" "$partial_path" "$final_path" "$status" "$summary_path" "$LIMIT" <<'PY'
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
    summary_path,
    expected_total,
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
summary = Path(summary_path) if summary_path else None

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
    "judge_total": int(expected_total),
    "file_mtime": file_mtime,
    "file_size": file_size,
}
if summary is not None:
    heartbeat["summary_path"] = str(summary)
    heartbeat["summary_exists"] = summary.exists()

path = Path(heartbeat_path)
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(heartbeat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
tmp.replace(path)
PY
}

run_eval() {
  local run_id="$1"
  local heartbeat_path="$2"
  local log_path="$3"
  local command_text="$4"
  local summary_path="${5:-}"
  local partial_path="${EVAL_DIR}/${run_id}_${BENCHMARK}.partial.json"
  local final_path="${EVAL_DIR}/${run_id}_${BENCHMARK}.json"
  local start_time
  start_time="$(date -u +%Y-%m-%dT%H:%M:%S%z)"

  write_heartbeat "$heartbeat_path" "$run_id" "$command_text" \
    "$start_time" "$partial_path" "$final_path" "started" "$summary_path"

  (
    while true; do
      sleep 120
      write_heartbeat "$heartbeat_path" "$run_id" "$command_text" \
        "$start_time" "$partial_path" "$final_path" "running" "$summary_path"
    done
  ) &
  local heartbeat_pid="$!"

  bash -lc "$command_text" >"$log_path" 2>&1
  local eval_status="$?"

  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true

  if [ "$eval_status" -eq 0 ] && [ -s "$final_path" ]; then
    write_heartbeat "$heartbeat_path" "$run_id" "$command_text" \
      "$start_time" "$partial_path" "$final_path" "completed" "$summary_path"
  else
    write_heartbeat "$heartbeat_path" "$run_id" "$command_text" \
      "$start_time" "$partial_path" "$final_path" "failed" "$summary_path"
  fi

  return "$eval_status"
}

BASELINE_COMMAND="MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path ${DATA_PATH} --baseline memoryos_lite --limit ${LIMIT} --run-id ${BASELINE_RUN_ID} --llm-answer --llm-judge"
REPAIR_SUMMARY="${EVAL_DIR}/${REPAIR_RUN_ID}_${BENCHMARK}_repair_smoke_summary.json"
REPAIR_COMMAND="MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path ${DATA_PATH} --baseline memoryos_lite --limit ${LIMIT} --run-id ${REPAIR_RUN_ID} --repair-smoke-baseline-report ${EVAL_DIR}/${BASELINE_RUN_ID}_${BENCHMARK}.json --llm-answer --llm-judge"

run_eval \
  "$BASELINE_RUN_ID" \
  "${PHASE_DIR}/eval_heartbeat_${BASELINE_RUN_ID}.json" \
  "${PHASE_DIR}/${BASELINE_RUN_ID}.log" \
  "$BASELINE_COMMAND"
baseline_status="$?"

if [ "$baseline_status" -ne 0 ]; then
  exit "$baseline_status"
fi

run_eval \
  "$REPAIR_RUN_ID" \
  "${PHASE_DIR}/eval_heartbeat_${REPAIR_RUN_ID}.json" \
  "${PHASE_DIR}/${REPAIR_RUN_ID}.log" \
  "$REPAIR_COMMAND" \
  "$REPAIR_SUMMARY"
repair_status="$?"

exit "$repair_status"
