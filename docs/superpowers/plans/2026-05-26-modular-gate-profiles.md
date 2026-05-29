# Modular Gate Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hard-coded xmuse full-gate commands with configuration-driven modular gate profiles, preserve lane gate metadata, and change full quality gate cadence to 20 successful normal lanes.

**Architecture:** Add a focused `xmuse_core.gates` package for profile loading, resolution, execution, and reporting. `TaskDescriptor` carries gate metadata and `base_head_sha` from `feature_lanes.json`; `QualityGate` and `MasterLoop` both call the same `GateProfileResolver -> GateRunner -> GateReport` path. `xmuse/gate_profiles.json` owns profile definitions and test manifests.

**Tech Stack:** Python 3.11, dataclasses, JSON config, asyncio subprocesses, pytest, ruff, existing xmuse master loop and quality gate code.

---

## File Structure

- Create `src/xmuse_core/gates/__init__.py`: public exports for gate profile APIs.
- Create `src/xmuse_core/gates/models.py`: dataclasses for config, command specs, plans, reports, and resolution details.
- Create `src/xmuse_core/gates/loader.py`: strict JSON loading and validation for `xmuse/gate_profiles.json`.
- Create `src/xmuse_core/gates/resolver.py`: explicit/diff/unknown profile resolution and profile mismatch logic.
- Create `src/xmuse_core/gates/runner.py`: structured command execution, env overlay, artifact writing, and `GateReport` construction.
- Create `src/xmuse_core/gates/coverage.py`: profile test ownership guard for files, nodeids, and pytest markers.
- Create `xmuse/gate_profiles.json`: first profile configuration with real strict-product manifest and full gate interval 20.
- Modify `src/xmuse_core/agents/consumer.py`: extend `TaskDescriptor` with gate metadata.
- Modify `src/xmuse_core/agents/quality_gate.py`: delegate lane-local gate execution to gate profiles while preserving `GateResult` compatibility.
- Modify `xmuse/master_loop.py`: remove hard-coded full gate command constants, preserve gate metadata in `load_lanes()`, use configured interval 20, generate full gate lanes with `gate_profiles=["strict-product"]`, and run full gates through `GateRunner`.
- Modify `tests/test_xmuse_master_loop.py`: update full-gate interval/profile tests and metadata propagation tests.
- Modify `tests/test_xmuse_quality_gate.py`: update lane-local gate tests for profile-backed execution.
- Create `tests/test_xmuse_gate_profiles.py`: loader, resolver, runner, report, and coverage guard tests.

## Task 1: Gate Data Models

**Files:**
- Create: `src/xmuse_core/gates/__init__.py`
- Create: `src/xmuse_core/gates/models.py`
- Test: `tests/test_xmuse_gate_profiles.py`

- [ ] **Step 1: Write failing model tests**

Add this file with the initial tests:

```python
from __future__ import annotations

from pathlib import Path

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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.gates'`.

- [ ] **Step 3: Implement models**

Create `src/xmuse_core/gates/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CURRENT_PRODUCT_ENV: dict[str, str] = {
    "MEMORYOS_MEMORY_ARCH": "v3",
    "MEMORYOS_RECALL_PIPELINE": "v2",
    "MEMORYOS_PAGING_MODE": "off",
    "MEMORYOS_AGENT_KERNEL": "off",
}


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path = Path(".")
    timeout_s: int = 0
    allow_extra_args: bool = False


@dataclass(frozen=True)
class GateCommand:
    command: str
    args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GateProfile:
    profile_id: str
    description: str
    blocking: bool
    env: dict[str, str]
    commands: list[GateCommand]
    diff_selectors: list[str]
    test_files: list[str]
    test_nodeids: list[str]
    test_markers: list[str]
    mixed_test_files: list[str]


@dataclass(frozen=True)
class ProfileDefaults:
    full_gate_profile: str
    full_gate_interval: int
    unknown_diff_policy: str
    unclassified_test_policy: str


@dataclass(frozen=True)
class GateConfig:
    schema_version: int
    defaults: ProfileDefaults
    command_catalog: dict[str, CommandSpec]
    profiles: dict[str, GateProfile]


@dataclass(frozen=True)
class CommandPlan:
    command_id: str
    argv: list[str]
    cwd: Path
    timeout_s: int
    env: dict[str, str]
    profile_id: str
    blocking: bool


@dataclass(frozen=True)
class GatePlan:
    feature_id: str
    worktree: Path
    profiles: list[str]
    blocking: bool
    commands: list[CommandPlan]
    resolution_reasons: dict[str, list[str]]
    changed_paths: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class GateCommandResult:
    command_id: str
    profile_id: str
    blocking: bool
    argv: list[str]
    cwd: Path
    timeout_s: int
    returncode: int
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class GateReport:
    feature_id: str
    passed: bool
    blocking_passed: bool
    nonblocking_failures: list[str]
    profile_ids: list[str]
    resolution_reasons: dict[str, list[str]]
    command_results: list[GateCommandResult]
    artifact_dir: Path
    warnings: list[str]

    @property
    def errors(self) -> list[str]:
        return [
            f"{result.profile_id}:{result.command_id} failed (exit {result.returncode})"
            for result in self.command_results
            if result.returncode != 0
        ]
```

Create `src/xmuse_core/gates/__init__.py`:

```python
from xmuse_core.gates.models import (
    CURRENT_PRODUCT_ENV,
    CommandPlan,
    CommandSpec,
    GateCommand,
    GateCommandResult,
    GateConfig,
    GatePlan,
    GateProfile,
    GateReport,
    ProfileDefaults,
)

__all__ = [
    "CURRENT_PRODUCT_ENV",
    "CommandPlan",
    "CommandSpec",
    "GateCommand",
    "GateCommandResult",
    "GateConfig",
    "GatePlan",
    "GateProfile",
    "GateReport",
    "ProfileDefaults",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS for 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/gates/__init__.py src/xmuse_core/gates/models.py tests/test_xmuse_gate_profiles.py
git commit -m "feat: add gate profile data models"
```

## Task 2: Gate Profile Loader

**Files:**
- Create: `src/xmuse_core/gates/loader.py`
- Modify: `src/xmuse_core/gates/__init__.py`
- Modify: `tests/test_xmuse_gate_profiles.py`

- [ ] **Step 1: Write failing loader tests**

Append these tests to `tests/test_xmuse_gate_profiles.py`:

```python
import json

import pytest

from xmuse_core.gates.loader import GateProfileConfigError, load_gate_config


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.gates.loader'`.

- [ ] **Step 3: Implement loader**

Create `src/xmuse_core/gates/loader.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xmuse_core.gates.models import (
    CommandSpec,
    GateCommand,
    GateConfig,
    GateProfile,
    ProfileDefaults,
)


class GateProfileConfigError(ValueError):
    pass


_ROOT_KEYS = {"schema_version", "defaults", "command_catalog", "profiles"}
_DEFAULT_KEYS = {
    "full_gate_profile",
    "full_gate_interval",
    "unknown_diff_policy",
    "unclassified_test_policy",
}
_COMMAND_KEYS = {"argv", "cwd", "timeout_s", "allow_extra_args"}
_PROFILE_KEYS = {
    "description",
    "blocking",
    "env",
    "commands",
    "diff_selectors",
    "test_files",
    "test_nodeids",
    "test_markers",
    "mixed_test_files",
}
_GATE_COMMAND_KEYS = {"command", "args"}


def load_gate_config(path: Path, *, repo_root: Path) -> GateConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise GateProfileConfigError("gate config root must be an object")
    _reject_unknown(raw, _ROOT_KEYS, "root")

    schema_version = _require_int(raw, "schema_version", "root")
    if schema_version != 1:
        raise GateProfileConfigError(f"unsupported schema_version: {schema_version}")

    defaults = _parse_defaults(_require_dict(raw, "defaults", "root"))
    command_catalog = _parse_command_catalog(
        _require_dict(raw, "command_catalog", "root"),
        repo_root=repo_root,
    )
    profiles = _parse_profiles(
        _require_dict(raw, "profiles", "root"),
        command_catalog=command_catalog,
    )

    if defaults.full_gate_profile not in profiles:
        raise GateProfileConfigError("defaults.full_gate_profile references unknown profile")
    if defaults.unknown_diff_policy not in profiles:
        raise GateProfileConfigError("defaults.unknown_diff_policy references unknown profile")
    if defaults.full_gate_interval <= 0:
        raise GateProfileConfigError("defaults.full_gate_interval must be positive")
    if "strict-product" not in profiles:
        raise GateProfileConfigError("strict-product profile is required")
    strict = profiles["strict-product"]
    if not strict.test_files and not strict.test_nodeids and not strict.test_markers:
        raise GateProfileConfigError("strict-product manifest must not be empty")
    for profile in profiles.values():
        has_manifest = profile.test_files or profile.test_nodeids or profile.test_markers
        if profile.blocking and not has_manifest:
            raise GateProfileConfigError(
                f"blocking profile manifest must not be empty: {profile.profile_id}"
            )

    return GateConfig(
        schema_version=schema_version,
        defaults=defaults,
        command_catalog=command_catalog,
        profiles=profiles,
    )


def _parse_defaults(raw: dict[str, Any]) -> ProfileDefaults:
    _reject_unknown(raw, _DEFAULT_KEYS, "defaults")
    return ProfileDefaults(
        full_gate_profile=_require_str(raw, "full_gate_profile", "defaults"),
        full_gate_interval=_require_int(raw, "full_gate_interval", "defaults"),
        unknown_diff_policy=_require_str(raw, "unknown_diff_policy", "defaults"),
        unclassified_test_policy=_require_str(
            raw,
            "unclassified_test_policy",
            "defaults",
        ),
    )


def _parse_command_catalog(
    raw: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, CommandSpec]:
    catalog: dict[str, CommandSpec] = {}
    for command_id, value in raw.items():
        if not isinstance(command_id, str) or not command_id:
            raise GateProfileConfigError("command id must be a non-empty string")
        command = _require_object(value, f"command_catalog.{command_id}")
        _reject_unknown(command, _COMMAND_KEYS, f"command_catalog.{command_id}")
        cwd = Path(_require_str(command, "cwd", f"command_catalog.{command_id}"))
        resolved = (repo_root / cwd).resolve()
        if repo_root.resolve() not in (resolved, *resolved.parents):
            raise GateProfileConfigError(f"{command_id} cwd must stay inside repo")
        catalog[command_id] = CommandSpec(
            argv=_require_str_list(command, "argv", f"command_catalog.{command_id}"),
            cwd=cwd,
            timeout_s=_require_int(command, "timeout_s", f"command_catalog.{command_id}"),
            allow_extra_args=_require_bool(
                command,
                "allow_extra_args",
                f"command_catalog.{command_id}",
            ),
        )
    return catalog


def _parse_profiles(
    raw: dict[str, Any],
    *,
    command_catalog: dict[str, CommandSpec],
) -> dict[str, GateProfile]:
    profiles: dict[str, GateProfile] = {}
    for profile_id, value in raw.items():
        if not isinstance(profile_id, str) or not profile_id:
            raise GateProfileConfigError("profile id must be a non-empty string")
        profile = _require_object(value, f"profiles.{profile_id}")
        _reject_unknown(profile, _PROFILE_KEYS, f"profiles.{profile_id}")
        commands = [
            _parse_gate_command(item, command_catalog, f"profiles.{profile_id}.commands")
            for item in _require_list(profile, "commands", f"profiles.{profile_id}")
        ]
        profiles[profile_id] = GateProfile(
            profile_id=profile_id,
            description=_require_str(profile, "description", f"profiles.{profile_id}"),
            blocking=_require_bool(profile, "blocking", f"profiles.{profile_id}"),
            env=_require_str_dict(profile, "env", f"profiles.{profile_id}"),
            commands=commands,
            diff_selectors=_require_str_list(
                profile,
                "diff_selectors",
                f"profiles.{profile_id}",
            ),
            test_files=_require_str_list(profile, "test_files", f"profiles.{profile_id}"),
            test_nodeids=_require_str_list(
                profile,
                "test_nodeids",
                f"profiles.{profile_id}",
            ),
            test_markers=_require_str_list(
                profile,
                "test_markers",
                f"profiles.{profile_id}",
            ),
            mixed_test_files=_require_str_list(
                profile,
                "mixed_test_files",
                f"profiles.{profile_id}",
            ),
        )
    return profiles


def _parse_gate_command(
    value: Any,
    command_catalog: dict[str, CommandSpec],
    context: str,
) -> GateCommand:
    raw = _require_object(value, context)
    _reject_unknown(raw, _GATE_COMMAND_KEYS, context)
    command = _require_str(raw, "command", context)
    if command not in command_catalog:
        raise GateProfileConfigError(f"{context}.command references unknown command")
    args = _require_str_list(raw, "args", context)
    if args and not command_catalog[command].allow_extra_args:
        raise GateProfileConfigError(f"{command} does not allow extra args")
    return GateCommand(command=command, args=args)


def _reject_unknown(raw: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise GateProfileConfigError(f"{context} has unknown field: {unknown[0]}")


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateProfileConfigError(f"{context} must be an object")
    return value


def _require_dict(raw: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    return _require_object(raw.get(key), f"{context}.{key}")


def _require_list(raw: dict[str, Any], key: str, context: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise GateProfileConfigError(f"{context}.{key} must be a list")
    return value


def _require_str(raw: dict[str, Any], key: str, context: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise GateProfileConfigError(f"{context}.{key} must be a non-empty string")
    return value


def _require_int(raw: dict[str, Any], key: str, context: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise GateProfileConfigError(f"{context}.{key} must be an int")
    return value


def _require_bool(raw: dict[str, Any], key: str, context: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise GateProfileConfigError(f"{context}.{key} must be a bool")
    return value


def _require_str_list(raw: dict[str, Any], key: str, context: str) -> list[str]:
    values = _require_list(raw, key, context)
    if not all(isinstance(value, str) and value for value in values):
        raise GateProfileConfigError(f"{context}.{key} must be a list of strings")
    return list(values)


def _require_str_dict(raw: dict[str, Any], key: str, context: str) -> dict[str, str]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise GateProfileConfigError(f"{context}.{key} must be an object")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise GateProfileConfigError(f"{context}.{key} must be a string map")
    return dict(value)
```

Update `src/xmuse_core/gates/__init__.py`:

```python
from xmuse_core.gates.loader import GateProfileConfigError, load_gate_config

__all__ = [
    "CURRENT_PRODUCT_ENV",
    "CommandPlan",
    "CommandSpec",
    "GateCommand",
    "GateCommandResult",
    "GateConfig",
    "GatePlan",
    "GateProfile",
    "GateProfileConfigError",
    "GateReport",
    "ProfileDefaults",
    "load_gate_config",
]
```

Keep the existing model imports above this addition.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS for the loader and model tests.

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/gates/__init__.py src/xmuse_core/gates/loader.py tests/test_xmuse_gate_profiles.py
git commit -m "feat: load gate profile configuration"
```

## Task 3: Profile Resolver

**Files:**
- Create: `src/xmuse_core/gates/resolver.py`
- Modify: `src/xmuse_core/gates/__init__.py`
- Modify: `tests/test_xmuse_gate_profiles.py`

- [ ] **Step 1: Write failing resolver tests**

Append these tests to `tests/test_xmuse_gate_profiles.py`:

```python
from xmuse_core.gates.resolver import GateProfileResolver, ProfileMismatchError


def _loaded_config(tmp_path):
    config_path = tmp_path / "gate_profiles.json"
    data = _minimal_gate_config()
    data["profiles"]["xmuse-core"] = {
        "description": "xmuse core",
        "blocking": True,
        "env": {},
        "commands": [{"command": "pytest", "args": ["-q", "tests/test_xmuse_master_loop.py"]}],
        "diff_selectors": ["xmuse/**", "src/xmuse_core/**"],
        "test_files": ["tests/test_xmuse_master_loop.py"],
        "test_nodeids": [],
        "test_markers": [],
        "mixed_test_files": [],
    }
    _write_gate_config(config_path, data)
    return load_gate_config(config_path, repo_root=tmp_path)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.gates.resolver'`.

- [ ] **Step 3: Implement resolver**

Create `src/xmuse_core/gates/resolver.py`:

```python
from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from xmuse_core.gates.models import CommandPlan, GateConfig, GatePlan, GateProfile


class ProfileMismatchError(ValueError):
    pass


class GateProfileResolver:
    def __init__(self, config: GateConfig) -> None:
        self.config = config

    def resolve(
        self,
        *,
        feature_id: str,
        worktree: Path,
        explicit_profiles: list[str],
        changed_paths: list[str],
        warnings: list[str] | None = None,
    ) -> GatePlan:
        warnings = list(warnings or [])
        if explicit_profiles:
            profiles = self._dedupe_profiles(explicit_profiles)
            reasons = {profile_id: ["explicit_lane_profile"] for profile_id in profiles}
            missing = self._missing_blocking_profiles(profiles, changed_paths)
            if missing:
                raise ProfileMismatchError(
                    "missing blocking profile for changed paths: "
                    + ", ".join(sorted(missing))
                )
        else:
            profiles = self._profiles_for_paths(changed_paths)
            reasons = {profile_id: ["diff_selector"] for profile_id in profiles}
            if not profiles:
                profile_id = self.config.defaults.unknown_diff_policy
                profiles = [profile_id]
                reasons = {profile_id: ["unknown_diff_policy"]}

        profile_objs = [self.config.profiles[profile_id] for profile_id in profiles]
        commands = self._build_commands(profile_objs)
        return GatePlan(
            feature_id=feature_id,
            worktree=worktree,
            profiles=profiles,
            blocking=any(profile.blocking for profile in profile_objs),
            commands=commands,
            resolution_reasons=reasons,
            changed_paths=list(changed_paths),
            warnings=warnings,
        )

    def _profiles_for_paths(self, changed_paths: list[str]) -> list[str]:
        matched: list[str] = []
        for profile_id, profile in self.config.profiles.items():
            if any(self._profile_matches_path(profile, path) for path in changed_paths):
                matched.append(profile_id)
        return self._dedupe_profiles(matched)

    def _missing_blocking_profiles(
        self,
        explicit_profiles: list[str],
        changed_paths: list[str],
    ) -> set[str]:
        explicit = set(explicit_profiles)
        missing: set[str] = set()
        for profile_id, profile in self.config.profiles.items():
            if not profile.blocking or profile_id in explicit:
                continue
            if any(self._profile_matches_path(profile, path) for path in changed_paths):
                missing.add(profile_id)
        return missing

    def _profile_matches_path(self, profile: GateProfile, path: str) -> bool:
        return any(fnmatch(path, selector) for selector in profile.diff_selectors)

    def _build_commands(
        self,
        profiles: list[GateProfile],
    ) -> list[CommandPlan]:
        commands: list[CommandPlan] = []
        seen_commands: set[tuple[str, tuple[str, ...], str, tuple[tuple[str, str], ...]]] = set()
        for profile in profiles:
            for gate_command in profile.commands:
                spec = self.config.command_catalog[gate_command.command]
                argv = [*spec.argv, *gate_command.args]
                key = (
                    gate_command.command,
                    tuple(argv),
                    spec.cwd.as_posix(),
                    tuple(sorted(profile.env.items())),
                )
                if key in seen_commands:
                    continue
                commands.append(
                    CommandPlan(
                        command_id=gate_command.command,
                        argv=argv,
                        cwd=spec.cwd,
                        timeout_s=spec.timeout_s,
                        env=dict(profile.env),
                        profile_id=profile.profile_id,
                        blocking=profile.blocking,
                    )
                )
                seen_commands.add(key)
        return commands

    def _dedupe_profiles(self, profiles: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for profile_id in profiles:
            if profile_id not in self.config.profiles:
                raise ProfileMismatchError(f"unknown gate profile: {profile_id}")
            if profile_id in seen:
                continue
            result.append(profile_id)
            seen.add(profile_id)
        return result
```

Update `src/xmuse_core/gates/__init__.py`:

```python
from xmuse_core.gates.resolver import GateProfileResolver, ProfileMismatchError

__all__ = [
    "CURRENT_PRODUCT_ENV",
    "CommandSpec",
    "GateCommand",
    "GateCommandResult",
    "GateConfig",
    "GatePlan",
    "GateProfile",
    "GateProfileConfigError",
    "GateProfileResolver",
    "GateReport",
    "ProfileDefaults",
    "ProfileMismatchError",
    "load_gate_config",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS for the model, loader, resolver, and runner tests.

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/gates/__init__.py src/xmuse_core/gates/resolver.py tests/test_xmuse_gate_profiles.py
git commit -m "feat: resolve gate profiles from lanes and diffs"
```

## Task 4: Gate Runner and Reports

**Files:**
- Create: `src/xmuse_core/gates/runner.py`
- Modify: `src/xmuse_core/gates/__init__.py`
- Modify: `tests/test_xmuse_gate_profiles.py`

- [ ] **Step 1: Write failing runner tests**

Append these tests to `tests/test_xmuse_gate_profiles.py`:

```python
import asyncio

from xmuse_core.gates.runner import GateRunner


class FakeProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self._stdout = stdout.encode()
        self._stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_gate_runner_writes_report_artifacts_and_applies_env(tmp_path, monkeypatch):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.gates.runner'`.

- [ ] **Step 3: Implement runner**

Create `src/xmuse_core/gates/runner.py`:

```python
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from xmuse_core.gates.models import CommandPlan, GateCommandResult, GatePlan, GateReport


class GateRunner:
    def __init__(self, *, repo_root: Path, logs_root: Path | None = None) -> None:
        self.repo_root = repo_root
        self.logs_root = logs_root or repo_root / "xmuse" / "logs" / "gates"

    async def run(self, plan: GatePlan) -> GateReport:
        artifact_dir = self.logs_root / plan.feature_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        results: list[GateCommandResult] = []
        for command in plan.commands:
            name = f"{command.profile_id}__{command.command_id}"
            result = await self._run_command(plan.worktree, command)
            stdout_path = artifact_dir / f"{name}.stdout"
            stderr_path = artifact_dir / f"{name}.stderr"
            stdout_path.write_text(result[1], encoding="utf-8")
            stderr_path.write_text(result[2], encoding="utf-8")
            results.append(
                GateCommandResult(
                    command_id=command.command_id,
                    profile_id=command.profile_id,
                    blocking=command.blocking,
                    argv=command.argv,
                    cwd=command.cwd,
                    timeout_s=command.timeout_s,
                    returncode=result[0],
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )
            )

        blocking_passed = all(
            result.returncode == 0 for result in results if result.blocking
        )
        nonblocking_failures = sorted(
            {
                result.profile_id
                for result in results
                if not result.blocking and result.returncode != 0
            }
        )
        report = GateReport(
            feature_id=plan.feature_id,
            passed=blocking_passed if plan.blocking else True,
            blocking_passed=blocking_passed,
            nonblocking_failures=nonblocking_failures,
            profile_ids=plan.profiles,
            resolution_reasons=plan.resolution_reasons,
            command_results=results,
            artifact_dir=artifact_dir,
            warnings=[
                *plan.warnings,
                *[
                    f"nonblocking profile failed: {profile_id}"
                    for profile_id in nonblocking_failures
                ],
            ],
        )
        (artifact_dir / "report.json").write_text(
            json.dumps(_report_to_json(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return report

    async def _run_command(
        self,
        worktree: Path,
        command: CommandPlan,
    ) -> tuple[int, str, str]:
        env = dict(os.environ)
        env.update(command.env)
        cwd = (worktree / command.cwd).resolve()
        process = await asyncio.create_subprocess_exec(
            *command.argv,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        returncode = process.returncode
        if returncode is None:
            returncode = await process.wait()
        return (
            returncode,
            stdout_bytes.decode(errors="replace"),
            stderr_bytes.decode(errors="replace"),
        )


def _report_to_json(report: GateReport) -> dict:
    return {
        "feature_id": report.feature_id,
        "passed": report.passed,
        "blocking_passed": report.blocking_passed,
        "nonblocking_failures": report.nonblocking_failures,
        "profile_ids": report.profile_ids,
        "resolution_reasons": report.resolution_reasons,
        "warnings": report.warnings,
        "artifact_dir": str(report.artifact_dir),
        "command_results": [
            {
                "command_id": result.command_id,
                "profile_id": result.profile_id,
                "blocking": result.blocking,
                "argv": result.argv,
                "cwd": result.cwd.as_posix(),
                "timeout_s": result.timeout_s,
                "returncode": result.returncode,
                "stdout_path": str(result.stdout_path),
                "stderr_path": str(result.stderr_path),
            }
            for result in report.command_results
        ],
    }
```

Update `src/xmuse_core/gates/__init__.py`:

```python
from xmuse_core.gates.runner import GateRunner

__all__ = [
    "CURRENT_PRODUCT_ENV",
    "CommandSpec",
    "GateCommand",
    "GateCommandResult",
    "GateConfig",
    "GatePlan",
    "GateProfile",
    "GateProfileConfigError",
    "GateProfileResolver",
    "GateReport",
    "GateRunner",
    "ProfileDefaults",
    "ProfileMismatchError",
    "load_gate_config",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS for the gate profile tests added so far.

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/gates/__init__.py src/xmuse_core/gates/runner.py tests/test_xmuse_gate_profiles.py
git commit -m "feat: run gate profile commands"
```

## Task 5: Coverage Guard and Initial Config

**Files:**
- Create: `src/xmuse_core/gates/coverage.py`
- Create: `xmuse/gate_profiles.json`
- Modify: `src/xmuse_core/gates/__init__.py`
- Modify: `tests/test_xmuse_gate_profiles.py`

- [ ] **Step 1: Write failing coverage/config tests**

Append these tests to `tests/test_xmuse_gate_profiles.py`:

```python
from xmuse_core.gates.coverage import GateCoverageError, validate_test_ownership


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
    config["profiles"]["strict-product"]["test_files"] = []
    config["profiles"]["strict-product"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config["profiles"]["historical"]["mixed_test_files"] = ["tests/test_mixed.py"]
    config_path = tmp_path / "gate_profiles.json"
    _write_gate_config(config_path, config)
    loaded = load_gate_config(config_path, repo_root=tmp_path)

    with pytest.raises(GateCoverageError, match="unowned mixed test nodeid"):
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
    config["profiles"]["strict-product"]["test_files"] = []
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
    config["profiles"]["strict-product"]["test_files"] = []
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.gates.coverage'` or missing `xmuse/gate_profiles.json`.

- [ ] **Step 3: Implement coverage guard**

Create `src/xmuse_core/gates/coverage.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path

from xmuse_core.gates.models import GateConfig


class GateCoverageError(ValueError):
    pass


def validate_test_ownership(config: GateConfig, *, tests_root: Path) -> None:
    owned_full_files: set[str] = set()
    mixed_files: set[str] = set()
    owned_nodeids: set[str] = set()
    owned_markers: set[str] = set()
    for profile in config.profiles.values():
        owned_full_files.update(profile.test_files)
        mixed_files.update(profile.mixed_test_files)
        owned_nodeids.update(profile.test_nodeids)
        owned_markers.update(profile.test_markers)

    for test_file in sorted(tests_root.rglob("test*.py")):
        rel = test_file.as_posix()
        if not rel.startswith("tests/"):
            rel = f"tests/{test_file.relative_to(tests_root).as_posix()}"
        if rel in owned_full_files:
            continue
        if rel in mixed_files:
            _validate_mixed_file(
                test_file,
                rel=rel,
                owned_nodeids=owned_nodeids,
                owned_markers=owned_markers,
            )
            continue
        if rel not in {nodeid.split("::", 1)[0] for nodeid in owned_nodeids}:
            raise GateCoverageError(f"unclassified test file: {rel}")


def _validate_mixed_file(
    test_file: Path,
    *,
    rel: str,
    owned_nodeids: set[str],
    owned_markers: set[str],
) -> None:
    for nodeid, markers in _collect_test_nodes(test_file, rel=rel):
        if nodeid in owned_nodeids or markers.intersection(owned_markers):
            continue
        raise GateCoverageError(f"unowned mixed test nodeid: {nodeid}")


def _collect_test_nodes(test_file: Path, *, rel: str) -> list[tuple[str, set[str]]]:
    tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=rel)
    nodes: list[tuple[str, set[str]]] = []
    for item in tree.body:
        if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
            nodes.append((f"{rel}::{item.name}", _decorator_markers(item.decorator_list)))
        if isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
            class_markers = _decorator_markers(item.decorator_list)
            for method in item.body:
                if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"):
                    nodes.append(
                        (
                            f"{rel}::{item.name}::{method.name}",
                            class_markers | _decorator_markers(method.decorator_list),
                        )
                    )
    return nodes


def _decorator_markers(decorators: list[ast.expr]) -> set[str]:
    markers: set[str] = set()
    for decorator in decorators:
        marker = _marker_name(decorator)
        if marker:
            markers.add(marker)
    return markers


def _marker_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Call):
        return _marker_name(expr.func)
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Attribute):
        if isinstance(expr.value.value, ast.Name) and expr.value.value.id == "pytest":
            if expr.value.attr == "mark":
                return expr.attr
    return None
```

Update `src/xmuse_core/gates/__init__.py`:

```python
from xmuse_core.gates.coverage import GateCoverageError, validate_test_ownership

__all__ = [
    "CURRENT_PRODUCT_ENV",
    "CommandSpec",
    "GateCommand",
    "GateCommandResult",
    "GateConfig",
    "GateCoverageError",
    "GatePlan",
    "GateProfile",
    "GateProfileConfigError",
    "GateProfileResolver",
    "GateReport",
    "GateRunner",
    "ProfileDefaults",
    "ProfileMismatchError",
    "load_gate_config",
    "validate_test_ownership",
]
```

- [ ] **Step 4: Create initial config**

Create `xmuse/gate_profiles.json`. Use real manifests. This initial config must load and should be intentionally minimal for `strict-product`. Do not list a file in `mixed_test_files` unless every collected nodeid in that file is owned by `test_nodeids` or `test_markers`; the initial config keeps mixed files out of blocking profiles until they are split explicitly.

```json
{
  "schema_version": 1,
  "defaults": {
    "full_gate_profile": "strict-product",
    "full_gate_interval": 20,
    "unknown_diff_policy": "strict-product",
    "unclassified_test_policy": "fail"
  },
  "command_catalog": {
    "pytest": {
      "argv": ["uv", "run", "pytest"],
      "cwd": ".",
      "timeout_s": 0,
      "allow_extra_args": true
    },
    "ruff-src": {
      "argv": ["uv", "run", "ruff", "check", "src/"],
      "cwd": ".",
      "timeout_s": 0,
      "allow_extra_args": false
    },
    "ruff-xmuse": {
      "argv": ["uv", "run", "ruff", "check", "xmuse/"],
      "cwd": ".",
      "timeout_s": 0,
      "allow_extra_args": false
    }
  },
  "profiles": {
    "strict-product": {
      "description": "Current v3/v2/off MemoryOS and xmuse core product surface.",
      "blocking": true,
      "env": {
        "MEMORYOS_MEMORY_ARCH": "v3",
        "MEMORYOS_RECALL_PIPELINE": "v2",
        "MEMORYOS_PAGING_MODE": "off",
        "MEMORYOS_AGENT_KERNEL": "off"
      },
      "commands": [
        {
          "command": "pytest",
          "args": [
            "-q",
            "tests/test_v3_path.py",
            "tests/test_core_memory_service.py",
            "tests/test_core_memory_store.py",
            "tests/test_episode_store.py",
            "tests/test_episode_retrieval.py",
            "tests/test_recall_pipeline.py",
            "tests/test_recall_cache.py",
            "tests/test_query_expansion.py",
            "tests/test_memoryos_middleware.py",
            "tests/test_memoryos_agent_endpoints.py",
            "tests/test_xmuse_quality_gate.py",
            "tests/test_xmuse_master_loop.py",
            "tests/test_xmuse_master_loop_integration.py",
            "tests/test_xmuse_auto_discovery.py",
            "tests/test_xmuse_rework_loop.py",
            "tests/test_xmuse_core_agents_consumer.py",
            "tests/test_xmuse_core_agents_launchers.py",
            "tests/test_xmuse_core_agents_manager.py",
            "tests/test_xmuse_core_agents_protocol.py",
            "tests/test_xmuse_core_agents_registry.py",
            "tests/test_xmuse_core_agents_session.py",
            "tests/test_xmuse_core_schema.py",
            "tests/test_xmuse_core_state.py",
            "tests/test_xmuse_core_status.py",
            "tests/test_xmuse_core_routing.py",
            "tests/test_xmuse_core_callback_server.py",
            "tests/test_xmuse_mcp_server.py",
            "tests/test_xmuse_overnight_runner.py"
          ]
        }
      ],
      "diff_selectors": [
        "src/memoryos_lite/config.py",
        "src/memoryos_lite/store.py",
        "src/memoryos_lite/schemas.py",
        "src/memoryos_lite/engine.py",
        "src/memoryos_lite/retrieval/**",
        "src/xmuse_core/**",
        "xmuse/**"
      ],
      "test_files": [
        "tests/test_v3_path.py",
        "tests/test_core_memory_service.py",
        "tests/test_core_memory_store.py",
        "tests/test_episode_store.py",
        "tests/test_episode_retrieval.py",
        "tests/test_recall_pipeline.py",
        "tests/test_recall_cache.py",
        "tests/test_query_expansion.py",
        "tests/test_memoryos_middleware.py",
        "tests/test_memoryos_agent_endpoints.py",
        "tests/test_xmuse_quality_gate.py",
        "tests/test_xmuse_master_loop.py",
        "tests/test_xmuse_master_loop_integration.py",
        "tests/test_xmuse_auto_discovery.py",
        "tests/test_xmuse_rework_loop.py",
        "tests/test_xmuse_core_agents_consumer.py",
        "tests/test_xmuse_core_agents_launchers.py",
        "tests/test_xmuse_core_agents_manager.py",
        "tests/test_xmuse_core_agents_protocol.py",
        "tests/test_xmuse_core_agents_registry.py",
        "tests/test_xmuse_core_agents_session.py",
        "tests/test_xmuse_core_schema.py",
        "tests/test_xmuse_core_state.py",
        "tests/test_xmuse_core_status.py",
        "tests/test_xmuse_core_routing.py",
        "tests/test_xmuse_core_callback_server.py",
        "tests/test_xmuse_mcp_server.py",
        "tests/test_xmuse_overnight_runner.py"
      ],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "memoryos-core": {
      "description": "Current MemoryOS v3 core/store/config surface.",
      "blocking": true,
      "env": {
        "MEMORYOS_MEMORY_ARCH": "v3",
        "MEMORYOS_RECALL_PIPELINE": "v2",
        "MEMORYOS_PAGING_MODE": "off",
        "MEMORYOS_AGENT_KERNEL": "off"
      },
      "commands": [
        {
          "command": "pytest",
          "args": ["-q", "tests/test_v3_path.py", "tests/test_core_memory_service.py", "tests/test_core_memory_store.py"]
        }
      ],
      "diff_selectors": ["src/memoryos_lite/config.py", "src/memoryos_lite/store.py", "src/memoryos_lite/schemas.py", "src/memoryos_lite/engine.py"],
      "test_files": ["tests/test_v3_path.py", "tests/test_core_memory_service.py", "tests/test_core_memory_store.py"],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "memoryos-recall": {
      "description": "Current v2 recall and episode surface.",
      "blocking": true,
      "env": {
        "MEMORYOS_MEMORY_ARCH": "v3",
        "MEMORYOS_RECALL_PIPELINE": "v2",
        "MEMORYOS_PAGING_MODE": "off",
        "MEMORYOS_AGENT_KERNEL": "off"
      },
      "commands": [
        {
          "command": "pytest",
          "args": ["-q", "tests/test_episode_store.py", "tests/test_episode_retrieval.py", "tests/test_recall_pipeline.py", "tests/test_recall_cache.py", "tests/test_query_expansion.py"]
        }
      ],
      "diff_selectors": ["src/memoryos_lite/retrieval/**"],
      "test_files": ["tests/test_episode_store.py", "tests/test_episode_retrieval.py", "tests/test_recall_pipeline.py", "tests/test_recall_cache.py", "tests/test_query_expansion.py"],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "memoryos-api": {
      "description": "Current MemoryOS API and middleware surface.",
      "blocking": true,
      "env": {
        "MEMORYOS_MEMORY_ARCH": "v3",
        "MEMORYOS_RECALL_PIPELINE": "v2",
        "MEMORYOS_PAGING_MODE": "off",
        "MEMORYOS_AGENT_KERNEL": "off"
      },
      "commands": [
        {
          "command": "pytest",
          "args": ["-q", "tests/test_memoryos_middleware.py", "tests/test_memoryos_agent_endpoints.py"]
        }
      ],
      "diff_selectors": ["src/memoryos_lite/api/**", "src/memoryos_lite/cli.py"],
      "test_files": ["tests/test_memoryos_middleware.py", "tests/test_memoryos_agent_endpoints.py"],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "xmuse-core": {
      "description": "xmuse orchestration and agent runner surface.",
      "blocking": true,
      "env": {},
      "commands": [
        {
          "command": "pytest",
          "args": [
            "-q",
            "tests/test_xmuse_quality_gate.py",
            "tests/test_xmuse_master_loop.py",
            "tests/test_xmuse_master_loop_integration.py",
            "tests/test_xmuse_auto_discovery.py",
            "tests/test_xmuse_rework_loop.py",
            "tests/test_xmuse_core_agents_consumer.py",
            "tests/test_xmuse_core_agents_launchers.py",
            "tests/test_xmuse_core_agents_manager.py",
            "tests/test_xmuse_core_agents_protocol.py",
            "tests/test_xmuse_core_agents_registry.py",
            "tests/test_xmuse_core_agents_session.py",
            "tests/test_xmuse_core_schema.py",
            "tests/test_xmuse_core_state.py",
            "tests/test_xmuse_core_status.py",
            "tests/test_xmuse_core_routing.py",
            "tests/test_xmuse_core_callback_server.py",
            "tests/test_xmuse_mcp_server.py",
            "tests/test_xmuse_overnight_runner.py"
          ]
        }
      ],
      "diff_selectors": ["xmuse/**", "src/xmuse_core/**"],
      "test_files": [
        "tests/test_xmuse_quality_gate.py",
        "tests/test_xmuse_master_loop.py",
        "tests/test_xmuse_master_loop_integration.py",
        "tests/test_xmuse_auto_discovery.py",
        "tests/test_xmuse_rework_loop.py",
        "tests/test_xmuse_core_agents_consumer.py",
        "tests/test_xmuse_core_agents_launchers.py",
        "tests/test_xmuse_core_agents_manager.py",
        "tests/test_xmuse_core_agents_protocol.py",
        "tests/test_xmuse_core_agents_registry.py",
        "tests/test_xmuse_core_agents_session.py",
        "tests/test_xmuse_core_schema.py",
        "tests/test_xmuse_core_state.py",
        "tests/test_xmuse_core_status.py",
        "tests/test_xmuse_core_routing.py",
        "tests/test_xmuse_core_callback_server.py",
        "tests/test_xmuse_mcp_server.py",
        "tests/test_xmuse_overnight_runner.py"
      ],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "xmuse-ui": {
      "description": "xmuse dashboard and frontend surface.",
      "blocking": true,
      "env": {},
      "commands": [
        {
          "command": "pytest",
          "args": ["-q", "tests/test_xmuse_dashboard_api.py"]
        }
      ],
      "diff_selectors": ["xmuse/dashboard/**", "xmuse/frontend/**"],
      "test_files": ["tests/test_xmuse_dashboard_api.py"],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "memoryos-kernel": {
      "description": "Opt-in kernel profile, not part of strict-product.",
      "blocking": true,
      "env": {
        "MEMORYOS_AGENT_KERNEL": "v1"
      },
      "commands": [
        {
          "command": "pytest",
          "args": ["-q", "tests/test_agent_kernel.py"]
        }
      ],
      "diff_selectors": ["src/memoryos_lite/agent_kernel.py"],
      "test_files": ["tests/test_agent_kernel.py"],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    },
    "historical": {
      "description": "Legacy, historical, experimental, and gray-area diagnostics.",
      "blocking": false,
      "env": {},
      "commands": [],
      "diff_selectors": ["src/memoryos_lite/legacy_paging.py", "src/memoryos_lite/agent_graph.py"],
      "test_files": [
        "tests/test_agent.py",
        "tests/test_agent_demo.py",
        "tests/test_cli_agent_demo.py",
        "tests/test_budget.py",
        "tests/test_conflict.py",
        "tests/test_conflict_adversarial.py",
        "tests/test_conflict_slots.py",
        "tests/test_evals_advanced.py",
        "tests/test_evidence_integration.py",
        "tests/test_evidence_representer.py",
        "tests/test_hybrid_multiquery.py",
        "tests/test_item_retrieval.py",
        "tests/test_item_tools.py",
        "tests/test_observability.py",
        "tests/test_pagination_hotpath.py",
        "tests/test_patch_edge_cases.py",
        "tests/test_performance.py",
        "tests/test_rag_pipeline.py",
        "tests/test_retrieval.py"
      ],
      "test_nodeids": [],
      "test_markers": [],
      "mixed_test_files": []
    }
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS for all gate profile tests.

- [ ] **Step 6: Commit**

```bash
git add src/xmuse_core/gates/__init__.py src/xmuse_core/gates/coverage.py xmuse/gate_profiles.json tests/test_xmuse_gate_profiles.py
git commit -m "feat: add gate profile configuration"
```

## Task 6: Preserve Gate Metadata in Tasks

**Files:**
- Modify: `src/xmuse_core/agents/consumer.py`
- Modify: `xmuse/master_loop.py`
- Modify: `tests/test_xmuse_master_loop.py`

- [ ] **Step 1: Write failing metadata propagation test**

Add this test to `tests/test_xmuse_master_loop.py` near the `load_lanes` tests:

```python
def test_load_lanes_preserves_gate_metadata(tmp_path):
    from master_loop import load_lanes

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "profiled",
                "task_type": "execute",
                "prompt": "do work",
                "worktree": str(tmp_path),
                "gate_profile": "memoryos-core",
                "gate_profiles": ["memoryos-core", "memoryos-recall"],
                "base_head_sha": "abc123",
                "custom_gate_note": "preserve me",
            }
        ],
    )

    task = load_lanes(lanes_path)[0]

    assert task.gate_profile == "memoryos-core"
    assert task.gate_profiles == ["memoryos-core", "memoryos-recall"]
    assert task.base_head_sha == "abc123"
    assert task.lane_metadata["custom_gate_note"] == "preserve me"


def test_load_lanes_records_base_head_sha_for_new_worktree(tmp_path, monkeypatch):
    import master_loop
    from master_loop import load_lanes

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "new-lane",
                "task_type": "execute",
                "prompt": "do work",
            }
        ],
    )
    monkeypatch.setattr(master_loop, "ensure_worktree", lambda feature_id, branch=None: tmp_path)
    monkeypatch.setattr(master_loop, "_root_head_sha", lambda: "base-sha")

    task = load_lanes(lanes_path)[0]
    lanes = _read_lanes(lanes_path)

    assert task.base_head_sha == "base-sha"
    assert lanes[0]["base_head_sha"] == "base-sha"
    assert lanes[0]["worktree"] == str(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_xmuse_master_loop.py::test_load_lanes_preserves_gate_metadata -q
```

Expected: FAIL with `AttributeError: 'TaskDescriptor' object has no attribute 'gate_profile'`.

- [ ] **Step 3: Extend TaskDescriptor**

Modify `src/xmuse_core/agents/consumer.py`:

```python
@dataclass
class TaskDescriptor:
    feature_id: str
    task_type: str
    prompt: str
    worktree: str = "."
    required_capabilities: list[str] = field(default_factory=lambda: ["code"])
    developed_by_runtime: AgentRuntime | None = None
    priority: int = 0
    gate_profile: str | None = None
    gate_profiles: list[str] = field(default_factory=list)
    lane_metadata: dict[str, object] = field(default_factory=dict)
    base_head_sha: str | None = None
```

- [ ] **Step 4: Preserve metadata in load_lanes and rework tasks**

In `xmuse/master_loop.py`, add a helper near `_coerce_priority`:

```python
def _root_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


_TASK_DESCRIPTOR_FIELDS = {
    "feature_id",
    "task_type",
    "prompt",
    "worktree",
    "capabilities",
    "developed_by_runtime",
    "priority",
    "gate_profile",
    "gate_profiles",
    "base_head_sha",
}


def _lane_metadata(lane: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in lane.items() if key not in _TASK_DESCRIPTOR_FIELDS}
```

In `load_lanes()`, initialize `mutated = False` before the lane loop, then persist `worktree` and `base_head_sha` when a normal lane gets its worktree for the first time:

```python
    mutated = False

    for index, lane in enumerate(all_lanes):
        if task_type == FULL_QUALITY_GATE_TASK_TYPE:
            worktree = worktree or "."
        elif not worktree or worktree == ".":
            worktree = str(ensure_worktree(lane["feature_id"], branch=lane.get("branch")))
            lane["worktree"] = worktree
            lane["base_head_sha"] = lane.get("base_head_sha") or _root_head_sha()
            mutated = True

        base_head_sha = lane.get("base_head_sha")
        if task_type != FULL_QUALITY_GATE_TASK_TYPE and not isinstance(base_head_sha, str):
            base_head_sha = _root_head_sha()
            lane["base_head_sha"] = base_head_sha
            mutated = True
```

After the `for` loop in `load_lanes()`, write the mutated lane file only if a lane now has a persisted worktree or base SHA:

```python
    if mutated:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
```

Then update `TaskDescriptor(...)`:

```python
TaskDescriptor(
    feature_id=lane["feature_id"],
    task_type=task_type,
    prompt=lane["prompt"],
    worktree=worktree,
    required_capabilities=lane.get("capabilities", ["code"]),
    developed_by_runtime=lane.get("developed_by_runtime"),
    priority=_coerce_priority(lane.get("priority")),
    gate_profile=lane.get("gate_profile") if isinstance(lane.get("gate_profile"), str) else None,
    gate_profiles=[
        item for item in lane.get("gate_profiles", []) if isinstance(item, str)
    ],
    lane_metadata=_lane_metadata(lane),
    base_head_sha=base_head_sha if isinstance(base_head_sha, str) else None,
)
```

When creating `rework_task`, carry gate metadata:

```python
rework_task = TaskDescriptor(
    feature_id=task.feature_id,
    task_type="rework",
    prompt=enriched_prompt,
    worktree=str(worktree),
    required_capabilities=task.required_capabilities,
    developed_by_runtime=task.developed_by_runtime,
    priority=task.priority,
    gate_profile=task.gate_profile,
    gate_profiles=task.gate_profiles,
    lane_metadata=task.lane_metadata,
    base_head_sha=task.base_head_sha,
)
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_xmuse_master_loop.py::test_load_lanes_preserves_gate_metadata -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/xmuse_core/agents/consumer.py xmuse/master_loop.py tests/test_xmuse_master_loop.py
git commit -m "feat: preserve gate metadata on lane tasks"
```

## Task 7: Integrate Gate Profiles With QualityGate

**Files:**
- Modify: `src/xmuse_core/agents/quality_gate.py`
- Modify: `tests/test_xmuse_quality_gate.py`
- Modify: `tests/test_xmuse_gate_profiles.py`

- [ ] **Step 1: Write failing QualityGate integration test**

Add this test to `tests/test_xmuse_quality_gate.py`:

```python
import json


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
async def test_quality_gate_uses_profile_runner_when_configured(tmp_path, monkeypatch):
    from xmuse_core.agents.quality_gate import QualityGate
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
    from xmuse_core.agents.quality_gate import QualityGate

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
    from xmuse_core.agents.quality_gate import QualityGate

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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_xmuse_quality_gate.py::test_quality_gate_uses_profile_runner_when_configured -q
```

Expected: FAIL because `QualityGate.__init__` does not accept `profile_config_path` and `check()` does not accept gate metadata.

- [ ] **Step 3: Extend QualityGate**

Modify `src/xmuse_core/agents/quality_gate.py`:

```python
@dataclass
class GateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    commands: dict[str, list[str]] = field(default_factory=dict)
    gate_report: dict[str, object] | None = None
    gate_warnings: list[str] = field(default_factory=list)


class QualityGate:
    _INSERTION_LIMIT = 1000
    _INSERTIONS_RE = re.compile(r"(\d+)\s+insertions?\(\+\)")
    _DEFAULT_BASE_REF = "HEAD~1"
    _SMOKE_TESTS = ("tests/test_config.py",)

    def __init__(
        self,
        *,
        profile_config_path: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.profile_config_path = profile_config_path
        self.repo_root = repo_root or Path.cwd()
        self._profile_config = None
        self._runner = None

    async def check(
        self,
        worktree: Path,
        *,
        feature_id: str = "lane-local",
        gate_profile: str | None = None,
        gate_profiles: list[str] | None = None,
        changed_paths: list[str] | None = None,
        base_head_sha: str | None = None,
    ) -> GateResult:
        if self.profile_config_path is not None:
            return await self._check_with_profiles(
                worktree,
                feature_id=feature_id,
                gate_profile=gate_profile,
                gate_profiles=gate_profiles or [],
                changed_paths=changed_paths,
                base_head_sha=base_head_sha,
            )
        return await self._check_legacy(worktree)
```

Move the current `check()` body into `_check_legacy()`.

Add `_check_with_profiles()`:

```python
    async def _check_with_profiles(
        self,
        worktree: Path,
        *,
        feature_id: str,
        gate_profile: str | None,
        gate_profiles: list[str],
        changed_paths: list[str] | None,
        base_head_sha: str | None,
    ) -> GateResult:
        from xmuse_core.gates.loader import load_gate_config
        from xmuse_core.gates.resolver import GateProfileResolver, ProfileMismatchError
        from xmuse_core.gates.runner import GateRunner

        config = self._profile_config
        if config is None:
            config = load_gate_config(self.profile_config_path, repo_root=self.repo_root)
            self._profile_config = config
        runner = self._runner
        if runner is None:
            runner = GateRunner(repo_root=self.repo_root)
            self._runner = runner

        explicit = list(gate_profiles)
        if not explicit and gate_profile:
            explicit = [gate_profile]
        warnings: list[str] = []
        if changed_paths is None:
            changed, warnings = await self._changed_paths(
                worktree,
                base_head_sha=base_head_sha,
            )
        else:
            changed = changed_paths
        try:
            plan = GateProfileResolver(config).resolve(
                feature_id=feature_id,
                worktree=worktree,
                explicit_profiles=explicit,
                changed_paths=changed,
                warnings=warnings,
            )
        except ProfileMismatchError as exc:
            return GateResult(
                passed=False,
                errors=[f"profile_mismatch failed: {exc}"],
                checks={"gate_profiles": False},
                commands={},
            )
        report = await runner.run(plan)
        return GateResult(
            passed=report.passed,
            errors=report.errors,
            checks={"gate_profiles": report.passed},
            commands={"gate_profiles": ["profiles", *report.profile_ids]},
            gate_report={
                "feature_id": report.feature_id,
                "passed": report.passed,
                "blocking_passed": report.blocking_passed,
                "nonblocking_failures": report.nonblocking_failures,
                "profile_ids": report.profile_ids,
                "artifact_dir": str(report.artifact_dir),
            },
            gate_warnings=report.warnings,
        )

    async def _changed_paths(
        self,
        worktree: Path,
        *,
        base_head_sha: str | None,
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        base_ref = f"{base_head_sha}...HEAD" if base_head_sha else self._DEFAULT_BASE_REF
        if base_head_sha is None:
            merge_base = await self._run(worktree, "git", "merge-base", "HEAD", "main")
            if merge_base.returncode == 0 and merge_base.stdout.strip():
                base_ref = f"{merge_base.stdout.strip()}...HEAD"
                warnings.append("legacy_diff_base_inferred")
        result = await self._run(worktree, "git", "diff", "--name-only", base_ref)
        if result.returncode != 0:
            return [], warnings
        return [line.strip() for line in result.stdout.splitlines() if line.strip()], warnings
```

- [ ] **Step 4: Update protocols and fakes to accept gate metadata**

Change `QualityGateLike.check()` in `xmuse/master_loop.py` to:

```python
class GateResultLike(Protocol):
    passed: bool
    errors: list[str]
    gate_report: dict[str, object] | None
    gate_warnings: list[str]


class QualityGateLike(Protocol):
    async def check(self, worktree: Path, **kwargs: Any) -> GateResultLike: ...
```

Change every fake in `tests/test_xmuse_master_loop.py` from:

```python
async def check(self, worktree: Path) -> FakeGateResult:
```

to:

```python
async def check(self, worktree: Path, **kwargs: object) -> FakeGateResult:
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_xmuse_quality_gate.py tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/xmuse_core/agents/quality_gate.py xmuse/master_loop.py tests/test_xmuse_quality_gate.py tests/test_xmuse_gate_profiles.py
git commit -m "feat: run lane gates through gate profiles"
```

## Task 8: Integrate Full Gate Profiles in MasterLoop

**Files:**
- Modify: `xmuse/master_loop.py`
- Modify: `tests/test_xmuse_master_loop.py`

- [ ] **Step 1: Write failing full-gate config tests**

Add or update these tests in `tests/test_xmuse_master_loop.py`:

```python
@dataclass
class FakeGateResult:
    passed: bool
    errors: list[str]
    gate_report: dict[str, object] | None = None
    gate_warnings: list[str] | None = None


@pytest.mark.asyncio
async def test_twenty_successful_lanes_enqueue_profiled_full_quality_gate(
    tmp_path,
    monkeypatch,
):
    from master_loop import FULL_QUALITY_GATE_TASK_TYPE, MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": f"lane-{idx}",
                "task_type": "execute",
                "prompt": "fix",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            }
            for idx in range(20)
        ],
    )

    consumer = FakeConsumer(["done"] * 20)
    gate = FakeGate([FakeGateResult(True, [])])
    rework = FakeReworkLoop(FakeLaneResult("done"))
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=consumer,
        quality_gate=gate,
        rework_loop=rework,
        max_hours=1,
        max_concurrent=4,
        discovery_enabled=False,
    )

    summary = await loop.run()

    lanes = _read_lanes(lanes_path)
    full_gate_lanes = [
        lane for lane in lanes if lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE
    ]
    assert summary.successful_lanes == 21
    assert len(full_gate_lanes) == 1
    assert full_gate_lanes[0]["status"] == "done"
    assert full_gate_lanes[0]["gate_profiles"] == ["strict-product"]
    assert full_gate_lanes[0]["batch_lane_ids"] == [f"lane-{idx}" for idx in range(20)]


@pytest.mark.asyncio
async def test_nineteen_successful_lanes_do_not_enqueue_full_quality_gate(tmp_path):
    from master_loop import FULL_QUALITY_GATE_TASK_TYPE, MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": f"lane-{idx}",
                "task_type": "execute",
                "prompt": "fix",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            }
            for idx in range(19)
        ],
    )
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=FakeConsumer(["done"] * 19),
        quality_gate=FakeGate([FakeGateResult(True, [])]),
        rework_loop=FakeReworkLoop(FakeLaneResult("done")),
        max_hours=1,
        max_concurrent=4,
        discovery_enabled=False,
    )

    await loop.run()

    assert [
        lane for lane in _read_lanes(lanes_path) if lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE
    ] == []


@pytest.mark.asyncio
async def test_historical_nonblocking_gate_warning_does_not_fail_or_repair(tmp_path):
    from master_loop import MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "historical-lane",
                "task_type": "execute",
                "prompt": "touch historical diagnostics",
                "worktree": str(tmp_path),
                "gate_profiles": ["historical"],
            }
        ],
    )
    gate_result = FakeGateResult(
        True,
        [],
        gate_report={
            "profile_ids": ["historical"],
            "passed": True,
            "blocking_passed": True,
            "nonblocking_failures": ["historical"],
        },
        gate_warnings=["nonblocking profile failed: historical"],
    )
    gate = FakeGate([gate_result])
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=FakeConsumer(["done"]),
        quality_gate=gate,
        rework_loop=FakeReworkLoop(FakeLaneResult("done")),
        max_hours=1,
        max_concurrent=1,
        discovery_enabled=False,
    )

    summary = await loop.run()

    lanes = _read_lanes(lanes_path)
    assert summary.failed_lanes == 0
    assert lanes[0]["status"] == "done"
    assert lanes[0]["gate_report"]["profile_ids"] == ["historical"]
    assert lanes[0]["gate_warnings"] == ["nonblocking profile failed: historical"]
    assert not any(lane["feature_id"].startswith("full-quality-gate-repair-") for lane in lanes)
    assert loop.rework_loop.calls == []
```

Update existing `test_twelve_successful_lanes_enqueue_full_quality_gate` to the 20-lane version or remove the old test after the new tests exist.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_xmuse_master_loop.py -q
```

Expected: FAIL because current interval is 12 and generated full gate lanes do not include `gate_profiles`.

- [ ] **Step 3: Replace hard-coded full gate command path**

In `xmuse/master_loop.py`:

- Remove `FULL_QUALITY_GATE_INTERVAL = 12`, `FULL_QUALITY_GATE_IGNORES`, `FULL_QUALITY_GATE_EXPRESSION`, `FULL_QUALITY_GATE_PYTEST_ARGS`, `FULL_QUALITY_GATE_COMMAND`, and `FULL_QUALITY_GATE_COMMAND_TEXT`.
- Add:

```python
DEFAULT_GATE_PROFILES_PATH = ROOT / "xmuse" / "gate_profiles.json"
```

In `MasterLoop.__init__`, add `gate_profiles_path: Path = DEFAULT_GATE_PROFILES_PATH` and store `self.gate_profiles_path`.

In `MasterLoop.from_defaults()`, construct the default gate with the same config path:

```python
        return cls(
            lanes_path=lanes_path,
            auto_discovery_path=auto_discovery_path,
            consumer=consumer,
            quality_gate=QualityGate(
                profile_config_path=DEFAULT_GATE_PROFILES_PATH,
                repo_root=ROOT,
            ),
            rework_loop=ReworkLoop(error_knowledge=error_knowledge),
            error_knowledge=error_knowledge,
            max_hours=max_hours,
            max_concurrent=max_concurrent,
            discovery_enabled=discovery_enabled,
            gate_profiles_path=DEFAULT_GATE_PROFILES_PATH,
        )
```

Add a regression test:

```python
def test_master_loop_from_defaults_enables_profile_gate(monkeypatch, tmp_path):
    import master_loop
    import xmuse_core.agents.rework_loop as rework_loop_module
    from master_loop import DEFAULT_GATE_PROFILES_PATH, MasterLoop

    monkeypatch.setattr(master_loop.AgentRegistry, "from_file", lambda path: object())
    monkeypatch.setattr(master_loop, "MemoryOSClient", lambda base_url: object())
    monkeypatch.setattr(master_loop, "SessionManager", lambda **kwargs: object())
    monkeypatch.setattr(master_loop, "WorklistConsumer", lambda **kwargs: object())
    monkeypatch.setattr(master_loop, "ErrorKnowledge", lambda: object())
    monkeypatch.setattr(rework_loop_module, "ReworkLoop", lambda error_knowledge: object())

    loop = MasterLoop.from_defaults(lanes_path=tmp_path / "feature_lanes.json")

    assert loop.quality_gate.profile_config_path == DEFAULT_GATE_PROFILES_PATH
    assert loop.quality_gate.repo_root == master_loop.ROOT
```

Add helper:

```python
    def _full_gate_interval(self) -> int:
        from xmuse_core.gates.loader import load_gate_config

        config = load_gate_config(self.gate_profiles_path, repo_root=ROOT)
        return config.defaults.full_gate_interval
```

Use `_full_gate_interval()` in `_maybe_append_full_quality_gate_lane()` and `_next_full_gate_batch()` instead of the removed constant.

- [ ] **Step 4: Generate profiled full-gate lanes**

In `_maybe_append_full_quality_gate_lane()`, append:

```python
"prompt": "Run the strict-product xmuse quality gate.",
"gate_profiles": ["strict-product"],
"base_head_sha": head_sha,
```

Keep `head_sha` for compatibility, but use `base_head_sha` for diff base semantics.

- [ ] **Step 5: Run full-gate through QualityGate profile path**

Change `_run_full_quality_gate_lane()`:

```python
    async def _run_full_quality_gate_lane(self, task: TaskDescriptor) -> str:
        self._update_lane_status(task.feature_id, "running")
        gate_result = await self.quality_gate.check(
            ROOT,
            feature_id=task.feature_id,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles or ["strict-product"],
            changed_paths=[],
            base_head_sha=task.base_head_sha,
        )
        if gate_result.passed:
            self._record_gate_report(task.feature_id, gate_result)
            self._update_lane_status(task.feature_id, "done")
            return "done"

        self._record_gate_report(task.feature_id, gate_result)
        artifact_path = self._write_full_gate_artifact_from_errors(task.feature_id, gate_result.errors)
        await self._append_full_gate_repair_lane(task, gate_result, artifact_path)
        self._update_lane_status(task.feature_id, "failed")
        return "failed"
```

Add compatibility artifact helper:

```python
    def _write_full_gate_artifact_from_errors(
        self,
        feature_id: str,
        errors: list[str],
    ) -> Path:
        artifact_dir = ROOT / "xmuse" / "logs" / "full_quality_gate"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{feature_id}.log"
        artifact_path.write_text("\n\n".join(errors) + "\n", encoding="utf-8")
        return artifact_path
```

Add lane report helper:

```python
    def _record_gate_report(self, feature_id: str, result: GateResultLike) -> None:
        report = getattr(result, "gate_report", None)
        warnings = getattr(result, "gate_warnings", None) or []
        if report is None and not warnings:
            return
        data = json.loads(self.lanes_path.read_text(encoding="utf-8"))
        for lane in data.get("lanes", []):
            if lane.get("feature_id") != feature_id:
                continue
            if report is not None:
                lane["gate_report"] = report
            if warnings:
                lane["gate_warnings"] = list(warnings)
            break
        _write_json_atomic(self.lanes_path, data)
```

Update `_append_full_gate_repair_lane()` to accept `GateResultLike` instead of `ProcessResult` and use:

```python
output = "\n\n".join(result.errors)[-6000:]
```

In repair prompt, replace the old hard-coded command line with:

```python
"Profile: strict-product\n"
```

- [ ] **Step 6: Pass gate metadata to lane-local checks**

In `_run_lane()`, call:

```python
gate_result = await self.quality_gate.check(
    Path(task.worktree),
    feature_id=task.feature_id,
    gate_profile=task.gate_profile,
    gate_profiles=task.gate_profiles,
    base_head_sha=task.base_head_sha,
)
self._record_gate_report(task.feature_id, gate_result)
```

Keep the existing `if gate_result.passed:` branch immediately after this call. This ensures nonblocking historical failures are written to lane metadata but still proceed through the successful lane path because `GateResult.passed` reflects blocking status only.

- [ ] **Step 7: Run tests**

Run:

```bash
uv run pytest tests/test_xmuse_master_loop.py tests/test_xmuse_quality_gate.py tests/test_xmuse_gate_profiles.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add xmuse/master_loop.py tests/test_xmuse_master_loop.py tests/test_xmuse_quality_gate.py tests/test_xmuse_gate_profiles.py
git commit -m "feat: run full gates through profiles"
```

## Task 9: Final Verification

**Files:**
- No new files.
- Verify all changed files.

- [ ] **Step 1: Run targeted test suite**

Run:

```bash
uv run pytest tests/test_xmuse_gate_profiles.py tests/test_xmuse_master_loop.py tests/test_xmuse_quality_gate.py tests/test_xmuse_auto_discovery.py -q
```

Expected: PASS.

- [ ] **Step 2: Run ruff**

Run:

```bash
uv run ruff check src/xmuse_core/gates src/xmuse_core/agents/consumer.py src/xmuse_core/agents/quality_gate.py xmuse/master_loop.py tests/test_xmuse_gate_profiles.py tests/test_xmuse_master_loop.py tests/test_xmuse_quality_gate.py
```

Expected: PASS.

- [ ] **Step 3: Check config command collection**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
from xmuse_core.gates.loader import load_gate_config

config = load_gate_config(Path("xmuse/gate_profiles.json"), repo_root=Path("."))
strict = config.profiles["strict-product"]
print(config.defaults.full_gate_interval)
print(len(strict.commands[0].args))
print(strict.env)
PY
```

Expected output includes:

```text
20
{'MEMORYOS_MEMORY_ARCH': 'v3', 'MEMORYOS_RECALL_PIPELINE': 'v2', 'MEMORYOS_PAGING_MODE': 'off', 'MEMORYOS_AGENT_KERNEL': 'off'}
```

- [ ] **Step 4: Review git diff**

Run:

```bash
git diff --stat HEAD
git status --short
```

Expected: only intended gate profile implementation files are modified or already committed.

- [ ] **Step 5: Finish without an empty commit**

If Task 9 required fixes, return to the task that introduced the failing file,
apply the fix there, rerun that task's test command, and use that task's commit
command. If no fixes were needed, do not create an empty commit.
