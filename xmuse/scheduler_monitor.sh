#!/bin/bash
set -euo pipefail

PROJECT="/home/iiyatu/projects/python/memoryOS"
LOOP_ROOT="${XMUSE_LOOP_ROOT:-xmuse}"
INTERVAL_SECONDS="${XMUSE_MONITOR_INTERVAL_SECONDS:-600}"
LOG_FILE="${XMUSE_MONITOR_LOG_FILE:-/tmp/xmuse_scheduler_monitor.log}"
PID_FILE="${XMUSE_MONITOR_PID_FILE:-/tmp/xmuse_scheduler_monitor.pid}"
LOCK_FILE="${XMUSE_MONITOR_LOCK_FILE:-/tmp/xmuse_scheduler_monitor.lock}"

cd "$PROJECT"

exec 8>>"$LOCK_FILE"
if ! flock -n 8; then
    echo "xmuse scheduler monitor already running" >&2
    exit 1
fi

echo "$$" > "$PID_FILE"

log() {
    printf '[%s] %s\n' "$(date -Iseconds)" "$*" >> "$LOG_FILE"
}

cleanup() {
    if [ -f "$PID_FILE" ] && [ "$(cat "$PID_FILE" 2>/dev/null || true)" = "$$" ]; then
        rm -f "$PID_FILE"
    fi
}
trap cleanup EXIT

active_job_state() {
    python3 - <<'PY'
import importlib.util
from pathlib import Path

loop = Path("xmuse")
spec = importlib.util.spec_from_file_location("hermes_hardening", loop / "hermes_hardening.py")
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
status = module.classify_active_job(loop)
state = str(status.get("state") or "unknown")
if state == "exited_or_missing" and status.get("status") == "running":
    module.complete_active_job(loop, exit_code=143, status="failed")
print(state)
PY
}

launcher_alive() {
    local pid=""
    if [ -f "$LOOP_ROOT/run.lock" ]; then
        pid="$(awk -F'[ =]' '/pid=/{print $2}' "$LOOP_ROOT/run.lock" 2>/dev/null || true)"
    fi
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start_master() {
    log "master missing; restarting"
    nohup bash "$LOOP_ROOT/god_launcher.sh" >/tmp/xmuse_master_god_launcher.nohup 2>&1 &
    printf '%s\n' "$!" > /tmp/xmuse_master_god_launcher.pid
}

refresh_report() {
    XMUSE_REPORT_ONLY=1 python3 "$LOOP_ROOT/hermes_reporter.py" \
        >/tmp/xmuse_report_only_monitor.json \
        2>/tmp/xmuse_report_only_monitor.err || true
}

refresh_dispatch() {
    python3 "$LOOP_ROOT/multi_lane_dispatcher.py" --write \
        >/tmp/xmuse_dispatch_monitor.json \
        2>/tmp/xmuse_dispatch_monitor.err || true
}

log "monitor started interval=${INTERVAL_SECONDS}s"
while true; do
    log "scheduler tick"
    refresh_report
    refresh_dispatch

    state="$(active_job_state || echo unknown)"
    if ! launcher_alive || [ "$state" != "running" ]; then
        start_master
        sleep 5
        refresh_report
    else
        log "master alive active_job_state=${state}"
    fi

    sleep "$INTERVAL_SECONDS"
done
