from __future__ import annotations

import json
from pathlib import Path

from memoryos_lite.config import Settings
from memoryos_lite.public_benchmarks import (
    PublicBenchmarkResult,
    _extract_item_metrics,
    run_public_benchmark,
)
from memoryos_lite.schemas import TraceEvent, utc_now
from memoryos_lite.store import create_store


def _make_store(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    return store


# ---------------------------------------------------------------------------
# PublicBenchmarkResult field defaults
# ---------------------------------------------------------------------------


def test_public_benchmark_result_has_item_fields():
    result = PublicBenchmarkResult(
        benchmark="longmemeval",
        baseline="full",
        case_id="c1",
        question="q",
        expected_answer="a",
        answer="a",
        answer_mode="projected",
        verdict="pass",
        reasoning="exact",
        expected_present=[],
        expected_missing=[],
        source_ids=[],
        expected_source_ids=[],
        source_overlap_ids=[],
        missing_source_ids=[],
        retrieval_candidate_top_k=None,
        retrieval_candidate_unit=None,
        retrieval_candidate_page_ids=[],
        retrieval_candidate_source_ids=[],
        retrieval_candidate_session_ids=[],
        page_candidate_top_k=None,
        page_candidate_page_ids=[],
        page_candidate_source_ids=[],
        page_candidate_session_ids=[],
        source_recall=None,
        source_hit=None,
        source_hit_at_k=None,
        page_source_overlap_at_k=None,
        expected_session_ids=[],
        source_session_ids=[],
        session_overlap_ids=[],
        missing_session_ids=[],
        session_recall=None,
        session_hit=None,
        session_hit_at_k=None,
        page_session_overlap_at_k=None,
        context_tokens=0,
        page_count=0,
        loaded_pages=0,
        dropped_pages=0,
        page_type_counts={},
        page_source_counts=[],
        page_summary_token_counts=[],
        retrieved_page_ids=[],
        dropped_page_reasons={},
        dropped_relevant_page_ids=[],
        dropped_relevant_page_count=0,
        superseded_source_recovered=0,
        candidate_budget_dropped=0,
        active_overlap_not_top5=0,
        latency_ms=0,
    )
    assert result.item_source_overlap_at_k is None
    assert result.item_promoted_evidence_count == 0
    assert result.item_evidence_budget_dropped == 0
    assert result.source_not_indexed is False
    assert result.item_hit_item_ids == []
    assert result.item_hit_source_ids == []


# ---------------------------------------------------------------------------
# _extract_item_metrics — no item_retrieval trace
# ---------------------------------------------------------------------------


def test_extract_item_metrics_no_trace(tmp_path):
    store = _make_store(tmp_path)
    metrics = _extract_item_metrics(store, "session_x", ["msg_001"])
    assert metrics["item_source_overlap_at_k"] is None
    assert metrics["item_promoted_evidence_count"] == 0
    assert metrics["item_evidence_budget_dropped"] == 0
    assert metrics["source_not_indexed"] is False
    assert metrics["item_hit_item_ids"] == []
    assert metrics["item_hit_source_ids"] == []


# ---------------------------------------------------------------------------
# _extract_item_metrics — item_retrieval trace with hits
# ---------------------------------------------------------------------------


def test_extract_item_metrics_with_trace_overlap(tmp_path):
    store = _make_store(tmp_path)
    session_id = "session_y"
    trace = TraceEvent(
        session_id=session_id,
        event_type="item_retrieval",
        payload={
            "item_hit_ids": ["item_001", "item_002"],
            "promoted_source_ids": ["msg_001", "msg_003"],
            "promoted_evidence_count": 2,
            "item_evidence_budget_dropped": 1,
        },
        created_at=utc_now(),
    )
    store.add_trace(trace)

    metrics = _extract_item_metrics(store, session_id, ["msg_001"])
    assert metrics["item_source_overlap_at_k"] is True
    assert metrics["item_promoted_evidence_count"] == 2
    assert metrics["item_evidence_budget_dropped"] == 1
    assert metrics["item_hit_item_ids"] == ["item_001", "item_002"]
    assert metrics["item_hit_source_ids"] == ["msg_001", "msg_003"]


def test_extract_item_metrics_with_trace_no_overlap(tmp_path):
    store = _make_store(tmp_path)
    session_id = "session_z"
    trace = TraceEvent(
        session_id=session_id,
        event_type="item_retrieval",
        payload={
            "item_hit_ids": ["item_010"],
            "promoted_source_ids": ["msg_999"],
            "promoted_evidence_count": 1,
            "item_evidence_budget_dropped": 0,
        },
        created_at=utc_now(),
    )
    store.add_trace(trace)

    metrics = _extract_item_metrics(store, session_id, ["msg_001"])
    assert metrics["item_source_overlap_at_k"] is False
    assert metrics["item_hit_source_ids"] == ["msg_999"]


# ---------------------------------------------------------------------------
# source_mapping.json written by run_public_benchmark
# ---------------------------------------------------------------------------


def _make_locomo_data(tmp_path: Path, sample_id: str) -> Path:
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": sample_id,
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The final project is MemoryOS Lite.",
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:2",
                                "text": "Agreed, MemoryOS Lite it is.",
                            },
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the final project?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return data_path


def test_run_public_benchmark_writes_source_mapping(tmp_path):
    data_path = _make_locomo_data(tmp_path, "sample_map")
    eval_root = tmp_path / "eval_runs"
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_eval_data_dir=eval_root,
    )

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="mapping-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    mapping_path = eval_root / "mapping-test" / "source_mapping.json"
    assert mapping_path.exists(), "source_mapping.json was not written"

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    # Two messages were ingested; both benchmark IDs should appear as keys
    expected_bench_ids = {
        "sample_map_qa_001:sample_map:D1:1",
        "sample_map_qa_001:sample_map:D1:2",
    }
    assert expected_bench_ids <= set(mapping.keys()), (
        f"Expected benchmark IDs {expected_bench_ids} not all present in mapping keys: "
        f"{set(mapping.keys())}"
    )


def test_run_public_benchmark_source_mapping_values_are_stored_ids(tmp_path):
    data_path = _make_locomo_data(tmp_path, "sample_ids")
    eval_root = tmp_path / "eval_runs"
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_eval_data_dir=eval_root,
    )

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="ids-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    mapping_path = eval_root / "ids-test" / "source_mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    # All values must be non-empty strings (stored message IDs)
    assert all(isinstance(v, str) and v for v in mapping.values()), (
        "All mapping values must be non-empty strings"
    )
    # The mapping must be non-empty
    assert len(mapping) >= 2
