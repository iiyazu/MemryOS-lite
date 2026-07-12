from __future__ import annotations

import ast
import tomllib
from pathlib import Path


def test_memoryos_lite_does_not_import_xmuse_core() -> None:
    root = Path("src/memoryos_lite")
    offenders: list[tuple[str, str]] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "xmuse_core" or alias.name.startswith("xmuse_core."):
                        offenders.append((str(path), alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "xmuse_core" or module.startswith("xmuse_core."):
                    offenders.append((str(path), module))

    assert offenders == []


def test_memoryos_package_metadata_does_not_export_xmuse_entrypoints() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    scripts = pyproject["project"]["scripts"]
    assert set(scripts) == {"memoryos", "memoryos-lite"}
    assert not any(name.startswith("xmuse") for name in scripts)


def test_memoryos_default_dependencies_do_not_include_xmuse_runtime_packages() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]
    assert not any(dep.startswith("ray") for dep in dependencies)
    assert not any(dep.startswith("textual") for dep in dependencies)
    assert "xmuse" not in pyproject["project"].get("optional-dependencies", {})


def test_memoryos_tree_does_not_contain_importable_xmuse_source() -> None:
    forbidden_roots = [
        Path("src/xmuse_core"),
        Path("tests/xmuse"),
        Path("tests/fixtures/xmuse"),
    ]
    assert [str(path) for path in forbidden_roots if path.exists()] == []

    xmuse_root = Path("xmuse")
    if xmuse_root.exists():
        source_files = [
            str(path)
            for path in xmuse_root.rglob("*")
            if path.is_file() and path.suffix in {".py", ".pyc", ".sh", ".css", ".tcss"}
        ]
        assert source_files == []


def test_memoryos_tree_keeps_only_documentation_under_legacy_xmuse_root() -> None:
    xmuse_root = Path("xmuse")
    if not xmuse_root.exists():
        return

    non_document_files = [
        str(path)
        for path in xmuse_root.rglob("*")
        if path.is_file() and path.suffix not in {".md", ".txt"}
    ]

    assert non_document_files == []
