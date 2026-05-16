from __future__ import annotations

from pathlib import Path

from memoryos_lite.config import Settings
from memoryos_lite.public_benchmarks import PublicBenchmarkResult, _extract_item_metrics
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
