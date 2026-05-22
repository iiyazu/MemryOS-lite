#!/usr/bin/env python3
"""Hermes Scheduler + Reporter — 监控存活, 死时启动 God, 生成报告, 不改代码或 state.json."""
import json, subprocess, os, time
from pathlib import Path
from datetime import datetime, timezone
import importlib.util

LOOP = Path("/home/iiyatu/projects/python/memoryOS/.hermes-loop")
PROJECT = LOOP.parent
LAUNCHER = LOOP / "god_launcher.sh"
STATE_FILE = LOOP / "state.json"
LOCK_FILE = LOOP / "run.lock"


def phase8_hardening_report(s):
    """Return phase-8 eval/ACK status if the additive hardening module is present."""
    ex = s.get("execute_lane", {})
    if ex.get("phase") != "phase-8":
        return None
    module_path = LOOP / "hermes_hardening.py"
    if not module_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
        if spec is None or spec.loader is None:
            return {"error": "cannot load hermes_hardening.py"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._run_phase8(LOOP, PROJECT / ".memoryos" / "evals", write=True)
    except Exception as exc:
        return {"error": str(exc)}


def read_lock_pid() -> int | None:
    """Return the PID recorded in run.lock, if any."""
    if not LOCK_FILE.exists():
        return None
    try:
        content = LOCK_FILE.read_text()
        pid_str = content.split("pid=")[1].split()[0]
        return int(pid_str)
    except Exception:
        return None


def lock_status() -> str:
    """Return a stable lock status without mutating the filesystem."""
    pid = read_lock_pid()
    if pid is None:
        return "missing"
    try:
        os.kill(pid, 0)
        return "ok"
    except ProcessLookupError:
        return "stale"
    except PermissionError:
        return "unknown"
    except Exception:
        return "unknown"


def is_god_alive(grace_period: bool = False) -> bool:
    """God is alive if lock PID exists AND (heartbeat fresh OR in grace period)."""
    if lock_status() != "ok":
        return False
    hb = LOOP / "heartbeat.log"
    if not hb.exists():
        return grace_period  # Fresh start, no heartbeat yet
    try:
        lines = [l for l in hb.read_text().strip().split("\n") if l.strip()]
        if not lines:
            return grace_period
        hb_ts = lines[-1].split()[-1]
        hb_dt = datetime.fromisoformat(hb_ts)
        age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
        if age < 1200:
            return True
        return grace_period and age < 1500  # 25min grace for restarts
    except:
        return grace_period

def generate_report(s):
    now = datetime.now(timezone.utc)
    god_alive = is_god_alive()
    
    # Heartbeat
    hb = LOOP / "heartbeat.log"
    hb_last = ""
    hb_age = None
    if hb.exists():
        lines = [l for l in hb.read_text().strip().split("\n") if l.strip()]
        if lines:
            hb_last = lines[-1]
            try:
                hb_ts = hb_last.split()[-1]
                hb_dt = datetime.fromisoformat(hb_ts)
                hb_age = (now - hb_dt).total_seconds()
            except:
                pass
    
    # Dirty files
    dirty = subprocess.run(["git", "-C", str(PROJECT), "status", "--short"], capture_output=True, text=True).stdout.strip()
    
    ex = s.get("execute_lane", {})
    pl = s.get("plan_lane", {})
    hardening = phase8_hardening_report(s)
    
    report = {
        "timestamp": now.isoformat(),
        "report_age_seconds": 0,
        "stale": not is_god_alive() and lock_status() in ("stale", "ok"),
        "god": {
            "alive": god_alive,
            "heartbeat_last": hb_last[-80:] if hb_last else "",
            "heartbeat_age_seconds": hb_age
        },
        "lock": {
            "exists": LOCK_FILE.exists(),
            "status": lock_status()
        },
        "execute_lane": {"phase": ex.get("phase"), "state": ex.get("state")},
        "plan_lane": {"phase": pl.get("phase"), "state": pl.get("state")},
        "research_lane": s.get("research_lane", {}).get("phases", []),
        "phases": [{"id": p["id"], "name": p["name"], "status": p["status"]} for p in s.get("phases", [])],
        "dirty_files": dirty[:500] if dirty else "(clean)",
        "action": "wait" if god_alive else "start"
    }
    if hardening is not None:
        report["phase8_hardening"] = hardening
    return report

def start_god() -> bool:
    """Safely start God. Returns True if God confirmed running after start."""
    if is_god_alive():
        return True
    subprocess.Popen(["bash", str(LAUNCHER)], cwd=str(PROJECT),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait and verify — use grace period for fresh start
    for _ in range(6):
        time.sleep(5)
        if is_god_alive(grace_period=True):
            return True
    return False

def main():
    s = json.loads(STATE_FILE.read_text())
    
    # If DONE, exit silently
    if s.get("current_state") == "DONE":
        return
    
    god_alive = is_god_alive()
    action = "wait"
    if not god_alive:
        started = start_god()
        god_alive = started
        action = "started_ok" if started else "started_failed"
    
    # Generate report (report uses is_god_alive() without grace)
    report = generate_report(s)
    report["action"] = action
    
    reports_dir = LOOP / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "latest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    
    # Markdown
    hb_age = report["god"].get("heartbeat_age_seconds")
    hb_str = f"{hb_age:.0f}s ago" if hb_age is not None else "—"
    
    md = f"""# Hermes Report — {report['timestamp'][:19]}Z

| Field | Value |
|-------|-------|
| God   | {"🟢" if god_alive else "🔴"} |
| Exec  | {report['execute_lane']['phase']} / {report['execute_lane']['state']} |
| Plan  | {report['plan_lane']['phase']} / {report['plan_lane']['state']} |
| HB    | {hb_str} |
| Action| {action} |
"""
    (reports_dir / "latest.md").write_text(md)
    return report

if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2, ensure_ascii=False))
