#!/bin/bash
set -euo pipefail

PROJECT="/home/iiyatu/projects/python/memoryOS"
cd "$PROJECT"

INTERVAL_SECONDS="${XMUSE_MONITOR_INTERVAL_SECONDS:-600}"
PID_FILE="${XMUSE_MONITOR_PID_FILE:-/tmp/xmuse_scheduler_monitor.pid}"
NOHUP_FILE="${XMUSE_MONITOR_NOHUP_FILE:-/tmp/xmuse_scheduler_monitor.nohup}"

if [ -f "$PID_FILE" ]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "xmuse scheduler monitor already running pid=$pid"
        exit 0
    fi
fi

setsid -f env XMUSE_MONITOR_INTERVAL_SECONDS="$INTERVAL_SECONDS" \
    bash xmuse/scheduler_monitor.sh >"$NOHUP_FILE" 2>&1

for _ in 1 2 3 4 5; do
    sleep 1
    if [ -f "$PID_FILE" ]; then
        pid="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "xmuse scheduler monitor started pid=$pid interval=${INTERVAL_SECONDS}s"
            exit 0
        fi
    fi
done

echo "xmuse scheduler monitor failed to start" >&2
cat "$NOHUP_FILE" >&2 2>/dev/null || true
exit 1
