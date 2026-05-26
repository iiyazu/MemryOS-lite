from __future__ import annotations

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
        FakeProcess(0, b"tests passed\n"),
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(0, b" 3 files changed, 12 insertions(+), 1 deletion(-)\n"),
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
    assert result.checks == {"pytest": True, "ruff": True, "diff_sanity": True}
    assert calls == [
        (("uv", "run", "pytest", "tests/", "-x", "-q"), tmp_path),
        (("uv", "run", "ruff", "check", "src/", "xmuse/"), tmp_path),
        (("git", "diff", "--stat", "HEAD~1"), tmp_path),
    ]


@pytest.mark.asyncio
async def test_quality_gate_collects_subprocess_failure_output(
    monkeypatch, tmp_path: Path
) -> None:
    results = [
        FakeProcess(1, b"failed stdout\n", b"failed stderr\n"),
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(0, b" 1 file changed, 2 insertions(+)\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is False
    assert result.checks == {"pytest": False, "ruff": True, "diff_sanity": True}
    assert len(result.errors) == 1
    assert "pytest failed" in result.errors[0]
    assert "failed stdout" in result.errors[0]
    assert "failed stderr" in result.errors[0]


@pytest.mark.asyncio
async def test_quality_gate_fails_diff_sanity_over_insertions_limit(
    monkeypatch, tmp_path: Path
) -> None:
    results = [
        FakeProcess(0, b"tests passed\n"),
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(0, b" 42 files changed, 1001 insertions(+), 3 deletions(-)\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is False
    assert result.checks == {"pytest": True, "ruff": True, "diff_sanity": False}
    assert result.errors == [
        "diff_sanity failed: 1001 insertions exceeds limit of 1000\n"
        " 42 files changed, 1001 insertions(+), 3 deletions(-)"
    ]


@pytest.mark.asyncio
async def test_quality_gate_reports_diff_command_failure(monkeypatch, tmp_path: Path) -> None:
    results = [
        FakeProcess(0, b"tests passed\n"),
        FakeProcess(0, b"ruff passed\n"),
        FakeProcess(128, b"", b"fatal: bad revision 'HEAD~1'\n"),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "xmuse_core.agents.quality_gate.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await QualityGate().check(tmp_path)

    assert result.passed is False
    assert result.checks == {"pytest": True, "ruff": True, "diff_sanity": False}
    assert result.errors == ["diff_sanity failed (exit 128)\nfatal: bad revision 'HEAD~1'"]
