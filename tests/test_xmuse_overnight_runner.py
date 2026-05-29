from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def test_overnight_runner_ignores_preround_dirty_agent_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "xmuse").mkdir(exist_ok=True)
    shutil.copy(Path("xmuse/overnight_runner.sh"), repo / "xmuse" / "overnight_runner.sh")
    (repo / "src" / "xmuse_core" / "agents").mkdir(parents=True)
    dirty_file = repo / "src" / "xmuse_core" / "agents" / "existing.py"
    dirty_file.write_text("before\n")

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True, text=True)
    dirty_file.write_text("before\nuser dirty change\n")

    fake_bin = repo / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "python3").write_text("#!/bin/sh\nprintf '0\\n'\n")
    os.chmod(fake_bin / "uv", 0o755)
    os.chmod(fake_bin / "python3", 0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["XMUSE_MAX_HOURS"] = "1"

    result = subprocess.run(
        ["bash", "xmuse/overnight_runner.sh"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Self-modification detected" not in result.stdout
    assert dirty_file.read_text() == "before\nuser dirty change\n"
