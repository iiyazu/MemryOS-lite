#!/usr/bin/env python3
"""Hermes Scheduler + Reporter — 监控存活, 死时启动 God, 生成报告, 不改代码或 state.json."""
import importlib.util
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

LOOP = Path("/home/iiyatu/projects/python/memoryOS/.hermes-loop")
PROJECT = LOOP.parent
LAUNCHER = LOOP / "god_launcher.sh"
STATE_FILE = LOOP / "state.json"
LOCK_FILE = LOOP / "run.lock"


def controller_hardening_report(s):
    """Return current phase control-plane hardening status if available."""
    ex = s.get("execute_lane", {})
    phase_id = ex.get("phase")
    if not phase_id:
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
        if phase_id == "phase-8":
            return module._run_phase8(LOOP, PROJECT / ".memoryos" / "evals", write=True)
        return module.run_phase_hardening(
            LOOP,
            PROJECT / ".memoryos" / "evals",
            phase_id,
            write=True,
        )
    except Exception as exc:
        return {"error": str(exc)}


def _load_hardening_module():
    module_path = LOOP / "hermes_hardening.py"
    if not module_path.exists():
        module_path = Path(__file__).with_name("hermes_hardening.py")
    if not module_path.exists():
        return None, {"error": "missing hermes_hardening.py"}
    spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
    if spec is None or spec.loader is None:
        return None, {"error": "cannot load hermes_hardening.py"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, None


def master_slave_report():
    """Return optional master/slave feature-lane summary."""
    module, error = _load_hardening_module()
    if error:
        return error
    try:
        summary = module.summarize_master_slave_control(LOOP, project_root=PROJECT)
        module.write_master_slave_status(LOOP, summary)
        return summary
    except Exception as exc:
        return {"error": str(exc)}


def master_report() -> dict:
    """Return active Master control-plane status, if Master exists."""
    module, error = _load_hardening_module()
    if error:
        return {
            "version": "1.0",
            "source": "missing_hardening",
            "activation_state": None,
            "counts": {"total": 0, "reviewable": 0, "mergeable": 0, "held": 0, "blocked": 0, "merged": 0},
            "queues": {},
            "errors": [error["error"]],
        }
    controller = module.resolve_active_controller(LOOP)
    if controller["source"] == "master":
        return module.write_master_status(LOOP, controller["state"])
    state = controller.get("state") if isinstance(controller.get("state"), dict) else {}
    return {
        "version": "1.0",
        "source": controller["source"],
        "activation_state": state.get("activation_state"),
        "counts": {"total": 0, "reviewable": 0, "mergeable": 0, "held": 0, "blocked": 0, "merged": 0},
        "queues": {},
        "errors": controller.get("errors", []),
    }


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
        lines = [line for line in hb.read_text().strip().split("\n") if line.strip()]
        if not lines:
            return grace_period
        hb_ts = lines[-1].split()[-1]
        hb_dt = datetime.fromisoformat(hb_ts)
        age = (datetime.now(UTC) - hb_dt).total_seconds()
        if age < 1200:
            return True
        return grace_period and age < 1500  # 25min grace for restarts
    except Exception:
        return grace_period


def generate_report(s):
    now = datetime.now(UTC)
    god_alive = is_god_alive()

    # Heartbeat
    hb = LOOP / "heartbeat.log"
    hb_last = ""
    hb_age = None
    if hb.exists():
        lines = [line for line in hb.read_text().strip().split("\n") if line.strip()]
        if lines:
            hb_last = lines[-1]
            try:
                hb_ts = hb_last.split()[-1]
                hb_dt = datetime.fromisoformat(hb_ts)
                hb_age = (now - hb_dt).total_seconds()
            except Exception:
                pass

    # Dirty files
    dirty = subprocess.run(
        ["git", "-C", str(PROJECT), "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    ex = s.get("execute_lane", {})
    pl = s.get("plan_lane", {})
    hardening = controller_hardening_report(s)
    master = master_report()
    master_slave = master_slave_report()

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
        "master": master,
        "phases": [
            {"id": p["id"], "name": p["name"], "status": p["status"]}
            for p in s.get("phases", [])
        ],
        "dirty_files": dirty[:500] if dirty else "(clean)",
        "action": "wait" if god_alive else "start"
    }
    if hardening is not None:
        report["controller_hardening"] = hardening
    if master_slave is not None:
        report["master_slave"] = master_slave
    return report


def start_god() -> bool:
    """Safely start God. Returns True if God confirmed running after start."""
    if is_god_alive():
        return True
    subprocess.Popen(
        ["bash", str(LAUNCHER)],
        cwd=str(PROJECT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait and verify — use grace period for fresh start
    for _ in range(6):
        time.sleep(5)
        if is_god_alive(grace_period=True):
            return True
    return False


def main():
    s = json.loads(STATE_FILE.read_text())

    done = s.get("current_state") == "DONE"
    god_alive = is_god_alive()
    action = "done" if done else "wait"
    if not done and not god_alive:
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
    if report.get("master_slave"):
        counts = report["master_slave"].get("counts", {})
        md += (
            "\n"
            f"Master/slave features: {counts.get('features', 0)} total, "
            f"{counts.get('reviewable', 0)} reviewable, "
            f"{counts.get('mergeable', 0)} mergeable, "
            f"{counts.get('blocked', 0)} blocked.\n"
        )
    (reports_dir / "latest.md").write_text(md)
    return report


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2, ensure_ascii=False))
