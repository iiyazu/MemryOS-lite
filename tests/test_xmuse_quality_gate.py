from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.agents.quality_gate import QualityGate


class FakeProcess:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_quality_gate_passes_when_all_checks_succeed(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], Path]] = []
    results = [
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(0, b" 3 files changed, 12 insertions(+), 1 deletion(-)\n"),
        FakeProcess(0, b"src/xmuse_core/agents/quality_gate.py\n"),
        FakeProcess(0, b"targeted tests passed\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        calls.append((cmd, kwargs["cwd"]))
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.checks == {
        "ruff": True,
        "diff_sanity": True,
        "targeted_pytest": True,
    }
    assert calls == [
        (("uv", "run", "ruff", "check", "src/", "xmuse/"), tmp_path),
        (("git", "diff", "--stat", "HEAD~1"), tmp_path),
        (("git", "diff", "--name-only", "HEAD~1"), tmp_path),
        (("uv", "run", "pytest", "tests/test_config.py", "-x", "-q"), tmp_path),
    ]


@pytest.mark.asyncio
async def test_quality_gate_collects_subprocess_failure_output(
    monkeypatch, tmp_path: Path
) -> None:
    results = [
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(0, b" 1 file changed, 2 insertions(+)\n"),
        FakeProcess(0, b"tests/test_memory.py\n"),
        FakeProcess(1, b"failed stdout\n", b"failed stderr\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is False
    assert result.checks == {
        "ruff": True,
        "diff_sanity": True,
        "targeted_pytest": False,
    }
    assert len(result.errors) == 1
    assert "targeted_pytest failed" in result.errors[0]
    assert "failed stdout" in result.errors[0]
    assert "failed stderr" in result.errors[0]


@pytest.mark.asyncio
async def test_quality_gate_fails_diff_sanity_over_insertions_limit(
    monkeypatch, tmp_path: Path
) -> None:
    results = [
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(0, b" 42 files changed, 1001 insertions(+), 3 deletions(-)\n"),
        FakeProcess(0, b"src/memoryos_lite/config.py\n"),
        FakeProcess(0, b"targeted tests passed\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is False
    assert result.checks == {
        "ruff": True,
        "diff_sanity": False,
        "targeted_pytest": True,
    }
    assert result.errors == [
        "diff_sanity failed: 1001 insertions exceeds limit of 1000\n"
        " 42 files changed, 1001 insertions(+), 3 deletions(-)"
    ]


@pytest.mark.asyncio
async def test_quality_gate_reports_diff_command_failure(monkeypatch, tmp_path: Path) -> None:
    results = [
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(128, b"", b"fatal: bad revision 'HEAD~1'\n"),
        FakeProcess(128, b"", b"fatal: bad revision 'HEAD~1'\n"),
        FakeProcess(0, b"targeted tests passed\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is False
    assert result.checks == {
        "ruff": True,
        "diff_sanity": False,
        "targeted_pytest": True,
    }
    assert result.errors == ["diff_sanity failed (exit 128)\nfatal: bad revision 'HEAD~1'"]


def _quality_gate_config_dict() -> dict:
    return {
        "schema_version": 1,
        "defaults": {
            "full_gate_profile": "strict-product",
            "full_gate_interval": 20,
            "unknown_diff_policy": "strict-product",
            "unclassified_test_policy": "fail",
        },
        "command_catalog": {
            "pytest": {
                "argv": ["uv", "run", "pytest"],
                "cwd": ".",
                "timeout_s": 0,
                "allow_extra_args": True,
            }
        },
        "profiles": {
            "strict-product": {
                "description": "Current product",
                "blocking": True,
                "env": {
                    "MEMORYOS_MEMORY_ARCH": "v3",
                    "MEMORYOS_RECALL_PIPELINE": "v2",
                    "MEMORYOS_PAGING_MODE": "off",
                    "MEMORYOS_AGENT_KERNEL": "off",
                },
                "commands": [
                    {"command": "pytest", "args": ["-q", "tests/test_v3_path.py"]}
                ],
                "diff_selectors": ["src/memoryos_lite/**"],
                "test_files": ["tests/test_v3_path.py"],
                "test_nodeids": [],
                "test_markers": [],
                "mixed_test_files": [],
            }
        },
    }


def _write_quality_gate_config(path: Path) -> None:
    path.write_text(json.dumps(_quality_gate_config_dict(), indent=2), encoding="utf-8")


@pytest.mark.asyncio
async def test_quality_gate_uses_profile_runner_when_configured(tmp_path):
    from xmuse_core.gates.loader import load_gate_config
    from xmuse_core.gates.models import GateReport

    config_path = tmp_path / "gate_profiles.json"
    _write_quality_gate_config(config_path)
    reports: list[GateReport] = []

    class FakeRunner:
        async def run(self, plan):
            report = GateReport(
                feature_id=plan.feature_id,
                passed=True,
                blocking_passed=True,
                nonblocking_failures=[],
                profile_ids=plan.profiles,
                resolution_reasons=plan.resolution_reasons,
                command_results=[],
                artifact_dir=tmp_path / "logs",
                warnings=[],
            )
            reports.append(report)
            return report

    gate = QualityGate(profile_config_path=config_path, repo_root=tmp_path)
    gate._profile_config = load_gate_config(config_path, repo_root=tmp_path)
    gate._runner = FakeRunner()

    result = await gate.check(
        tmp_path,
        feature_id="lane-a",
        gate_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
        base_head_sha="abc123",
    )

    assert result.passed is True
    assert result.checks["gate_profiles"] is True
    assert reports[0].profile_ids == ["strict-product"]


@pytest.mark.asyncio
async def test_quality_gate_changed_paths_uses_base_head_sha(tmp_path, monkeypatch):
    calls: list[tuple[str, ...]] = []

    async def fake_run(worktree, *cmd):
        calls.append(cmd)
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": "src/memoryos_lite/config.py\n"},
        )()

    gate = QualityGate()
    monkeypatch.setattr(gate, "_run", fake_run)

    changed, warnings = await gate._changed_paths(tmp_path, base_head_sha="abc123")

    assert changed == ["src/memoryos_lite/config.py"]
    assert warnings == []
    assert calls == [("git", "diff", "--name-only", "abc123...HEAD")]


@pytest.mark.asyncio
async def test_quality_gate_changed_paths_uses_merge_base_for_legacy_lane(
    tmp_path,
    monkeypatch,
):
    calls: list[tuple[str, ...]] = []

    async def fake_run(worktree, *cmd):
        calls.append(cmd)
        if cmd[:3] == ("git", "merge-base", "HEAD"):
            return type("Result", (), {"returncode": 0, "stdout": "merge-base-sha\n"})()
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": "xmuse/master_loop.py\n"},
        )()

    gate = QualityGate()
    monkeypatch.setattr(gate, "_run", fake_run)

    changed, warnings = await gate._changed_paths(tmp_path, base_head_sha=None)

    assert changed == ["xmuse/master_loop.py"]
    assert warnings == ["legacy_diff_base_inferred"]
    assert calls[-1] == ("git", "diff", "--name-only", "merge-base-sha...HEAD")


@pytest.mark.asyncio
async def test_quality_gate_fails_closed_when_profile_diff_collection_fails(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "gate_profiles.json"
    _write_quality_gate_config(config_path)

    async def fake_run(worktree, *cmd):
        return type(
            "Result",
            (),
            {
                "returncode": 128,
                "stdout": "",
                "stderr": "fatal: bad revision\n",
                "output": "fatal: bad revision",
            },
        )()

    gate = QualityGate(profile_config_path=config_path, repo_root=tmp_path)
    monkeypatch.setattr(gate, "_run", fake_run)

    result = await gate.check(
        tmp_path,
        feature_id="lane-a",
        gate_profiles=["historical"],
        base_head_sha="bad-base",
    )

    assert result.passed is False
    assert result.checks == {"gate_profiles": False}
    assert "diff_collection_failed" in result.errors[0]
