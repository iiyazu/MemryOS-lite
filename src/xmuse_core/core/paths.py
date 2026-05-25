from __future__ import annotations

from pathlib import Path
from typing import Any


def controller_path(loop: str | Path, ref: str) -> Path:
    loop_path = Path(loop)
    path = Path(ref)
    if path.is_absolute():
        return path
    if ref.startswith("xmuse/"):
        return loop_path.parent / ref
    return loop_path / ref


def resolve_controller_path(loop: str | Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return controller_path(loop, value)


def controller_display_path(loop: str | Path, path: str | Path) -> str:
    loop_path = Path(loop)
    display_path = Path(path)
    try:
        return display_path.resolve().relative_to(loop_path.parent.resolve()).as_posix()
    except ValueError:
        return str(display_path)
