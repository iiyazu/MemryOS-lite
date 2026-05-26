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
    python3 - <<'PY' 8>&-
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
    nohup bash "$LOOP_ROOT/god_launcher.sh" >/tmp/xmuse_master_god_launcher.nohup 2>&1 8>&- &
    printf '%s\n' "$!" > /tmp/xmuse_master_god_launcher.pid
}

refresh_report() {
    XMUSE_REPORT_ONLY=1 python3 "$LOOP_ROOT/hermes_reporter.py" \
        >/tmp/xmuse_report_only_monitor.json \
        2>/tmp/xmuse_report_only_monitor.err 8>&- || true
}

refresh_dispatch() {
    python3 "$LOOP_ROOT/multi_lane_dispatcher.py" --write \
        >/tmp/xmuse_dispatch_monitor.json \
        2>/tmp/xmuse_dispatch_monitor.err 8>&- || true
}

run_master_review_queue() {
    python3 "$LOOP_ROOT/master_review_runner.py" --loop "$LOOP_ROOT" \
        >/tmp/xmuse_master_review_runner.json \
        2>/tmp/xmuse_master_review_runner.err 8>&- || true
}

run_integrated_tests() {
    if pgrep -f "[i]ntegrated_test_runner.py --loop $LOOP_ROOT" >/dev/null 2>&1; then
        log "integrated test pass already running; skipping duplicate"
        return
    fi
    nohup python3 "$LOOP_ROOT/integrated_test_runner.py" --loop "$LOOP_ROOT" \
        >/tmp/xmuse_integrated_test_runner.json \
        2>/tmp/xmuse_integrated_test_runner.err 8>&- &
    printf '%s\n' "$!" > /tmp/xmuse_integrated_test_runner.pid
}

run_master_merge_queue() {
    python3 "$LOOP_ROOT/master_merge_runner.py" --loop "$LOOP_ROOT" --execute \
        >/tmp/xmuse_master_merge_runner.json \
        2>/tmp/xmuse_master_merge_runner.err 8>&- || true
}

dispatch_has_queued_jobs() {
    python3 "$LOOP_ROOT/slave_job_runner.py" has-queued --loop "$LOOP_ROOT" 8>&-
}

start_queued_slave_jobs() {
    python3 "$LOOP_ROOT/slave_job_runner.py" start-queued --loop "$LOOP_ROOT" \
        >/tmp/xmuse_slave_job_runner.json \
        2>/tmp/xmuse_slave_job_runner.err 8>&- || true
}

slave_jobs_need_master_reconcile() {
    python3 "$LOOP_ROOT/slave_job_runner.py" needs-master --loop "$LOOP_ROOT" 8>&-
}

master_has_review_or_merge_queue() {
    python3 - <<'PY' 8>&-
import json
from pathlib import Path

path = Path("xmuse/master_status.json")
try:
    status = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
queues = status.get("queues", {})
if queues.get("master_review_queue") or queues.get("merge_queue"):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

log "monitor started interval=${INTERVAL_SECONDS}s"
while true; do
    log "scheduler tick"
    refresh_report
    refresh_dispatch
    log "scheduler tick slave dispatch pass"
    start_queued_slave_jobs
    log "scheduler tick integrated test pass"
    run_integrated_tests
    log "scheduler tick master merge pass"
    run_master_merge_queue
    refresh_report
    refresh_dispatch
    if master_has_review_or_merge_queue; then
        log "master review or merge queue has work; running deterministic master review pass"
        run_master_review_queue
        run_integrated_tests
        run_master_merge_queue
        refresh_report
        refresh_dispatch
    fi

    state="$(active_job_state || echo unknown)"
    if [ "$state" = "completed" ]; then
        if dispatch_has_queued_jobs; then
            log "master completed but dispatch has queued jobs; continuing slave execution"
            start_queued_slave_jobs
            run_integrated_tests
            run_master_merge_queue
            refresh_report
            if master_has_review_or_merge_queue; then
                log "master review or merge queue has work; restarting master for decision"
                start_master
                sleep 5
                refresh_report
            fi
            if slave_jobs_need_master_reconcile; then
                log "slave jobs finished; restarting master for reconcile"
                start_master
                sleep 5
                refresh_report
            fi
            sleep "$INTERVAL_SECONDS" 8>&-
            continue
        fi
        log "master completed; monitor stopping"
        refresh_report
        exit 0
    fi
    if ! launcher_alive || [ "$state" != "running" ]; then
        if master_has_review_or_merge_queue || slave_jobs_need_master_reconcile; then
            log "master needs decision work; restarting"
            start_master
            sleep 5
            refresh_report
        else
            log "master not running and no master decision work; leaving stopped"
        fi
    else
        log "master alive active_job_state=${state}"
    fi

    sleep "$INTERVAL_SECONDS" 8>&-
done
