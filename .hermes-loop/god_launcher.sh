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

PROMPT_FILE=".hermes-loop/god_loop_prompt.md"
BOOTSTRAP_STATUS="$(python3 - <<'PY'
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

loop = Path(".hermes-loop")
module_path = loop / "hermes_hardening.py"
spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
print(json.dumps(module.check_execute_bootstrap_gate(loop), ensure_ascii=False))
PY
)"
BOOTSTRAP_ACTION="$(python3 - "$BOOTSTRAP_STATUS" <<'PY'
import json
import sys

print(json.loads(sys.argv[1]).get("action", ""))
PY
)"

if [ "$BOOTSTRAP_ACTION" = "bootstrap_dispatch" ]; then
    BOOTSTRAP_PROMPT=".hermes-loop/bootstrap_prompt.md"
    python3 - "$BOOTSTRAP_STATUS" <<'PY' > "$BOOTSTRAP_PROMPT"
import json
import sys

status = json.loads(sys.argv[1])
phase_id = status.get("phase_id")
blockers = "\n".join(f"- {item}" for item in status.get("blockers", []))
print(f"""You are GOD recovering a MemoryOS Hermes phase protocol violation.

Current phase: `{phase_id}`.

The launcher preflight found that `state.json` says EXECUTE, but required
phase protocol artifacts are missing:

{blockers}

This is an orphan EXECUTE guard. You must NOT run tests, evals, `uv`, pytest,
ruff, or any command that writes `src/`, `tests/`, `docs/`, `.memoryos/`, or
benchmark reports.

Allowed work only:
1. Read `.hermes-loop/state.json`.
2. Read `.hermes-loop/blueprint.md`.
3. Read `.hermes-loop/work/{phase_id}/context_bundle.md`.
4. Read relevant prior phase artifacts named by that context bundle.
5. Write or refresh only these files under `.hermes-loop/work/{phase_id}/`:
   - `interrupted_orphan_execute.md`
   - `phase_status.md`
   - `god_dispatch.json`
   - `brainstorm.md`
   - `spec.md`
   - `plan.md`
   - `plan_review.md`
   - `plan_final.md`

The output must restore the phase to a protocol-complete PLAN/dispatch state.
Do not claim implementation progress. Do not write `ack.json`. Do not mark the
phase complete. Do not modify `state.json` unless you only change the current
state away from unsafe EXECUTE to a planning/dispatch state and record why in
`phase_status.md`.

After writing the allowed phase-local artifacts, stop.""")
PY
    PROMPT_FILE="$BOOTSTRAP_PROMPT"
fi

# Run Codex God in foreground. The model/effort are explicit here so the
# controller does not silently inherit a weaker local default.
{
    echo "===== god_launcher $(date -Iseconds) prompt=$PROMPT_FILE bootstrap_action=$BOOTSTRAP_ACTION ====="
    codex exec --yolo -m gpt-5.5 -c model_reasoning_effort=xhigh -c approval_policy=never "$(< "$PROMPT_FILE")"
} >> .hermes-loop/codex_output.log 2>&1
cleanup
