#!/bin/bash
# God Launcher with flock + parallel heartbeat
LOCKFILE="/home/iiyatu/projects/python/memoryOS/.hermes-loop/run.lock"
HBFILE="/home/iiyatu/projects/python/memoryOS/.hermes-loop/heartbeat.log"
cd /home/iiyatu/projects/python/memoryOS

exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "God already running (lock held)"
    exit 1
fi

echo "pid=$$ run_id=$(date -Iseconds)" > "$LOCKFILE"

cleanup() { rm -f "$LOCKFILE"; kill $HB_PID 2>/dev/null; }
trap cleanup EXIT

# Parallel heartbeat writer — writes every 30s independent of Codex
(
    n=0
    while true; do
        n=$((n+1))
        echo "GOD alive$(printf '%02d' $n) $(date -u -Iseconds)" >> "$HBFILE"
        sleep 30
    done
) &
HB_PID=$!

# Run codex in foreground
codex exec --yolo "$(< .hermes-loop/god_loop_prompt.md)"
cleanup
