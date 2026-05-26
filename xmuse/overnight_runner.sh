#!/bin/bash
# Overnight runner with restart-on-self-modify and smoke test
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

MAX_HOURS="${XMUSE_MAX_HOURS:-10}"
START_TIME=$(date +%s)
ROUND=0

log() { echo "[$(date -Iseconds)] $*"; }

smoke_test() {
    log "Running smoke test..."
    if ! uv run python -c "
from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.manager import SessionManager
from xmuse_core.agents.registry import AgentRegistry, AgentRuntime
print('smoke: OK')
" 2>&1; then
        log "SMOKE TEST FAILED — rolling back"
        git checkout -- src/xmuse_core/agents/ xmuse/master_loop.py xmuse/xmuse_main.py
        return 1
    fi
    return 0
}

check_timeout() {
    local now=$(date +%s)
    local elapsed=$(( (now - START_TIME) / 3600 ))
    if [ "$elapsed" -ge "$MAX_HOURS" ]; then
        log "Global timeout reached (${elapsed}h >= ${MAX_HOURS}h). Stopping."
        exit 0
    fi
}

# Tag current state for rollback
git tag -f "xmuse-overnight-start" HEAD 2>/dev/null || true
mkdir -p xmuse/logs

while true; do
    ROUND=$((ROUND + 1))
    check_timeout
    log "=== Round $ROUND ==="

    # Run master_loop.py (it exits when queue is empty)
    uv run python xmuse/master_loop.py \
        --lanes xmuse/feature_lanes.json \
        --config xmuse/agents.json \
        --concurrency 2 2>&1 | tee "xmuse/logs/round_${ROUND}.log" || true

    # Check if self-modification happened
    if git diff --name-only 2>/dev/null | grep -qE "master_loop|xmuse_main|agents/"; then
        log "Self-modification detected. Restarting after smoke test."
        git add -u
        git commit -m "chore(xmuse): auto-commit round $ROUND self-improvement" || true
        if ! smoke_test; then
            log "Smoke failed. Continuing with previous version."
        fi
    fi

    # Check if there are new lanes to process
    PENDING=$(python3 -c "
import json
lanes = json.loads(open('xmuse/feature_lanes.json').read()).get('lanes', [])
pending = [l for l in lanes if l.get('status') not in ('done', 'failed')]
print(len(pending))
" 2>/dev/null || echo "0")

    if [ "$PENDING" -eq 0 ]; then
        log "No pending lanes. Exiting."
        break
    fi

    log "Pending lanes: $PENDING. Continuing..."
done

log "Overnight run complete. $ROUND rounds executed."
