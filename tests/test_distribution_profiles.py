"""Packaging boundaries for the local-only sidecar."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from memoryos_lite import __version__
from memoryos_lite.api.app import app
from memoryos_lite.capabilities import MissingOptionalCapabilityError, require_remote_capability

ROOT = Path(__file__).resolve().parents[1]


def test_full_local_profile_keeps_remote_and_benchmark_stacks_optional() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    dependencies = "\n".join(project["dependencies"])
    assert "fastembed" not in dependencies
    assert "langchain" not in dependencies
    assert "langgraph" not in dependencies
    assert "qdrant" not in dependencies

    extras = project["optional-dependencies"]
    assert any(item.startswith("fastembed") for item in extras["full-local"])
    assert any(item.startswith("langchain-core") for item in extras["remote"])
    assert any(item.startswith("qdrant-client") for item in extras["remote"])
    assert extras["benchmark"] == ["memoryos-lite[remote]"]
    assert project["version"] == __version__ == app.version == "0.2.1"


def test_cli_and_api_import_without_remote_stack() -> None:
    """The full-local API entrypoint must not eagerly import remote extras."""
    code = """
import builtins

original_import = builtins.__import__
blocked = {"langchain_core", "langchain_openai", "langgraph", "qdrant_client"}

def guarded_import(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise ModuleNotFoundError(name)
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import memoryos_lite.cli
import memoryos_lite.api.app
from pathlib import Path
from tempfile import TemporaryDirectory
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
with TemporaryDirectory() as temp_dir:
    service = MemoryOSService(
        settings=Settings(
            data_dir=Path(temp_dir),
            memoryos_embedding_provider="none",
            memoryos_agent_kernel="external",
        )
    )
assert service.settings.resolved_agent_kernel == "external"
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_remote_capability_error_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("memoryos_lite.capabilities.find_spec", lambda _name: None)

    with pytest.raises(MissingOptionalCapabilityError) as raised:
        require_remote_capability("eval.public")

    assert str(raised.value) == (
        "memoryos capability 'eval.public' is unavailable; "
        "install memoryos-lite[remote] "
        "(missing: langchain_core, langchain_openai, langgraph, qdrant_client)"
    )
