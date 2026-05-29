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
        has_commands = bool(profile.commands)
        if profile.blocking and not has_manifest and not has_commands:
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
