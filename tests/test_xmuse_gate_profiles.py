from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from xmuse_core.gates.coverage import GateCoverageError, validate_test_ownership
from xmuse_core.gates.loader import GateProfileConfigError, load_gate_config
from xmuse_core.gates.models import (
    CURRENT_PRODUCT_ENV,
    CommandPlan,
    CommandSpec,
    GateCommand,
    GatePlan,
    GateProfile,
    GateReport,
    ProfileDefaults,
)
from xmuse_core.gates.resolver import GateProfileResolver, ProfileMismatchError
from xmuse_core.gates.runner import GateRunner


def _write_gate_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _minimal_gate_config() -> dict:
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
                "env": dict(CURRENT_PRODUCT_ENV),
                "commands": [
                    {"command": "pytest", "args": ["-q", "tests/test_v3_path.py"]}
                ],
                "diff_selectors": ["src/memoryos_lite/**"],
                "test_files": ["tests/test_v3_path.py"],
                "test_nodeids": [],
                "test_markers": [],
                "mixed_test_files": [],
            },
            "historical": {
                "description": "Historical",
                "blocking": False,
                "env": {},
                "commands": [],
                "diff_selectors": ["src/memoryos_lite/legacy_paging.py"],
                "test_files": [],
                "test_nodeids": [],
                "test_markers": [],
                "mixed_test_files": [],
            },
        },
    }


def _loaded_config(tmp_path: Path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["profiles"]["xmuse-core"] = {
        "description": "xmuse core",
        "blocking": True,
        "env": {},
        "commands": [
            {"command": "pytest", "args": ["-q", "tests/test_xmuse_master_loop.py"]}
        ],
        "diff_selectors": ["xmuse/**", "src/xmuse_core/**"],
        "test_files": ["tests/test_xmuse_master_loop.py"],
        "test_nodeids": [],
        "test_markers": [],
        "mixed_test_files": [],
    }
    _write_gate_config(config_path, data)
    return load_gate_config(config_path, repo_root=tmp_path)


def test_gate_models_preserve_current_product_env_and_command_argv():
    command = CommandSpec(
        argv=["uv", "run", "pytest"],
        cwd=Path("."),
        timeout_s=0,
        allow_extra_args=True,
    )
    profile = GateProfile(
        profile_id="strict-product",
        description="Current product",
        blocking=True,
        env=CURRENT_PRODUCT_ENV,
        commands=[GateCommand(command="pytest", args=["-q", "tests/test_v3_path.py"])],
        diff_selectors=["src/memoryos_lite/**"],
        test_files=["tests/test_v3_path.py"],
        test_nodeids=[],
        test_markers=[],
        mixed_test_files=[],
    )

    assert command.argv == ["uv", "run", "pytest"]
    assert command.cwd == Path(".")
    assert command.timeout_s == 0
    assert profile.env["MEMORYOS_MEMORY_ARCH"] == "v3"
    assert profile.env["MEMORYOS_RECALL_PIPELINE"] == "v2"
    assert profile.env["MEMORYOS_PAGING_MODE"] == "off"
    assert profile.env["MEMORYOS_AGENT_KERNEL"] == "off"


def test_gate_plan_report_shapes_are_serializable():
    defaults = ProfileDefaults(
        full_gate_profile="strict-product",
        full_gate_interval=20,
        unknown_diff_policy="strict-product",
        unclassified_test_policy="fail",
    )
    plan = GatePlan(
        feature_id="lane-a",
        worktree=Path("."),
        profiles=["strict-product"],
        blocking=True,
        commands=[
            CommandPlan(
                command_id="pytest",
                argv=["uv", "run", "pytest", "-q", "tests/test_v3_path.py"],
                cwd=Path("."),
                timeout_s=0,
                env={"MEMORYOS_MEMORY_ARCH": "v3"},
                profile_id="strict-product",
                blocking=True,
            )
        ],
        resolution_reasons={"strict-product": ["explicit_lane_profile"]},
        changed_paths=["src/memoryos_lite/config.py"],
        warnings=[],
    )
    report = GateReport(
        feature_id="lane-a",
        passed=True,
        blocking_passed=True,
        nonblocking_failures=[],
        profile_ids=["strict-product"],
        resolution_reasons=plan.resolution_reasons,
        command_results=[],
        artifact_dir=Path("xmuse/logs/gates/lane-a"),
        warnings=[],
    )

    assert defaults.full_gate_interval == 20
    assert plan.blocking is True
    assert plan.commands[0].command_id == "pytest"
    assert plan.commands[0].profile_id == "strict-product"
    assert report.passed is True
    assert report.artifact_dir.as_posix() == "xmuse/logs/gates/lane-a"


def test_load_gate_config_parses_strict_schema(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, _minimal_gate_config())

    config = load_gate_config(config_path, repo_root=tmp_path)

    assert config.defaults.full_gate_interval == 20
    assert config.defaults.full_gate_profile == "strict-product"
    assert config.command_catalog["pytest"].argv == ["uv", "run", "pytest"]
    assert config.profiles["strict-product"].blocking is True
    assert config.profiles["historical"].blocking is False


def test_load_gate_config_rejects_unknown_fields(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["profiles"]["strict-product"]["shell"] = "uv run pytest -q"
    _write_gate_config(config_path, data)

    with pytest.raises(GateProfileConfigError, match="unknown field"):
        load_gate_config(config_path, repo_root=tmp_path)


def test_load_gate_config_rejects_command_outside_repo(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["command_catalog"]["pytest"]["cwd"] = "../outside"
    _write_gate_config(config_path, data)

    with pytest.raises(GateProfileConfigError, match="cwd must stay inside repo"):
        load_gate_config(config_path, repo_root=tmp_path)


def test_load_gate_config_rejects_extra_args_when_not_allowed(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["command_catalog"]["pytest"]["allow_extra_args"] = False
    _write_gate_config(config_path, data)

    with pytest.raises(GateProfileConfigError, match="does not allow extra args"):
        load_gate_config(config_path, repo_root=tmp_path)


def test_load_gate_config_rejects_placeholder_strict_product_manifest(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["profiles"]["strict-product"]["test_files"] = []
    _write_gate_config(config_path, data)

    with pytest.raises(GateProfileConfigError, match="strict-product manifest"):
        load_gate_config(config_path, repo_root=tmp_path)


def test_load_gate_config_rejects_empty_blocking_profile_manifest(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["profiles"]["empty-blocking"] = {
        "description": "Empty blocking profile",
        "blocking": True,
        "env": {},
        "commands": [],
        "diff_selectors": ["src/memoryos_lite/retrieval/**"],
        "test_files": [],
        "test_nodeids": [],
        "test_markers": [],
        "mixed_test_files": [],
    }
    _write_gate_config(config_path, data)

    with pytest.raises(GateProfileConfigError, match="blocking profile manifest"):
        load_gate_config(config_path, repo_root=tmp_path)


def test_resolver_uses_explicit_gate_profiles_when_covering_changed_paths(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    plan = resolver.resolve(
        feature_id="lane-a",
        worktree=tmp_path,
        explicit_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
    )

    assert plan.profiles == ["strict-product"]
    assert plan.resolution_reasons["strict-product"] == ["explicit_lane_profile"]
    assert plan.blocking is True


def test_resolver_infers_profile_from_diff_when_no_explicit_profile(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    plan = resolver.resolve(
        feature_id="lane-xmuse",
        worktree=tmp_path,
        explicit_profiles=[],
        changed_paths=["xmuse/master_loop.py"],
    )

    assert plan.profiles == ["xmuse-core"]
    assert plan.resolution_reasons["xmuse-core"] == ["diff_selector"]


def test_resolver_uses_unknown_diff_policy_for_unmatched_path(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    plan = resolver.resolve(
        feature_id="lane-unknown",
        worktree=tmp_path,
        explicit_profiles=[],
        changed_paths=["unknown/file.txt"],
    )

    assert plan.profiles == ["strict-product"]
    assert plan.resolution_reasons["strict-product"] == ["unknown_diff_policy"]


def test_resolver_fails_closed_for_under_scoped_explicit_profile(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    with pytest.raises(ProfileMismatchError, match="missing blocking profile"):
        resolver.resolve(
            feature_id="lane-bad",
            worktree=tmp_path,
            explicit_profiles=["xmuse-core"],
            changed_paths=["src/memoryos_lite/config.py"],
        )


def test_resolver_rejects_explicit_historical_for_current_product_diff(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    with pytest.raises(ProfileMismatchError, match="missing blocking profile"):
        resolver.resolve(
            feature_id="lane-historical-bad",
            worktree=tmp_path,
            explicit_profiles=["historical"],
            changed_paths=["src/memoryos_lite/config.py"],
        )


def test_resolver_unions_multiple_matching_profiles(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    plan = resolver.resolve(
        feature_id="lane-multi",
        worktree=tmp_path,
        explicit_profiles=[],
        changed_paths=["src/memoryos_lite/config.py", "xmuse/master_loop.py"],
    )

    assert plan.profiles == ["strict-product", "xmuse-core"]


def test_resolver_preserves_structured_command_metadata(tmp_path):
    config = _loaded_config(tmp_path)
    resolver = GateProfileResolver(config)

    plan = resolver.resolve(
        feature_id="lane-a",
        worktree=tmp_path,
        explicit_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
    )

    command = plan.commands[0]
    assert command.command_id == "pytest"
    assert command.argv == ["uv", "run", "pytest", "-q", "tests/test_v3_path.py"]
    assert command.cwd == Path(".")
    assert command.timeout_s == 0
    assert command.env["MEMORYOS_MEMORY_ARCH"] == "v3"
    assert command.profile_id == "strict-product"
    assert command.blocking is True


class FakeProcess:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> None:
        self.stdout = stdout.encode()
        self.stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self.stdout, self.stderr


@pytest.mark.asyncio
async def test_gate_runner_executes_commands_and_writes_artifacts(tmp_path, monkeypatch):
    calls: list[tuple[tuple[str, ...], dict]] = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(stdout="ok", returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    config = _loaded_config(tmp_path)
    plan = GateProfileResolver(config).resolve(
        feature_id="lane-a",
        worktree=tmp_path,
        explicit_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
    )

    report = await GateRunner(repo_root=tmp_path).run(plan)

    assert report.passed is True
    assert calls[0][0] == ("uv", "run", "pytest", "-q", "tests/test_v3_path.py")
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[0][1]["env"]["MEMORYOS_MEMORY_ARCH"] == "v3"
    assert report.artifact_dir.exists()
    assert (report.artifact_dir / "report.json").exists()


@pytest.mark.asyncio
async def test_gate_runner_marks_blocking_failure(tmp_path, monkeypatch):
    async def fake_exec(*args, **kwargs):
        return FakeProcess(stderr="boom", returncode=2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    config = _loaded_config(tmp_path)
    plan = GateProfileResolver(config).resolve(
        feature_id="lane-fail",
        worktree=tmp_path,
        explicit_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
    )

    report = await GateRunner(repo_root=tmp_path).run(plan)

    assert report.passed is False
    assert report.blocking_passed is False
    assert report.errors == ["strict-product:pytest failed (exit 2)"]
    assert (report.artifact_dir / "strict-product__pytest.stderr").read_text() == "boom"
    report_json = json.loads((report.artifact_dir / "report.json").read_text())
    assert report_json["command_results"][0]["env"]["MEMORYOS_MEMORY_ARCH"] == "v3"


@pytest.mark.asyncio
async def test_gate_runner_skips_missing_pytest_file_args_when_some_exist(
    tmp_path, monkeypatch
):
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProcess(stdout="ok", returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_v3_path.py").write_text("def test_ok(): pass\n")
    config = _loaded_config(tmp_path)
    profile = config.profiles["strict-product"]
    profile.commands[0].args[:] = [
        "-q",
        "tests/test_xmuse_overnight_runner.py",
        "tests/test_v3_path.py",
    ]
    plan = GateProfileResolver(config).resolve(
        feature_id="lane-missing-test",
        worktree=tmp_path,
        explicit_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
    )

    report = await GateRunner(repo_root=tmp_path).run(plan)

    assert report.passed is True
    assert calls[0] == ("uv", "run", "pytest", "-q", "tests/test_v3_path.py")
    assert report.command_results[0].argv == [
        "uv",
        "run",
        "pytest",
        "-q",
        "tests/test_v3_path.py",
    ]
    assert report.warnings == [
        "skipped missing pytest path for strict-product:pytest: "
        "tests/test_xmuse_overnight_runner.py"
    ]


@pytest.mark.asyncio
async def test_gate_runner_enforces_command_timeout(tmp_path, monkeypatch):
    class SlowProcess:
        returncode = None
        killed = False

        async def communicate(self):
            if not self.killed:
                await asyncio.sleep(10)
            return b"", b"partial stderr"

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            return 124

    async def fake_exec(*args, **kwargs):
        return SlowProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    config = _loaded_config(tmp_path)
    pytest_spec = config.command_catalog["pytest"]
    config.command_catalog["pytest"] = CommandSpec(
        argv=pytest_spec.argv,
        cwd=pytest_spec.cwd,
        timeout_s=1,
        allow_extra_args=pytest_spec.allow_extra_args,
    )
    plan = GateProfileResolver(config).resolve(
        feature_id="lane-timeout",
        worktree=tmp_path,
        explicit_profiles=["strict-product"],
        changed_paths=["src/memoryos_lite/config.py"],
    )

    report = await GateRunner(repo_root=tmp_path).run(plan)

    assert report.passed is False
    assert report.command_results[0].returncode == 124
    assert "command timed out after 1s" in (
        report.artifact_dir / "strict-product__pytest.stderr"
    ).read_text()


def test_validate_test_ownership_accepts_all_files_classified(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_v3_path.py").write_text("def test_a(): pass\n")
    (tests_dir / "test_legacy.py").write_text("def test_b(): pass\n")
    config = _minimal_gate_config()
    config["profiles"]["historical"]["test_files"] = ["tests/test_legacy.py"]
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, config)
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    validate_test_ownership(loaded, tests_root=tests_dir)


def test_validate_test_ownership_rejects_unclassified_file(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_new.py").write_text("def test_new(): pass\n")
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, _minimal_gate_config())
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    with pytest.raises(GateCoverageError, match="unclassified test file"):
        validate_test_ownership(loaded, tests_root=tests_dir)


def test_validate_test_ownership_rejects_mixed_file_without_node_owner(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mixed.py").write_text(
        "def test_current(): pass\n"
        "def test_historical(): pass\n",
        encoding="utf-8",
    )
    config = _minimal_gate_config()
    config["profiles"]["strict-product"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config["profiles"]["historical"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, config)
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    with pytest.raises(GateCoverageError, match="unowned mixed test nodeid"):
        validate_test_ownership(loaded, tests_root=tests_dir)


def test_validate_test_ownership_rejects_async_mixed_node_without_owner(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mixed_async.py").write_text(
        "async def test_current_async(): pass\n",
        encoding="utf-8",
    )
    config = _minimal_gate_config()
    config["profiles"]["strict-product"]["mixed_test_files"] = [
        "tests/test_mixed_async.py"
    ]
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, config)
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    with pytest.raises(
        GateCoverageError,
        match="tests/test_mixed_async.py::test_current_async",
    ):
        validate_test_ownership(loaded, tests_root=tests_dir)


def test_validate_test_ownership_accepts_mixed_file_nodeids(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mixed.py").write_text(
        "def test_current(): pass\n"
        "def test_historical(): pass\n",
        encoding="utf-8",
    )
    config = _minimal_gate_config()
    config["profiles"]["strict-product"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config["profiles"]["strict-product"]["test_nodeids"] = [
        "tests/test_mixed.py::test_current"
    ]
    config["profiles"]["historical"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config["profiles"]["historical"]["test_nodeids"] = [
        "tests/test_mixed.py::test_historical"
    ]
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, config)
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    validate_test_ownership(loaded, tests_root=tests_dir)


def test_validate_test_ownership_accepts_mixed_file_markers(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mixed.py").write_text(
        "import pytest\n"
        "@pytest.mark.strict_product\n"
        "def test_current(): pass\n",
        encoding="utf-8",
    )
    config = _minimal_gate_config()
    config["profiles"]["strict-product"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config["profiles"]["strict-product"]["test_markers"] = ["strict_product"]
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, config)
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    validate_test_ownership(loaded, tests_root=tests_dir)


def test_repository_gate_profiles_config_loads():
    config = load_gate_config(Path("xmuse/gate_profiles.json"), repo_root=Path("."))

    assert config.defaults.full_gate_interval == 20
    assert "strict-product" in config.profiles
    assert config.profiles["strict-product"].blocking is True
    assert config.profiles["historical"].blocking is False
