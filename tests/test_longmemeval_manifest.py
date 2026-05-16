from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryos_lite.longmemeval_manifest import create_manifest, load_manifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

QUESTION_TYPES = ["single-session", "multi-session", "temporal", "knowledge"]


@pytest.fixture()
def synthetic_data(tmp_path: Path) -> Path:
    """Write a synthetic LongMemEval JSON file with 60 cases, 4 types, 15 each."""
    cases = []
    for i, qt in enumerate(QUESTION_TYPES):
        for j in range(15):
            cases.append(
                {
                    "question_id": f"{qt}-{j:03d}",
                    "question_type": qt,
                    "question": f"Question {i}-{j}?",
                    "answer": f"Answer {i}-{j}",
                }
            )
    data_path = tmp_path / "longmemeval_data.json"
    data_path.write_text(json.dumps(cases), encoding="utf-8")
    return data_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_manifest_produces_50_cases(synthetic_data: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    create_manifest(synthetic_data, manifest_path, n=50, seed=42)

    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(manifest["case_ids"]) == 50
    assert manifest["seed"] == 42
    assert manifest["source_data_hash"] is not None
    assert len(manifest["source_data_hash"]) == 16


def test_create_manifest_stratified_by_question_type(
    synthetic_data: Path, tmp_path: Path
) -> None:
    manifest_path = tmp_path / "manifest.json"
    create_manifest(synthetic_data, manifest_path, n=50, seed=42)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest["cases"]

    counts: dict[str, int] = {}
    for c in cases:
        qt = c["question_type"]
        counts[qt] = counts.get(qt, 0) + 1

    # With 4 types and n=50, stratified gives 12 or 13 per type — all >= 10
    for qt in QUESTION_TYPES:
        assert counts.get(qt, 0) >= 10, (
            f"question_type '{qt}' has only {counts.get(qt, 0)} cases, expected >= 10"
        )


def test_load_manifest_returns_metadata(synthetic_data: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    create_manifest(synthetic_data, manifest_path, n=50, seed=42)

    manifest = load_manifest(manifest_path)

    for key in ("case_ids", "cases", "seed", "created_at", "source_data_hash"):
        assert key in manifest, f"manifest missing key '{key}'"

    first = manifest["cases"][0]
    assert "question_id" in first
    assert "question_type" in first
