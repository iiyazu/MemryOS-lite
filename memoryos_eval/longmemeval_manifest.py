from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def create_manifest(
    data_path: Path,
    output_path: Path,
    n: int = 50,
    seed: int = 42,
) -> None:
    """Create a fixed subset manifest from a LongMemEval JSON data file.

    Performs stratified sampling by question_type so each type is represented
    proportionally. Writes a JSON manifest with metadata and the sampled cases.

    Args:
        data_path: Path to the LongMemEval JSON file (list of dicts).
        output_path: Destination path for the manifest JSON.
        n: Number of cases to sample (default 50).
        seed: Random seed for reproducibility (default 42).
    """
    raw = data_path.read_bytes()
    source_data_hash = hashlib.sha256(raw).hexdigest()[:16]

    cases: list[dict[str, Any]] = json.loads(raw)

    # Group by question_type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        qt = case.get("question_type", "unknown")
        by_type.setdefault(qt, []).append(case)

    rng = random.Random(seed)

    # Stratified sampling: distribute n slots across types as evenly as possible
    types = sorted(by_type.keys())
    num_types = len(types)
    base_per_type = n // num_types
    remainder = n % num_types

    # Types with index < remainder get one extra slot
    quota: dict[str, int] = {}
    for i, qt in enumerate(types):
        quota[qt] = base_per_type + (1 if i < remainder else 0)

    sampled: list[dict[str, Any]] = []
    for qt in types:
        pool = list(by_type[qt])
        rng.shuffle(pool)
        sampled.extend(pool[: quota[qt]])

    # Shuffle final list so types are interleaved
    rng.shuffle(sampled)

    case_ids = [str(c["question_id"]) for c in sampled]
    cases_meta = [
        {"question_id": str(c["question_id"]), "question_type": c.get("question_type", "unknown")}
        for c in sampled
    ]

    manifest: dict[str, Any] = {
        "seed": seed,
        "n": n,
        "source_data_hash": source_data_hash,
        "created_at": datetime.now(UTC).isoformat(),
        "case_ids": case_ids,
        "cases": cases_meta,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load and return a manifest dict from a JSON file.

    Args:
        manifest_path: Path to the manifest JSON file.

    Returns:
        The manifest as a plain dict.
    """
    return json.loads(manifest_path.read_text(encoding="utf-8"))
