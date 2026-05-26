from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
    env: dict[str, str]
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
