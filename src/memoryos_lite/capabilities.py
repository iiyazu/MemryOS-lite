"""Stable optional-dependency capability checks."""

from __future__ import annotations

from importlib.util import find_spec


class MissingOptionalCapabilityError(RuntimeError):
    """Raised when a requested optional feature is not installed."""

    def __init__(self, capability: str, extra: str, missing: list[str]) -> None:
        self.capability = capability
        self.extra = extra
        self.missing = tuple(missing)
        super().__init__(
            f"memoryos capability '{capability}' is unavailable; "
            f"install memoryos-lite[{extra}] (missing: {', '.join(missing)})"
        )


def require_remote_capability(capability: str) -> None:
    missing = [
        package
        for package in ("langchain_core", "langchain_openai", "langgraph", "qdrant_client")
        if find_spec(package) is None
    ]
    if missing:
        raise MissingOptionalCapabilityError(capability, "remote", missing)


def require_benchmark_capability(capability: str) -> None:
    """Prove both Hybrid retrieval and remote benchmark dependencies."""

    missing = [
        package
        for package in (
            "fastembed",
            "langchain_core",
            "langchain_openai",
            "langgraph",
            "qdrant_client",
        )
        if find_spec(package) is None
    ]
    if missing:
        raise MissingOptionalCapabilityError(capability, "benchmark", missing)
