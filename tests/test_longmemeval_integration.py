"""Integration test for Phase 2.5 LongMemEval pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.diagnostic_report import FAILURE_MODES, generate_report
from memoryos_lite.longmemeval_manifest import create_manifest, load_manifest
from memoryos_lite.public_benchmarks import run_public_benchmark


@pytest.fixture()
def synthetic_longmemeval(tmp_path: Path) -> Path:
    """Create a synthetic 10-case LongMemEval dataset."""
    cases = []
    for i in range(10):
        cases.append({
            "question_id": f"q_{i:04d}",
            "question": f"What is fact {i}?",
            "answer": f"Fact {i} is about topic {i}",
            "question_type": ["single-session", "multi-session", "temporal", "knowledge"][i % 4],
            "haystack_session_ids": [f"ses_{i}"],
            "haystack_dates": ["2024-01-01"],
            "answer_session_ids": [f"ses_{i}"],
            "haystack_sessions": [[
                {"role": "user", "content": f"Let me tell you about fact {i}. Topic {i}."},
                {"role": "assistant", "content": f"I see, fact {i} is about topic {i}."},
                {"role": "user", "content": f"Yes, fact {i} is very important for our project."},
                {"role": "user", "content": f"Remember that fact {i} relates to topic {i}."},
            ]],
        })
    data_path = tmp_path / "longmemeval.json"
    data_path.write_text(json.dumps(cases), encoding="utf-8")
    return data_path


def test_full_pipeline(synthetic_longmemeval: Path, tmp_path: Path) -> None:
    """End-to-end: manifest → benchmark → metrics → report."""
    # 1. Create manifest
    manifest_path = tmp_path / "manifest.json"
    create_manifest(synthetic_longmemeval, manifest_path, n=5, seed=42)
    manifest = load_manifest(manifest_path)
    assert len(manifest["case_ids"]) == 5

    # 2. Run benchmark
    settings = Settings(data_dir=tmp_path / ".memoryos")
    results = run_public_benchmark(
        settings=settings,
        benchmark="longmemeval",
        data_path=synthetic_longmemeval,
        run_id="integration_test",
        baselines=["memoryos_lite"],
        limit=5,
        llm_answer=False,
        llm_judge=False,
        isolated=True,
    )
    assert len(results) == 5

    # 3. Verify item-level metrics exist on every result
    for r in results:
        assert hasattr(r, "item_source_overlap_at_k")
        assert hasattr(r, "item_promoted_evidence_count")
        assert hasattr(r, "item_evidence_budget_dropped")
        assert hasattr(r, "source_not_indexed")
        assert hasattr(r, "item_hit_item_ids")
        assert hasattr(r, "item_hit_source_ids")
        assert isinstance(r.item_promoted_evidence_count, int)
        assert isinstance(r.item_evidence_budget_dropped, int)
        assert isinstance(r.source_not_indexed, bool)
        assert isinstance(r.item_hit_item_ids, list)
        assert isinstance(r.item_hit_source_ids, list)

    # 4. Verify source mapping file exists and is non-empty
    mapping_path = (
        tmp_path / ".memoryos" / "eval_runs" / "integration_test" / "source_mapping.json"
    )
    assert mapping_path.exists(), "source_mapping.json was not written"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert len(mapping) > 0, "source_mapping.json must not be empty"

    # 5. Generate report and verify structure
    report = generate_report(results)
    assert report["total_cases"] == 5
    assert 0.0 <= report["source_hit_rate"] <= 1.0
    assert "failure_breakdown" in report
    for mode in report["failure_breakdown"]:
        assert mode in FAILURE_MODES, f"Unknown failure mode: {mode!r}"
