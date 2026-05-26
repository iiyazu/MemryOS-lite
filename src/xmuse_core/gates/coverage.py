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

    owned_node_files = {nodeid.split("::", 1)[0] for nodeid in owned_nodeids}
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
        if rel not in owned_node_files:
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
        if _is_test_function(item):
            nodes.append((f"{rel}::{item.name}", _decorator_markers(item.decorator_list)))
        if isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
            class_markers = _decorator_markers(item.decorator_list)
            for method in item.body:
                if _is_test_function(method):
                    nodes.append(
                        (
                            f"{rel}::{item.name}::{method.name}",
                            class_markers | _decorator_markers(method.decorator_list),
                        )
                    )
    return nodes


def _is_test_function(node: ast.AST) -> bool:
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
        "test_"
    )


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
