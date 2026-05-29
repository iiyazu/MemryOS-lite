#!/usr/bin/env python3
"""Discover failing checks and emit xmuse feature lanes as JSON."""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tokenize
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

PYTEST_COMMAND = ["uv", "run", "pytest", "tests/", "-x", "--timeout=60", "-q"]
RUFF_COMMAND = ["uv", "run", "ruff", "check", "src/", "xmuse/"]
MYPY_COMMAND = ["uv", "run", "mypy", "src/", "--ignore-missing-imports"]
COVERAGE_COMMAND = ["uv", "run", "pytest", "--cov=src", "--cov-report=json"]

CAPABILITIES = ["code", "test"]
FEATURE_LANES_PATH = Path("xmuse/feature_lanes.json")
COVERAGE_JSON_PATH = Path("coverage.json")
COVERAGE_THRESHOLD = 50.0
PRIORITY_PYTEST = 100
PRIORITY_MYPY = 80
PRIORITY_RUFF = 60
PRIORITY_COVERAGE = 40
PRIORITY_TODO = 20

PYTEST_FAILED_RE = re.compile(
    r"^FAILED\s+"
    r"(?P<nodeid>(?P<path>(?:[A-Za-z]:)?[^\s:]+\.py)(?:::[^\s]+)?)"
    r"(?:\s+-\s+(?P<message>.+))?$"
)
PYTEST_LOCATION_RE = re.compile(r"^(?P<path>(?:[A-Za-z]:)?[^\s:]+\.py):\d+:")
PYTEST_ERROR_RE = re.compile(r"^E\s+(?P<message>.+)$")

RUFF_CLASSIC_RE = re.compile(
    r"^(?P<path>(?:[A-Za-z]:)?[^\s:]+\.py):"
    r"(?P<line>\d+):(?P<column>\d+):\s+"
    r"(?P<code>[A-Z]+\d+)\s+(?P<message>.+)$"
)
RUFF_CODE_RE = re.compile(r"^(?P<code>[A-Z]+\d+)\b.*")
RUFF_LOCATION_RE = re.compile(
    r"^\s*-->\s+(?P<path>(?:[A-Za-z]:)?[^\s:]+\.py):"
    r"(?P<line>\d+):(?P<column>\d+)"
)

MYPY_ERROR_RE = re.compile(
    r"^(?P<path>(?:[A-Za-z]:)?[^\s:]+\.py):"
    r"(?P<line>\d+)"
    r"(?::(?P<column>\d+))?:\s+"
    r"error:\s+(?P<message>.+?)"
    r"(?:\s+\[(?P<code>[a-zA-Z0-9_-]+)\])?$"
)

ISSUE_COMMENT_RE = re.compile(r"\b(?P<tag>TODO|FIXME|HACK)\b(?P<body>.*)", re.IGNORECASE)
CODE_SCAN_DIRS = ("src", "xmuse", "tests")


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def discover(
    *,
    run_pytest: bool,
    run_ruff: bool,
    run_mypy: bool,
    run_coverage: bool,
    run_git_issues: bool,
    lanes_path: Path = FEATURE_LANES_PATH,
    root: Path = Path("."),
) -> list[dict[str, object]]:
    lanes: list[dict[str, object]] = []
    if run_pytest:
        result = run_command(PYTEST_COMMAND)
        if result.returncode != 0:
            lanes.extend(parse_pytest_output(_combined_output(result)))
    if run_ruff:
        result = run_command(RUFF_COMMAND)
        if result.returncode != 0:
            lanes.extend(parse_ruff_output(_combined_output(result)))
    if run_mypy:
        result = run_command(MYPY_COMMAND)
        if result.returncode != 0:
            lanes.extend(parse_mypy_output(_combined_output(result)))
    if run_coverage:
        run_command(COVERAGE_COMMAND)
        lanes.extend(parse_coverage_json(root / COVERAGE_JSON_PATH))
    if run_git_issues:
        lanes.extend(parse_git_issue_comments(root))

    existing_ids = load_existing_feature_ids(lanes_path)
    return finalize_lanes(lanes, existing_ids=existing_ids)


def parse_pytest_output(output: str) -> list[dict[str, object]]:
    lanes = []
    seen: set[str] = set()
    lines = output.splitlines()

    for line in lines:
        match = PYTEST_FAILED_RE.match(line.strip())
        if match is None:
            continue
        path = match.group("path")
        exact_message = line.strip()
        key = f"pytest:{exact_message}"
        if key in seen:
            continue
        seen.add(key)
        lanes.append(
            make_lane(
                feature_id_parts=["auto", "pytest", match.group("nodeid")],
                prompt=(
                    f"Fix pytest failure in {path}.\n\n"
                    f"Exact error message:\n{exact_message}\n\n"
                    "Run `uv run pytest tests/ -x --timeout=60 -q` to verify the fix."
                ),
                priority=PRIORITY_PYTEST,
            )
        )

    if lanes:
        return lanes

    fallback = _parse_pytest_fallback(lines)
    if fallback is None:
        return []
    path, exact_message = fallback
    return [
        make_lane(
            feature_id_parts=["auto", "pytest", path],
            prompt=(
                f"Fix pytest failure in {path}.\n\n"
                f"Exact error message:\n{exact_message}\n\n"
                "Run `uv run pytest tests/ -x --timeout=60 -q` to verify the fix."
            ),
            priority=PRIORITY_PYTEST,
        )
    ]


def parse_ruff_output(output: str) -> list[dict[str, object]]:
    lanes: list[dict[str, object]] = []
    seen: set[str] = set()
    lines = output.splitlines()
    file_errors: dict[str, list[str]] = {}

    for line in lines:
        match = RUFF_CLASSIC_RE.match(line.strip())
        if match is None:
            continue
        path = match.group("path")
        exact_message = line.strip()
        key = f"ruff:{exact_message}"
        if key in seen:
            continue
        seen.add(key)
        file_errors.setdefault(path, []).append(exact_message)

    for index, line in enumerate(lines):
        code_match = RUFF_CODE_RE.match(line.strip())
        if code_match is None:
            continue
        location = _find_next_ruff_location(lines, index + 1)
        if location is None:
            continue
        path, line_number, column, location_line = location
        exact_message = f"{line.strip()}\n{location_line}"
        key = f"ruff:{exact_message}"
        if key in seen:
            continue
        seen.add(key)
        file_errors.setdefault(path, []).append(exact_message)

    for path, errors in sorted(file_errors.items()):
        error_list = "\n".join(f"- {e}" for e in errors)
        lanes.append(
            make_lane(
                feature_id_parts=["batch", "ruff", path],
                prompt=(
                    f"Fix all ruff lint errors in {path}.\n\n"
                    f"Errors ({len(errors)}):\n{error_list}\n\n"
                    "Run `uv run ruff check src/ xmuse/` to verify the fix."
                ),
                priority=PRIORITY_RUFF,
                gate_profile="linter-only",
            )
        )

    return lanes


def parse_mypy_output(output: str) -> list[dict[str, object]]:
    lanes: list[dict[str, object]] = []
    seen: set[str] = set()
    file_errors: dict[str, list[str]] = {}
    for line in output.splitlines():
        match = MYPY_ERROR_RE.match(line.strip())
        if match is None:
            continue
        path = match.group("path")
        exact_message = line.strip()
        key = f"mypy:{exact_message}"
        if key in seen:
            continue
        seen.add(key)
        file_errors.setdefault(path, []).append(exact_message)

    for path, errors in sorted(file_errors.items()):
        error_list = "\n".join(f"- {e}" for e in errors)
        lanes.append(
            make_lane(
                feature_id_parts=["batch", "mypy", path],
                prompt=(
                    f"Fix all mypy type errors in {path}.\n\n"
                    f"Errors ({len(errors)}):\n{error_list}\n\n"
                    "Run `uv run mypy src/ --ignore-missing-imports` to verify the fix."
                ),
                priority=PRIORITY_MYPY,
                gate_profile="linter-only",
            )
        )
    return lanes


def parse_coverage_json(
    coverage_path: Path = COVERAGE_JSON_PATH,
    *,
    threshold: float = COVERAGE_THRESHOLD,
) -> list[dict[str, object]]:
    if not coverage_path.exists():
        return []
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = payload.get("files", {})
    if not isinstance(files, dict):
        return []

    lanes: list[dict[str, object]] = []
    for path, file_payload in sorted(files.items()):
        if not isinstance(path, str) or not isinstance(file_payload, dict):
            continue
        summary = file_payload.get("summary", {})
        if not isinstance(summary, dict):
            continue
        percent = summary.get("percent_covered")
        if not isinstance(percent, int | float):
            continue
        if float(percent) >= threshold:
            continue
        lanes.append(
            make_lane(
                feature_id_parts=["auto", "coverage", path],
                prompt=(
                    f"Add or improve tests for {path}.\n\n"
                    f"Current coverage is {float(percent):.2f}%, "
                    f"below the {threshold:.2f}% threshold.\n\n"
                    "Run `uv run pytest --cov=src --cov-report=json` to verify coverage."
                ),
                priority=PRIORITY_COVERAGE,
            )
        )
    return lanes


def parse_git_issue_comments(root: Path = Path(".")) -> list[dict[str, object]]:
    lanes: list[dict[str, object]] = []
    for path in iter_code_files(root):
        rel_path = path.relative_to(root).as_posix()
        for line_number, comment in iter_issue_comments(path):
            match = ISSUE_COMMENT_RE.search(comment)
            if match is None:
                continue
            tag = match.group("tag").upper()
            lanes.append(
                make_lane(
                    feature_id_parts=["auto", tag.lower(), rel_path, str(line_number)],
                    prompt=(
                        f"Clean up {tag} comment in {rel_path}:{line_number}.\n\n"
                        f"Comment:\n{comment.strip()}\n\n"
                        "Resolve the issue or replace it with a tracked, actionable note."
                    ),
                    priority=PRIORITY_TODO,
                )
            )
    return lanes


def iter_code_files(root: Path) -> Iterable[Path]:
    for dirname in CODE_SCAN_DIRS:
        directory = root / dirname
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.py")):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            yield path


def iter_issue_comments(path: Path) -> Iterable[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT and ISSUE_COMMENT_RE.search(token.string):
                yield token.start[0], token.string
    except tokenize.TokenError:
        return


def make_lane(
    feature_id_parts: Iterable[str],
    prompt: str,
    *,
    priority: int,
    gate_profile: str | None = None,
) -> dict[str, object]:
    lane: dict[str, object] = {
        "feature_id": slugify("-".join(feature_id_parts)),
        "task_type": "execute",
        "prompt": prompt,
        "capabilities": CAPABILITIES.copy(),
        "source": "auto",
        "priority": priority,
    }
    if gate_profile:
        lane["gate_profile"] = gate_profile
    return lane


def finalize_lanes(
    lanes: Iterable[dict[str, object]],
    *,
    existing_ids: set[str],
) -> list[dict[str, object]]:
    unique: dict[str, dict[str, object]] = {}

    def lane_sort_key(candidate: dict[str, object]) -> tuple[int, str]:
        priority = candidate.get("priority", 0)
        if not isinstance(priority, int):
            priority = 0
        return -priority, str(candidate.get("feature_id", ""))

    for lane in sorted(
        lanes,
        key=lane_sort_key,
    ):
        feature_id = lane.get("feature_id")
        if not isinstance(feature_id, str):
            continue
        if feature_id in existing_ids or feature_id in unique:
            continue
        unique[feature_id] = lane
    return list(unique.values())


def load_existing_feature_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    lane_payloads: list[Any]
    if isinstance(payload, list):
        lane_payloads = payload
    elif isinstance(payload, dict):
        lanes = payload.get("lanes", payload.get("features", []))
        lane_payloads = lanes if isinstance(lanes, list) else []
    else:
        lane_payloads = []
    return {
        feature_id
        for lane in lane_payloads
        if isinstance(lane, dict)
        for feature_id in [lane.get("feature_id") or lane.get("id")]
        if isinstance(feature_id, str)
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "auto-discovered"


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _parse_pytest_fallback(lines: list[str]) -> tuple[str, str] | None:
    path = None
    for line in lines:
        match = PYTEST_LOCATION_RE.match(line.strip())
        if match is not None:
            path = match.group("path")
            break
    if path is None:
        return None

    for line in lines:
        match = PYTEST_ERROR_RE.match(line.strip())
        if match is not None:
            return path, line.strip()
    return path, f"pytest failed in {path}"


def _find_next_ruff_location(lines: list[str], start: int) -> tuple[str, str, str, str] | None:
    for line in lines[start : start + 6]:
        match = RUFF_LOCATION_RE.match(line)
        if match is not None:
            return (
                match.group("path"),
                match.group("line"),
                match.group("column"),
                line.strip(),
            )
    return None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover pytest, ruff, mypy, coverage, and code-comment issues."
    )
    parser.add_argument("--pytest", action="store_true", help="Run pytest discovery")
    parser.add_argument("--ruff", action="store_true", help="Run ruff discovery")
    parser.add_argument("--mypy", action="store_true", help="Run mypy discovery")
    parser.add_argument("--coverage", action="store_true", help="Run coverage discovery")
    parser.add_argument(
        "--git-issues",
        action="store_true",
        help="Discover TODO, FIXME, and HACK comments in code",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run default lightweight discovery checks",
    )
    parser.add_argument(
        "--lanes-path",
        type=Path,
        default=FEATURE_LANES_PATH,
        help="Path to feature_lanes.json for deduplication",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    any_source = args.pytest or args.ruff or args.mypy or args.coverage or args.git_issues
    run_default = args.all or not any_source
    lanes = discover(
        run_pytest=args.pytest,
        run_ruff=run_default or args.ruff,
        run_mypy=run_default or args.mypy,
        run_coverage=args.coverage,
        run_git_issues=run_default or args.git_issues,
        lanes_path=args.lanes_path,
    )
    print(json.dumps(lanes, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
