#!/bin/bash
# God Launcher with flock + parallel heartbeat
LOCKFILE="/home/iiyatu/projects/python/memoryOS/xmuse/run.lock"
HBFILE="/home/iiyatu/projects/python/memoryOS/xmuse/heartbeat.log"
LOOP_ROOT="xmuse"
CODEX_OUTPUT="$LOOP_ROOT/codex_output.log"
IDLE_TIMEOUT_SECONDS="${XMUSE_CODEX_IDLE_TIMEOUT_SECONDS:-${HERMES_CODEX_IDLE_TIMEOUT_SECONDS:-10800}}"
ATTEMPT="${XMUSE_CODEX_ATTEMPT:-${HERMES_CODEX_ATTEMPT:-1}}"
cd /home/iiyatu/projects/python/memoryOS

exec 9>>"$LOCKFILE"
if ! flock -n 9; then
    echo "God already running (lock held)"
    exit 1
fi

: > "$LOCKFILE"
echo "pid=$$ run_id=$(date -Iseconds)" > "$LOCKFILE"

LAUNCHER_PID=$$
ACTIVE_JOB_WRITTEN=0
ACTIVE_JOB_COMPLETED=0
CODEX_PID=""

complete_active_job_if_needed() {
    if [ "$ACTIVE_JOB_WRITTEN" = "1" ] && [ "$ACTIVE_JOB_COMPLETED" != "1" ]; then
        local status="failed"
        local exit_code=143
        python3 - "$exit_code" "$status" <<'PY'
import importlib.util
import sys
from pathlib import Path

loop = Path("xmuse")
module_path = loop / "hermes_hardening.py"
spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
module.complete_active_job(
    loop,
    exit_code=int(sys.argv[1]),
    status=sys.argv[2],
)
PY
    fi
}

cleanup() {
    complete_active_job_if_needed
    if [ -n "${CODEX_PID:-}" ]; then
        kill "$CODEX_PID" 2>/dev/null || true
        wait "$CODEX_PID" 2>/dev/null || true
    fi
    if [ -n "${HB_PID:-}" ]; then
        kill "$HB_PID" 2>/dev/null || true
        wait "$HB_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Parallel heartbeat writer — writes every 30s independent of Codex
(
    n=0
    while kill -0 "$LAUNCHER_PID" 2>/dev/null; do
        n=$((n+1))
        echo "GOD alive$(printf '%02d' $n) $(date -u -Iseconds)" >> "$HBFILE"
        sleep 30
    done
) &
HB_PID=$!

MASTER_STATE_FILE="$LOOP_ROOT/master_state.json"
MASTER_PROMPT_FILE="$LOOP_ROOT/prompts/master_god_prompt.md"
MASTER_CONFIG_FILE="$LOOP_ROOT/master_config.json"
MASTER_BLUEPRINT_FILE="$LOOP_ROOT/master_blueprint.md"
MASTER_DISPATCH_TEMPLATE="$LOOP_ROOT/contracts/master_dispatch_template.json"
PROMPT_FILE="$MASTER_PROMPT_FILE"
BOOTSTRAP_STATUS="$(python3 - <<'PY'
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

loop = Path("xmuse")
module_path = loop / "hermes_hardening.py"
spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
print(json.dumps(module.resolve_active_controller(loop), ensure_ascii=False))
PY
)"
BOOTSTRAP_ACTION="$(python3 - "$BOOTSTRAP_STATUS" <<'PY'
import json
import sys

print(json.loads(sys.argv[1]).get("source", ""))
PY
)"

if [ "$BOOTSTRAP_ACTION" != "master" ]; then
    BOOTSTRAP_PROMPT="$LOOP_ROOT/bootstrap_master_prompt.md"
    python3 - "$BOOTSTRAP_STATUS" <<'PY' > "$BOOTSTRAP_PROMPT"
import json
import sys

status = json.loads(sys.argv[1])
errors = "\n".join(f"- {item}" for item in status.get("errors", [])) or "- no detail"
print(f"""You are Hermes Master God bootstrap guard.

The launcher did not find an active Master controller.

Controller source: `{status.get("source")}`.
Errors:
{errors}

Read xmuse/master_state.json, xmuse/master_config.json,
xmuse/master_blueprint.md, xmuse/prompts/master_god_prompt.md,
and xmuse/contracts/master_dispatch_template.json before acting.
Legacy root-loop files under xmuse/legacy/root-loop/ are audit history
and must not drive active execution.

Do not run product tests, evals, or write product files from this guard prompt.
Write only a Master-control status note if needed, then stop.""")
PY
    PROMPT_FILE="$BOOTSTRAP_PROMPT"
fi

PHASE_ID="master-control"

# Run Codex God with an explicit active-job registry. The model/effort are
# explicit here so the controller does not silently inherit a weaker local
# default.
{
    echo "===== god_launcher $(date -Iseconds) prompt=$PROMPT_FILE bootstrap_action=$BOOTSTRAP_ACTION ====="
    echo "===== master_files state=$MASTER_STATE_FILE config=$MASTER_CONFIG_FILE blueprint=$MASTER_BLUEPRINT_FILE dispatch=$MASTER_DISPATCH_TEMPLATE ====="
    codex exec --yolo -m gpt-5.5 -c model_reasoning_effort=xhigh -c approval_policy=never "$(< "$PROMPT_FILE")" &
    CODEX_PID=$!
    python3 - "$CODEX_PID" "$PHASE_ID" "$PROMPT_FILE" "$ATTEMPT" "$IDLE_TIMEOUT_SECONDS" <<'PY'
import importlib.util
import sys
from pathlib import Path

loop = Path("xmuse")
module_path = loop / "hermes_hardening.py"
spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
module.write_active_job(
    loop,
    pid=int(sys.argv[1]),
    phase_id=sys.argv[2] or None,
    prompt_file=sys.argv[3],
    attempt=int(sys.argv[4]),
    output_path="codex_output.log",
    idle_timeout_seconds=int(sys.argv[5]),
)
PY
    ACTIVE_JOB_WRITTEN=1
    wait "$CODEX_PID"
    CODEX_EXIT=$?
    if [ "$CODEX_EXIT" -eq 0 ]; then
        CODEX_STATUS="completed"
    else
        CODEX_STATUS="failed"
    fi
    python3 - "$CODEX_EXIT" "$CODEX_STATUS" <<'PY'
import importlib.util
import sys
from pathlib import Path

loop = Path("xmuse")
module_path = loop / "hermes_hardening.py"
spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
module.complete_active_job(
    loop,
    exit_code=int(sys.argv[1]),
    status=sys.argv[2],
)
PY
    ACTIVE_JOB_COMPLETED=1
} >> "$CODEX_OUTPUT" 2>&1
exit "$CODEX_EXIT"
