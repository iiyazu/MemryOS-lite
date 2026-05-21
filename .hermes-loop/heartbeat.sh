#!/bin/bash
# Hermes Loop heartbeat — check if loop is alive, restart if dead
STATE_FILE="/home/iiyatu/projects/python/memoryOS/.hermes-loop/state.json"
LOOP_DIR="/home/iiyatu/projects/python/memoryOS"

STATE=$(python3 -c "import json; s=json.load(open('$STATE_FILE')); print(s['current_state'])" 2>/dev/null || echo "ERROR")
PHASE=$(python3 -c "import json; s=json.load(open('$STATE_FILE')); print(s['current_phase_idx'])" 2>/dev/null || echo "?")
ALIVE=$(pgrep -f "hermes_loop.py" | wc -l)

if [ "$STATE" = "DONE" ]; then
    echo "✅ DONE. All phases complete. Heartbeat stopping."
    exit 0
fi

if [ "$ALIVE" -eq 0 ]; then
    echo "⚠️  Loop DEAD (state=$STATE). Restarting..."
    cd "$LOOP_DIR" && nohup python3 .hermes-loop/hermes_loop.py > /tmp/hermes_loop.log 2>&1 &
    echo "🔄 Restarted. PID=$!"
else
    echo "💓 ALIVE | state=$STATE | phase=$PHASE | pids=$ALIVE"
fi
