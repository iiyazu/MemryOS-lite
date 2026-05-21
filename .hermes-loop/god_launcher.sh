#!/bin/bash
# God Launcher with flock mutual exclusion
LOCKFILE="/home/iiyatu/projects/python/memoryOS/.hermes-loop/run.lock"
cd /home/iiyatu/projects/python/memoryOS

exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "God already running (lock held)"
    exit 1
fi

echo "pid=$$ run_id=$(date -Iseconds)" > "$LOCKFILE"

cleanup() { rm -f "$LOCKFILE"; }
trap cleanup EXIT

# Run codex in foreground (no exec — trap needs parent shell alive)
codex exec --yolo "$(< .hermes-loop/god_loop_prompt.md)"
cleanup
