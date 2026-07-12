from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KernelToolSpec:
    name: str
    level: int
    mutating: bool
    requires_policy_check: bool
    requires_source_refs_or_approval: bool
    requires_approval_by_default: bool
    verification_required: bool
    description: str


_PHASE16_KERNEL_TOOLS: dict[str, KernelToolSpec] = {
    "archive_write": KernelToolSpec(
        name="archive_write",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description="Write source-backed archival memory and attach it to the current session.",
    ),
    "archive_attach": KernelToolSpec(
        name="archive_attach",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description="Attach an existing archive to the current session scope.",
    ),
    "core_promotion_request": KernelToolSpec(
        name="core_promotion_request",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description="Create a pending core promotion candidate without applying it.",
    ),
    "core_candidate_apply": KernelToolSpec(
        name="core_candidate_apply",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description=(
            "Apply an approved pending core promotion candidate through lifecycle governance."
        ),
    ),
}


def get_kernel_tool_spec(tool_name: str) -> KernelToolSpec | None:
    return _PHASE16_KERNEL_TOOLS.get(tool_name)


def executable_kernel_tool_names() -> set[str]:
    return set(_PHASE16_KERNEL_TOOLS)


__all__ = [
    "KernelToolSpec",
    "executable_kernel_tool_names",
    "get_kernel_tool_spec",
]
