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
        return GatePlan(
            feature_id=feature_id,
            worktree=worktree,
            profiles=profiles,
            blocking=any(profile.blocking for profile in profile_objs),
            commands=self._build_commands(profile_objs),
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

    def _build_commands(self, profiles: list[GateProfile]) -> list[CommandPlan]:
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
