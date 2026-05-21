# DEPRECATED: 使用 god_launcher.sh + god_loop_prompt.md 作为唯一入口
# 此文件保留仅供参考，不要运行
#!/usr/bin/env python3
"""Hermes Loop v2 — 轻量状态机。Python 处理机械状态，Codex 处理推理状态。"""
import json, subprocess, sys, time
from pathlib import Path

# DEPRECATED: 唯一入口是 god_launcher.sh + god_loop_prompt.md
print('hermes_loop.py is DEPRECATED. Use god_launcher.sh instead.'); sys.exit(1)
from datetime import datetime, timezone

PROJECT = Path("/home/iiyatu/projects/python/memoryOS")
LOOP = PROJECT / ".hermes-loop"
STATE_FILE = LOOP / "state.json"

MAX_ITER = 50
CODEX_TIMEOUT = 10800  # 20 min

def _read_state():
    return json.loads(STATE_FILE.read_text())

def _write_state(state):
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

def _phase(state):
    idx = state.get("current_phase_idx", 0)
    phases = state.get("phases", [])
    return phases[idx] if idx < len(phases) else None

def _codex(short_prompt, workdir=PROJECT, state_name=""):
    """Minimal Codex call — methodology in prompts/*.md, Codex reads them."""
    full = f"""你是 Hermes Loop 的自治代理节点。工作目录:

⚠️ 自治模式: 没有用户交互。直接产出文件，不要等待批准。
   跳过所有 "ask user" / "wait for approval" / "user reviews" 步骤。
   你被注入的 superpowers skill 中的交互步骤一律跳过，直接产出最终结果。 {PROJECT}

## ⚠️ 心跳规则 (必须遵守)
每 5-10 分钟，在 .hermes-loop/heartbeat.log 末尾追加一行:
  格式: {state_name} alive{{N}} {{timestamp}}
  示例: PLAN_STORM alive03 2026-05-21T10:30:00
  从 alive01 开始，每次递增。这是你活着的唯一证明。不写心跳 = 被认为已死。

## 核心规则
1. 先读 .hermes-loop/prompts/ 下你的角色 prompt (god.md / plan_agent.md / execute_agent.md / review_agent.md)
2. 读 .hermes-loop/state.json 了解当前状态
3. 读 .hermes-loop/contracts/state_machine.json 了解状态机
4. 执行下述任务，产出文件到 .hermes-loop/
5. 更新 .hermes-loop/state.json 推进到下一状态

{short_prompt}

重要: 每次完成状态后必须更新 state.json 的 current_state。
不要做任务外的事。不要闲聊。
"""
    # Start heartbeat writer in background
    import threading, datetime as _dt
    hb_file = LOOP / "heartbeat.log"
    stop_hb = threading.Event()
    def _write_hb():
        n = 0
        while not stop_hb.is_set():
            n += 1
            ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
            hb_file.write_text((hb_file.read_text() if hb_file.exists() else "") + f"{state_name} alive{n:02d} {ts}\n")
            stop_hb.wait(30)
    hb_thread = threading.Thread(target=_write_hb, daemon=True)
    hb_thread.start()

    try:
        result = subprocess.run(
            ["codex", "exec", "--yolo", full],
            cwd=str(workdir), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=CODEX_TIMEOUT
        )
        # Tee to log file for real-time observation
        log_path = LOOP / "codex_output.log"
        with open(log_path, "a") as lf:
            lf.write(f"\n=== {state_name} {__import__('datetime').datetime.now().isoformat()} ===\n")
            for line in result.stdout.split("\n"):
                lf.write(line + "\n")
        result.stdout = result.stdout  # already captured
        ok = result.returncode == 0
        tail = (result.stdout or "")[-2000:]
        stop_hb.set()
        # Also write full output to log
        log_path = LOOP / "codex_output.log"
        with open(log_path, "a") as lf:
            lf.write(f"\n=== exit={result.returncode} ===\n")
        return ok, tail
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


# ── Fast Python handlers ─────────────────────────────────────

def do_god_dispatch(state):
    """Python: 从 blueprint 提取 phase 信息生成 dispatch JSON。"""
    phase = _phase(state)
    if not phase:
        state["current_state"] = "DONE"
        _write_state(state)
        return True

    blueprint = (LOOP / "blueprint.md").read_text()
    pid = phase["id"]
    pname = phase["name"]
    target = phase.get("target_state", "unknown")

    # Extract phase description from blueprint
    marker = f"### {phase['id'].replace('phase-', 'Phase ')}"
    start = blueprint.find(marker)
    if start < 0:
        marker = f"### {pname}"
        start = blueprint.find(marker)
    if start < 0:
        print(f"  [WARN] Phase {pid} not found in blueprint, using minimal dispatch")
        desc = phase.get("name", pid)
    else:
        # Find next phase marker
        next_marker = blueprint.find("\n### ", start + len(marker))
        if next_marker < 0:
            next_marker = len(blueprint)
        section = blueprint[start:next_marker]
        desc = section.strip()

    tasks_line = ""
    for line in desc.split("\n"):
        if line.strip().startswith("- "):
            tasks_line += line.strip() + "\n"

    dispatch = {
        "phase": pid,
        "phase_index": state["current_phase_idx"],
        "phase_name": pname,
        "target_state": target,
        "task_description": f"从 blueprint.md 的 {pid} 段提取的任务。\n{tasks_line}",
        "for_plan_agent": {
            "goal": f"完成 {pname} 的所有任务。详细描述见 blueprint.md 的 {pid} 段。",
            "constraints": [
                f"目标兼容状态: {target}",
                "遵守 blueprint.md 中的兼容性要求",
                "遵守 CLAUDE.md 中的约定"
            ],
            "relevant_files": [
                ".hermes-loop/blueprint.md",
                "CLAUDE.md",
                "src/memoryos_lite/"
            ],
            "design_notes": f"从 blueprint.md 的 {pid} 段提取设计要点"
        },
        "for_review_agent": {
            "tests_must_pass": True,
            "regression_bar": "zero unintended regressions",
            "spec_checklist": ["验收项从 blueprint 的 Acceptance 段提取"],
            "benchmark_commands": ["uv run pytest -q"],
            "benchmark_pass_threshold": "311 passed, hard eval 1.00/1.00"
        }
    }

    (LOOP / "god_dispatch.json").write_text(
        json.dumps(dispatch, indent=2, ensure_ascii=False) + "\n")

    state["current_state"] = "PLAN_STORM"
    phase["status"] = "in_progress"
    _write_state(state)
    print(f"  [OK] god_dispatch.json → PLAN_STORM")
    return True


def do_ack(state):
    """Python: trivial state flip."""
    state["current_state"] = "GOD_ADVANCE"
    state["iter_count"] = 0
    _write_state(state)
    print("  [OK] ACK → GOD_ADVANCE")
    return True


# ── Codex handlers ───────────────────────────────────────────

def _codex(short_prompt, state_name, workdir=PROJECT):
    full = f"""你是 Hermes Loop 的自治代理节点。工作目录:

⚠️ 自治模式: 没有用户交互。直接产出文件，不要等待批准。
   跳过所有 "ask user" / "wait for approval" / "user reviews" 步骤。
   你被注入的 superpowers skill 中的交互步骤一律跳过，直接产出最终结果。 {PROJECT}

## 心跳规则 (必须遵守)
每 5-10 分钟，在 .hermes-loop/heartbeat.log 末尾追加一行:
  格式: {state_name} alive{{N}} {{timestamp}}
  示例: PLAN_STORM alive03 2026-05-21T10:30:00
  从 alive01 开始，每次递增。这是你活着的唯一证明。

## 核心规则
1. 读 .hermes-loop/prompts/ 下你的角色 prompt
2. 读 .hermes-loop/state.json
3. 读 .hermes-loop/contracts/state_machine.json
4. 执行下述任务，产出文件到 .hermes-loop/
5. 完成后更新 state.json 的 current_state

{short_prompt}

重要: 每次完成状态后必须更新 state.json。不做任务外的事。
"""
    import threading, datetime as _dt, io

    # Start heartbeat writer in background
    hb_file = LOOP / "heartbeat.log"
    stop_hb = threading.Event()
    def _write_hb():
        n = 0
        while not stop_hb.is_set():
            n += 1
            ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
            hb_file.write_text((hb_file.read_text() if hb_file.exists() else "") + f"{state_name} alive{n:02d} {ts}\n")
            stop_hb.wait(30)
    hb_thread = threading.Thread(target=_write_hb, daemon=True)
    hb_thread.start()

    # Start Codex with real-time log
    log_path = LOOP / "codex_output.log"
    with open(log_path, "a") as lf:
        lf.write(f"\n=== {state_name} {_dt.datetime.now().isoformat()} ===\n")

    try:
        proc = subprocess.Popen(
            ["codex", "exec", "--yolo", full],
            cwd=str(workdir), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        output_lines = []
        for line in iter(proc.stdout.readline, ""):
            output_lines.append(line)
            with open(log_path, "a") as lf:
                lf.write(line)
        proc.wait(timeout=CODEX_TIMEOUT)
        ok = proc.returncode == 0
        tail = "".join(output_lines[-100:]) if output_lines else ""
    except subprocess.TimeoutExpired:
        proc.kill()
        ok = False
        tail = "TIMEOUT"
        with open(log_path, "a") as lf:
            lf.write(f"\n=== TIMEOUT after {CODEX_TIMEOUT}s ===\n")
    except Exception as e:
        ok = False
        tail = str(e)

    with open(log_path, "a") as lf:
        lf.write(f"=== exit={proc.returncode if 'proc' in dir() else '?'} ===\n")

    stop_hb.set()
    return ok, tail

def do_plan_storm(state):
    return _codex("""## 执行 PLAN_STORM
读 god_dispatch.json，读项目代码。brainstorming 2-3 种方案 → brainstorm.md。
然后 state.json: current_state = "PLAN_DRAFT"
""", "PLAN_STORM")

def do_plan_draft(state):
    return _codex("""## 执行 PLAN_DRAFT
读 brainstorm.md + god_dispatch.json。写 spec.md + plan.md (bite-sized, TDD)。
然后 state.json: current_state = "PLAN_SELF_REVIEW"
""", "PLAN_DRAFT")

def do_plan_self_review(state):
    return _codex("""## 执行 PLAN_SELF_REVIEW
审查 spec.md+plan.md。PASS → plan_final.md → state: EXECUTE。
FAIL → 迭代(max 3), 超限 → GOD_ADJUST
""", "PLAN_SELF_REVIEW")

def do_execute(state):
    return _codex("""## 执行 EXECUTE
读 plan_final.md。TDD: RED→GREEN→REFACTOR。uv run pytest -q 全量确认。
汇总到 result.md → state: EXECUTE_SELF_REVIEW
""", "EXECUTE")

def do_execute_self_review(state):
    return _codex("""## 执行 EXECUTE_SELF_REVIEW
内审 result.md。修小问题。大问题 → execute_review.md。
state: REVIEW
""", "EXECUTE_SELF_REVIEW")

def do_review(state):
    phase = _phase(state)
    return _codex(f"""## 执行 REVIEW (phase: {phase['id']})
读 god_dispatch.for_review_agent + result.md + execute_review.md + git diff。
ALL PASS → ack.json → state: ACK
FAIL(iter<3) → review_verdict.json → state: EXECUTE
iter>=3 → escalate.json → state: GOD_ADJUST
""", "REVIEW")

def do_god_advance(state):
    phase = _phase(state)
    idx = state["current_phase_idx"]
    return _codex(f"""## 执行 GOD_ADVANCE
读 ack.json。
1. git commit: git add -A && git commit -m "[{phase['id']}] ACK: {phase['name']}"
2. 反思 → reflect_{phase['id']}.md
3. 如需调整 → 更新 blueprint.md
4. 推进: idx={idx}/{len(state['phases'])} → GOD_DISPATCH or DONE
""", "GOD_ADVANCE")

def do_god_adjust(state):
    return _codex("""## 执行 GOD_ADJUST
读 escalate.json。分析根因 → 拆分/放宽/重设/放弃。
更新 blueprint.md + state.json → GOD_DISPATCH
""", "GOD_ADJUST")



HANDLERS = {
    "GOD_DISPATCH": ("py", do_god_dispatch),
    "PLAN_STORM": ("codex", do_plan_storm),
    "PLAN_DRAFT": ("codex", do_plan_draft),
    "PLAN_SELF_REVIEW": ("codex", do_plan_self_review),
    "EXECUTE": ("codex", do_execute),
    "EXECUTE_SELF_REVIEW": ("codex", do_execute_self_review),
    "REVIEW": ("codex", do_review),
    "ACK": ("py", do_ack),
    "GOD_ADVANCE": ("codex", do_god_advance),
    "GOD_ADJUST": ("codex", do_god_adjust),
}


def main():
    print("=" * 60)
    print("Hermes Loop v2")
    print(f"Project: {PROJECT}")
    print("=" * 60)

    for i in range(MAX_ITER):
        state = _read_state()
        cs = state.get("current_state", "")

        if cs == "DONE":
            print(f"\n\U0001F3C1 DONE at iter {i+1}")
            break

        handler_type, handler = HANDLERS.get(cs, (None, None))
        if not handler:
            print(f"[FATAL] Unknown state: {cs}")
            sys.exit(1)

        phase = _phase(state)
        pid = phase["id"] if phase else "?"
        print(f"\n-- Iter {i+1} | {cs} | {pid} ({handler_type}) --")

        if handler_type == "py":
            ok = handler(state)
        else:
            ok, out = handler(state)
            print(f"  codex: {'OK' if ok else 'FAIL'}")
            if not ok:
                print(f"  tail: {out[-500:]}")

        if not ok:
            print(f"[HALT] State {cs} failed.")
            sys.exit(1)

        time.sleep(3)

    else:
        print(f"\n\u26a0\ufe0f  Max iter {MAX_ITER}")

    print("\nDone.")


if __name__ == "__main__":
    main()
