from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xmuse"))
import auto_discovery


def completed(command: list[str], returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def test_discovers_pytest_failure_lane(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    output = """
FAILED tests/test_memory.py::test_roundtrip - AssertionError: expected stored memory
""".strip()

    def fake_run(command, **kwargs):
        assert command == ["uv", "run", "pytest", "tests/", "-x", "--timeout=60", "-q"]
        return completed(command, 1, stdout=output)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main(["--pytest"]) == 0

    lanes = json.loads(capsys.readouterr().out)
    assert lanes == [
        {
            "feature_id": "auto-pytest-tests-test-memory-py-test-roundtrip",
            "task_type": "execute",
            "prompt": (
                "Fix pytest failure in tests/test_memory.py.\n\n"
                "Exact error message:\n"
                "FAILED tests/test_memory.py::test_roundtrip - "
                "AssertionError: expected stored memory\n\n"
                "Run `uv run pytest tests/ -x --timeout=60 -q` to verify the fix."
            ),
            "capabilities": ["code", "test"],
            "source": "auto",
            "priority": 100,
        }
    ]


def test_discovers_ruff_error_lane(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    output = """
src/memoryos_lite/example.py:3:1: F401 `json` imported but unused
Found 1 error.
""".strip()

    def fake_run(command, **kwargs):
        assert command == ["uv", "run", "ruff", "check", "src/", "xmuse/"]
        return completed(command, 1, stdout=output)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main(["--ruff"]) == 0

    lanes = json.loads(capsys.readouterr().out)
    assert lanes == [
        {
            "feature_id": "auto-ruff-src-memoryos-lite-example-py-3-1-f401",
            "task_type": "execute",
            "prompt": (
                "Fix ruff lint error in src/memoryos_lite/example.py.\n\n"
                "Exact error message:\n"
                "src/memoryos_lite/example.py:3:1: F401 `json` imported but unused\n\n"
                "Run `uv run ruff check src/ xmuse/` to verify the fix."
            ),
            "capabilities": ["code", "test"],
            "source": "auto",
            "priority": 60,
        }
    ]


def test_discovers_mypy_error_lane(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    output = """
src/memoryos_lite/example.py:12: error: Incompatible return value type [return-value]
src/memoryos_lite/example.py:18:5: error: Name "missing" is not defined [name-defined]
Found 2 errors in 1 file (checked 1 source file)
""".strip()

    def fake_run(command, **kwargs):
        assert command == ["uv", "run", "mypy", "src/", "--ignore-missing-imports"]
        return completed(command, 1, stdout=output)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main(["--mypy"]) == 0

    lanes = json.loads(capsys.readouterr().out)
    assert [lane["feature_id"] for lane in lanes] == [
        "auto-mypy-src-memoryos-lite-example-py-12-return-value",
        "auto-mypy-src-memoryos-lite-example-py-18-5-name-defined",
    ]
    assert lanes[0]["task_type"] == "execute"
    assert lanes[0]["capabilities"] == ["code", "test"]
    assert lanes[0]["source"] == "auto"
    assert lanes[0]["priority"] == 80
    assert "Run `uv run mypy src/ --ignore-missing-imports`" in lanes[0]["prompt"]


def test_discovers_low_coverage_test_lane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "files": {
                    "src/memoryos_lite/untested.py": {
                        "summary": {"percent_covered": 42.5}
                    },
                    "src/memoryos_lite/covered.py": {"summary": {"percent_covered": 97.0}},
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_run(command, **kwargs):
        assert command == ["uv", "run", "pytest", "--cov=src", "--cov-report=json"]
        return completed(command, 0)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main(["--coverage"]) == 0

    lanes = json.loads(capsys.readouterr().out)
    assert lanes == [
        {
            "feature_id": "auto-coverage-src-memoryos-lite-untested-py",
            "task_type": "execute",
            "prompt": (
                "Add or improve tests for src/memoryos_lite/untested.py.\n\n"
                "Current coverage is 42.50%, below the 50.00% threshold.\n\n"
                "Run `uv run pytest --cov=src --cov-report=json` to verify coverage."
            ),
            "capabilities": ["code", "test"],
            "source": "auto",
            "priority": 40,
        }
    ]


def test_discovers_todo_cleanup_lane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    code = tmp_path / "src" / "memoryos_lite" / "todo_case.py"
    code.parent.mkdir(parents=True)
    code.write_text(
        "def f():\n"
        "    # TODO: replace placeholder parser\n"
        "    return 1\n"
        "    # normal comment\n",
        encoding="utf-8",
    )

    assert auto_discovery.main(["--git-issues"]) == 0

    lanes = json.loads(capsys.readouterr().out)
    assert lanes == [
        {
            "feature_id": "auto-todo-src-memoryos-lite-todo-case-py-2",
            "task_type": "execute",
            "prompt": (
                "Clean up TODO comment in src/memoryos_lite/todo_case.py:2.\n\n"
                "Comment:\n# TODO: replace placeholder parser\n\n"
                "Resolve the issue or replace it with a tracked, actionable note."
            ),
            "capabilities": ["code", "test"],
            "source": "auto",
            "priority": 20,
        }
    ]


def test_deduplicates_against_existing_feature_lanes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    lanes_path = tmp_path / "xmuse" / "feature_lanes.json"
    lanes_path.parent.mkdir()
    lanes_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {"feature_id": "auto-mypy-src-memoryos-lite-example-py-12-return-value"}
                ]
            }
        ),
        encoding="utf-8",
    )
    output = "src/memoryos_lite/example.py:12: error: Bad return [return-value]"

    def fake_run(command, **kwargs):
        return completed(command, 1, stdout=output)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main(["--mypy"]) == 0

    assert json.loads(capsys.readouterr().out) == []


def test_all_runs_lightweight_sources_and_orders_by_priority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    todo = tmp_path / "src" / "todo_case.py"
    todo.parent.mkdir(parents=True)
    todo.write_text("# TODO: cleanup later\n", encoding="utf-8")
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "files": {
                    "src/low.py": {"summary": {"percent_covered": 10.0}},
                }
            }
        ),
        encoding="utf-8",
    )
    command_outputs = {
        tuple(auto_discovery.RUFF_COMMAND): (
            1,
            "src/b.py:4:1: F401 `json` imported but unused",
        ),
        tuple(auto_discovery.MYPY_COMMAND): (
            1,
            "src/c.py:8: error: Name \"x\" is not defined [name-defined]",
        ),
    }
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        returncode, stdout = command_outputs[tuple(command)]
        return completed(command, returncode, stdout=stdout)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main(["--all"]) == 0

    lanes = json.loads(capsys.readouterr().out)
    assert commands == [
        auto_discovery.RUFF_COMMAND,
        auto_discovery.MYPY_COMMAND,
    ]
    assert [lane["priority"] for lane in lanes] == [80, 60, 20]
    assert [lane["feature_id"].split("-")[1] for lane in lanes] == [
        "mypy",
        "ruff",
        "todo",
    ]


def test_no_flags_defaults_to_lightweight_discovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "coverage.json").write_text(json.dumps({"files": {}}), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return completed(command, 0)

    monkeypatch.setattr(auto_discovery.subprocess, "run", fake_run)

    assert auto_discovery.main([]) == 0

    assert commands == [
        auto_discovery.RUFF_COMMAND,
        auto_discovery.MYPY_COMMAND,
    ]
    assert json.loads(capsys.readouterr().out) == []
