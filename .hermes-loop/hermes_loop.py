#!/usr/bin/env python3
"""Hermes Loop v2 — 轻量状态机。Python 处理机械状态，Codex 处理推理状态。"""
import json, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path("/home/iiyatu/projects/python/memoryOS")
LOOP = PROJECT / ".hermes-loop"
STATE_FILE = LOOP / "state.json"

MAX_ITER = 50
CODEX_TIMEOUT = 1200  # 20 min

def _read_state():
    return json.loads(STATE_FILE.read_text())

def _write_state(state):
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

def _phase(state):
    idx = state.get("current_phase_idx", 0)
    phases = state.get("phases", [])
    return phases[idx] if idx < len(phases) else None

def _codex(short_prompt, workdir=PROJECT):
    """Minimal Codex call — methodology in prompts/*.md, Codex reads them."""
    full = f"""你是 Hermes Loop 的代理节点。工作目录: {PROJECT}

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
    try:
        result = subprocess.run(
            ["codex", "exec", "--yolo", full],
            cwd=str(workdir), capture_output=True, text=True, timeout=CODEX_TIMEOUT
        )
        ok = result.returncode == 0
        tail = (result.stdout or "")[-2000:]
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

def do_plan_storm(state):
    pid = _phase(state)["id"]
    return _codex(f"""## 执行 PLAN_STORM

读 .hermes-loop/god_dispatch.json。这是当前要设计的 phase。读相关项目代码了解现状。

启动 brainstorming (你内部的多方案对比):
- 探讨 2-3 种实现方案
- 对比优劣
- 给出推荐方案

输出到 .hermes-loop/brainstorm.md

然后更新 state.json: current_state = "PLAN_DRAFT"
""")

def do_plan_draft(state):
    return _codex(f"""## 执行 PLAN_DRAFT

读 .hermes-loop/brainstorm.md 和 .hermes-loop/god_dispatch.json。

1. 写 spec.md — 设计文档
2. 写 plan.md — 实现步骤 (bite-sized, 精确文件路径, TDD 形式)

然后更新 state.json: current_state = "PLAN_SELF_REVIEW"
""")

def do_plan_self_review(state):
    return _codex(f"""## 执行 PLAN_SELF_REVIEW

审查 spec.md 和 plan.md。对照 god_dispatch.json 的 God 要求。
如果 PASS → 定稿为 plan_final.md → state.json: current_state = "EXECUTE"
如果 FAIL → 迭代修改 (max 3), 超限 → current_state = "GOD_ADJUST"
""")

def do_execute(state):
    return _codex(f"""## 执行 EXECUTE

读 .hermes-loop/plan_final.md。每个 task 严格 TDD:
1. RED: 写测试 → uv run pytest 确认 FAIL
2. GREEN: 写最小实现 → uv run pytest 确认 PASS  
3. REFACTOR: 清理
4. 全量: uv run pytest -q 确认无回归

汇总到 result.md。然后 state.json: current_state = "EXECUTE_SELF_REVIEW"
""")

def do_execute_self_review(state):
    return _codex(f"""## 执行 EXECUTE_SELF_REVIEW

内审 result.md 的代码改动。修小问题。大问题记录到 execute_review.md。
然后 state.json: current_state = "REVIEW"
""")

def do_review(state):
    phase = _phase(state)
    return _codex(f"""## 执行 REVIEW (phase: {phase['id']})

读 god_dispatch.json.for_review_agent (验收指标), result.md, execute_review.md, git diff。

审查并决策:
- ALL PASS → ack.json → state.json: current_state = "ACK"
- FAIL (iter < 3) → review_verdict.json (FAIL) → state.json: current_state = "EXECUTE"
- iter >= 3 → escalate.json → state.json: current_state = "GOD_ADJUST"
""")

def do_god_advance(state):
    phase = _phase(state)
    idx = state["current_phase_idx"]
    return _codex(f"""## 执行 GOD_ADVANCE

读 ack.json。

Step 1: git commit:
```bash
git -C {PROJECT} add -A
git -C {PROJECT} commit -m "[{phase['id']}] ACK: {phase['name']} — checkpoint"
```

Step 2: 反思 — 这个 phase 完成后，剩余蓝图需要调整吗？输出到 reflect_{phase['id']}.md

Step 3: 如果需要调整，更新 blueprint.md

Step 4: 推进 — 标记 phase completed。当前 phase_idx={idx}, 总共 {len(state['phases'])} phases。
有下一 phase → state.json: current_phase_idx += 1, current_state = "GOD_DISPATCH"
没有 → state.json: current_state = "DONE"
""")

def do_god_adjust(state):
    return _codex(f"""## 执行 GOD_ADJUST

读 escalate.json。分析根因，决策 (拆分/放宽/重设/放弃)。
更新 blueprint.md + state.json。然后 current_state = "GOD_DISPATCH"
""")


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
            print(f"\n🏁 DONE at iter {i+1}")
            break

        handler_type, handler = HANDLERS.get(cs, (None, None))
        if not handler:
            print(f"[FATAL] Unknown state: {cs}")
            sys.exit(1)

        phase = _phase(state)
        pid = phase["id"] if phase else "?"
        print(f"\n── Iter {i+1} | {cs} | {pid} ({handler_type}) ──")

        if handler_type == "py":
            ok = handler(state)
        else:
            ok, out = handler(state)
            print(f"  codex: {'OK' if ok else 'FAIL'}")
            if not ok:
                print(f"  tail: {out[-500:]}")

        if not ok:
            print(f"[HALT] State {cs} failed. Check .hermes-loop/")
            sys.exit(1)

        time.sleep(3)

    else:
        print(f"\n⚠️  Max iter {MAX_ITER}")

    print("\nDone.")


if __name__ == "__main__":
    main()
