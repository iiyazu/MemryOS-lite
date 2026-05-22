import builtins
import importlib
import json

import memoryos_lite.public_benchmarks as public_benchmarks
from memoryos_lite.cli import PUBLIC_TABLE_COLUMNS, _public_table_rows
from memoryos_lite.config import Settings
from memoryos_lite.public_benchmarks import load_public_benchmark_cases, run_public_benchmark
from memoryos_lite.v3_contracts import (
    ArchivalPassage,
    ArchiveAttachment,
    CoreMemoryBlock,
    SourceRef,
)


def _write_single_locomo_case(
    tmp_path,
    *,
    filename: str = "locomo_case.json",
    sample_id: str = "sample_case",
    text: str = "The marker is MemoryOS Lite.",
    question: str = "What is the marker?",
    answer: str = "MemoryOS Lite",
    evidence: list[str] | None = None,
):
    data_path = tmp_path / filename
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
                                "text": text,
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": question,
                            "answer": answer,
                            "evidence": evidence or ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return data_path


def test_load_longmemeval_cases_maps_answer_sources(tmp_path):
    data_path = tmp_path / "longmemeval.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "question_id": "lme_001",
                    "question": "What project did Alex choose?",
                    "answer": "MemoryOS Lite",
                    "answer_session_ids": ["s2"],
                    "haystack_session_ids": ["s1", "s2"],
                    "haystack_dates": ["2026-01-01", "2026-01-02"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "Alex considered Runbook."}],
                        [
                            {
                                "role": "assistant",
                                "content": "Alex chose MemoryOS Lite.",
                                "has_answer": True,
                            }
                        ],
                    ],
                    "question_type": "single-session-user",
                }
            ]
        ),
        encoding="utf-8",
    )

    cases = load_public_benchmark_cases("longmemeval", data_path)

    assert len(cases) == 1
    assert cases[0].case.expected_facts == ["MemoryOS Lite"]
    assert cases[0].expected_source_ids == ["lme_001:s2:001"]
    assert cases[0].expected_session_ids == ["s2"]
    assert cases[0].messages[1].content.startswith("[2026-01-02]")


def test_load_locomo_cases_maps_qa_evidence(tmp_path):
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_a",
                    "conversation": {
                        "session_1_date_time": "2026-01-01",
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "I use MemoryOS Lite.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What does Alice use?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                            "category": "single-hop",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    cases = load_public_benchmark_cases("locomo", data_path)

    assert len(cases) == 1
    assert cases[0].case.case_id == "sample_a_qa_001"
    assert cases[0].expected_source_ids == ["sample_a_qa_001:sample_a:D1:1"]
    assert cases[0].expected_session_ids == ["D1"]


def test_cli_public_helpers_import_without_agent_answer_eval(monkeypatch):
    import memoryos_lite.cli as cli

    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "memoryos_lite.agent_answer_eval":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(
        importlib.sys.modules, "memoryos_lite.agent_answer_eval", raising=False
    )
    monkeypatch.setattr(builtins, "__import__", blocked_import)

    reloaded = importlib.reload(cli)

    assert "benchmark" in reloaded.PUBLIC_TABLE_COLUMNS


def test_run_public_benchmark_without_llm_judge_writes_report(tmp_path):
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_b",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:1",
                                "text": "The final project is MemoryOS Lite.",
                            }
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
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-test",
        baselines=["sliding_window"],
        llm_answer=False,
        llm_judge=False,
    )

    assert len(results) == 1
    assert results[0].verdict == "pass"
    assert results[0].to_report()["pass"] is True
    assert results[0].source_hit is True
    assert results[0].source_hit_at_k is None
    assert results[0].source_overlap_ids == ["sample_b_qa_001:sample_b:D1:1"]
    assert results[0].session_overlap_ids == ["D1"]
    assert (settings.data_dir / "evals" / "public-test_locomo.json").exists()
    assert (settings.data_dir / "evals" / "public-test_locomo.partial.json").exists()


def test_longmemeval_temporal_comparison_keeps_two_raw_sources(tmp_path):
    filler = " ".join(f"detail{i}" for i in range(80))
    data_path = tmp_path / "longmemeval.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "question_id": "lme_temporal_two_sources",
                    "question_type": "temporal-reasoning",
                    "question": (
                        "Which event did I attend first, the 'Effective Time Management' "
                        "workshop or the 'Data Analysis using Python' webinar?"
                    ),
                    "answer": "'Data Analysis using Python' webinar",
                    "answer_session_ids": ["s_late", "s_early"],
                    "haystack_session_ids": ["s_late", "s_early"],
                    "haystack_dates": [
                        "2023/05/28 (Sun) 21:04",
                        "2023/05/28 (Sun) 07:17",
                    ],
                    "haystack_sessions": [
                        [
                            {
                                "role": "user",
                                "content": (
                                    "I attended the workshop on "
                                    '"Effective Time Management" at the local community '
                                    f"center last Saturday. {filler}"
                                ),
                                "has_answer": True,
                            },
                            {"role": "assistant", "content": "Noted."},
                            {"role": "user", "content": f"Later unrelated planning. {filler}"},
                        ],
                        [
                            {
                                "role": "user",
                                "content": (
                                    "I participated in a webinar on "
                                    '"Data Analysis using Python" two months ago. '
                                    f"{filler}"
                                ),
                                "has_answer": True,
                            },
                            {"role": "assistant", "content": "Noted."},
                            {"role": "user", "content": "I saved notes from that webinar."},
                            {"role": "assistant", "content": "Noted."},
                            {"role": "user", "content": f"Later unrelated notes. {filler}"},
                        ],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="longmemeval",
        data_path=data_path,
        run_id="longmemeval-two-source-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    result = results[0]
    assert result.retrieval_candidate_unit == "message"
    assert set(result.source_overlap_ids) == set(result.expected_source_ids)
    assert result.source_hit_at_k is True
    assert result.session_hit_at_k is True
    assert len(result.source_ids) >= 2


def test_longmemeval_temporal_anchor_exposes_page_candidate(tmp_path):
    filler = " ".join(f"background{i}" for i in range(45))
    data_path = tmp_path / "longmemeval.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "question_id": "lme_temporal_anchor_page",
                    "question_type": "temporal-reasoning",
                    "question": "When did I visit the Museum of Temporal Retrieval?",
                    "answer": "March 19th",
                    "answer_session_ids": ["s_temporal"],
                    "haystack_session_ids": ["s_temporal"],
                    "haystack_dates": ["2023/03/26 (Sun) 22:45"],
                    "haystack_sessions": [
                        [
                            {
                                "role": "user",
                                "content": (
                                    f"{filler}. On March 19th, I visited the "
                                    "Museum of Temporal Retrieval."
                                ),
                                "has_answer": True,
                            },
                            {"role": "assistant", "content": "Noted."},
                            {
                                "role": "user",
                                "content": "Older unrelated note about groceries.",
                            },
                            {"role": "user", "content": "Recent unrelated note about weather."},
                            {"role": "assistant", "content": "Noted."},
                        ],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="longmemeval",
        data_path=data_path,
        run_id="longmemeval-temporal-anchor-page-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    result = results[0]
    expected_source_id = "lme_temporal_anchor_page:s_temporal:001"
    assert result.page_source_overlap_at_k is True
    assert expected_source_id in result.page_candidate_source_ids


def test_public_benchmark_compare_baselines_reports_all_rows(tmp_path):
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_c",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:1",
                                "text": "The final project is MemoryOS Lite.",
                            }
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
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-compare-test",
        baselines=["all"],
        llm_answer=False,
        llm_judge=False,
    )

    assert {result.baseline for result in results} == {
        "sliding_window",
        "naive_summary",
        "vector_rag",
        "memoryos_lite",
    }
    rows = _public_table_rows(results)
    assert {row["baseline"] for row in rows} == {
        "sliding_window",
        "naive_summary",
        "vector_rag",
        "memoryos_lite",
    }
    assert all(set(PUBLIC_TABLE_COLUMNS) <= set(row) for row in rows)
    assert all("rel_dropped" in row for row in rows)
    assert all("sup_rec" in row for row in rows)
    assert all("cand_drop" in row for row in rows)
    assert all("act_not5" in row for row in rows)
    assert all("srcs/page" in row for row in rows)
    assert next(row for row in rows if row["baseline"] == "sliding_window")["msg_src@5"] == "-"


def test_public_benchmark_reports_dropped_relevant_memoryos_page(tmp_path):
    filler = " ".join("x" for _ in range(200))
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_d",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": f"决定：the interview marker is MemoryOS Lite. {filler}",
                            },
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:2",
                                "text": f"决定：related marker planning notes. {filler}",
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:3",
                                "text": f"决定：more marker discussion. {filler}",
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:4",
                                "text": "Recent distractor about lunch.",
                            },
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:5",
                                "text": "Recent distractor about weather.",
                            },
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the interview marker?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v1",
        memoryos_page_window_max_messages=100,
        memoryos_page_window_max_tokens=100_000,
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-dropped-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    assert len(results) == 1
    result = results[0]
    assert result.page_count == 1
    assert result.loaded_pages == 1
    assert result.dropped_pages == 0
    assert result.source_hit is True
    assert result.source_hit_at_k is True
    assert result.page_source_overlap_at_k is True
    assert result.session_hit is True
    assert result.session_hit_at_k is True
    assert result.page_session_overlap_at_k is True
    assert result.retrieval_candidate_unit == "message"
    assert result.page_candidate_page_ids
    assert result.retrieval_candidate_source_ids
    assert result.dropped_relevant_page_count == 0
    assert result.source_not_indexed is False
    assert result.page_type_counts
    assert result.page_source_counts == [3]


def test_public_benchmark_reports_windowed_page_diagnostics(tmp_path):
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_e",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The interview marker is MemoryOS Lite.",
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:2",
                                "text": "MemoryOS Lite is the final marker.",
                            },
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:3",
                                "text": "Unrelated planning details. " * 80,
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:4",
                                "text": "Unrelated travel details. " * 80,
                            },
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:5",
                                "text": "Another recent distractor about weather.",
                            },
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:6",
                                "text": "Recent distractor about lunch.",
                            },
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the interview marker?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v1",
        memoryos_page_window_max_messages=2,
        memoryos_page_window_max_tokens=10_000,
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-windowed-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    result = results[0]
    assert result.page_count == 2
    assert result.loaded_pages >= 1
    assert result.dropped_relevant_page_count == 0
    assert result.page_source_counts == [2, 2]
    assert len(result.page_summary_token_counts) == 2


def test_public_benchmark_reports_v2_recall_diagnostics(tmp_path):
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_v2",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The v2 recall marker is MemoryOS Lite.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the v2 recall marker?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recall_pipeline="v2",
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v2-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["episode_candidate_message_ids"]
    assert "planned_evidence_message_ids" in report
    assert "recall_candidate_message_ids" not in report
    assert "recall_planned_message_ids" not in report
    assert "item_source_hit_at_10" in report
    assert report["episode_source_hit_at_10"] is True
    assert report["planned_evidence_source_hit_at_5"] is True
    assert report["source_not_indexed"] is False


def test_public_benchmark_reports_v3_context_diagnostics(tmp_path):
    data_path = tmp_path / "locomo_v3.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_v3",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The v3 recall marker is MemoryOS Lite.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the v3 recall marker?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["memory_arch"] == "v3"
    assert report["v3_layer_counts"]["task"] == 1
    assert report["v3_layer_counts"]["recent"] >= 1
    assert report["v3_budget_decisions"]
    assert report["v3_diagnostics"]
    assert report["indexed_source_ids"]
    assert report["episode_candidate_message_ids"]
    assert report["planned_evidence_message_ids"]
    assert "episode_source_hit_at_10" in report
    assert "planned_evidence_source_hit_at_5" in report


def test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail(tmp_path):
    data_path = tmp_path / "locomo_taxonomy.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_taxonomy",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The supported marker is MemoryOS Lite.",
                            },
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:2",
                                "text": "A distractor says the marker is ArchiveBox.",
                            },
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the supported marker?",
                            "answer": "NeverReturnedExpectedToken",
                            "evidence": ["D1:1"],
                        },
                        {
                            "question": "What is the absent marker?",
                            "answer": "Not in memory",
                            "evidence": ["D9:9"],
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase2-taxonomy-red",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )
    reports = {result.case_id: result.to_report() for result in results}

    hit = reports["sample_taxonomy_qa_001"]["case_diagnostics"]
    miss = reports["sample_taxonomy_qa_002"]["case_diagnostics"]

    assert hit["retrieval_status"] == "evidence_retrieved"
    assert hit["selected_context_status"] == "evidence_selected"
    assert hit["rendered_context_status"] == "evidence_rendered"
    assert reports["sample_taxonomy_qa_001"]["verdict"] == "fail"
    assert hit["failure_class"] == "evidence_hit_answer_fail"
    assert miss["failure_class"] == "retrieval_miss"
    assert hit["failure_class"] != miss["failure_class"]


def test_public_benchmark_case_diagnostics_classifies_unsupported_answer_separately():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    diagnostics = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="unsupported-demo",
        memory_arch="v1",
        answer="The answer is unsupported. [source:bad-id]",
        answer_mode="llm",
        verdict="fail",
        reasoning="judge fail",
        expected_source_ids=["good-id"],
        retrieval_candidate_source_ids=["good-id"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=["good-id"],
        v3_context={},
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict=None,
        movement_baseline_source=None,
    )

    assert diagnostics["answer_support_status"] == "unsupported_answer"
    assert diagnostics["failure_class"] == "unsupported_answer"


def test_public_case_movement_from_comparison_report_pairs(tmp_path):
    from memoryos_lite.public_case_movement import (
        load_public_case_movement,
        movement_status,
    )

    previous_report_path = tmp_path / "previous.json"
    previous_report_path.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case-pass-to-fail",
                    "verdict": "pass",
                },
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case-fail-to-pass",
                    "verdict": "fail",
                },
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case-unchanged-pass",
                    "verdict": "pass",
                },
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case-unchanged-fail",
                    "verdict": "fail",
                },
            ]
        ),
        encoding="utf-8",
    )

    comparison = load_public_case_movement([previous_report_path])

    assert comparison[("locomo", "memoryos_lite", "case-pass-to-fail")].verdict == "pass"
    assert movement_status("pass", "fail") == "pass_to_fail"
    assert movement_status("fail", "pass") == "fail_to_pass"
    assert movement_status("pass", "pass") == "unchanged_pass"
    assert movement_status("fail", "fail") == "unchanged_fail"
    assert movement_status("error", "fail") == "unchanged_fail"


def test_public_case_movement_missing_baseline_is_not_anti_demo_evidence():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    diagnostics = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="missing-baseline",
        memory_arch="v3",
        answer="MemoryOS Lite",
        answer_mode="projected",
        verdict="pass",
        reasoning="exact substring match",
        expected_source_ids=["D1:1"],
        retrieval_candidate_source_ids=["D1:1"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=["D1:1"],
        v3_context={},
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict=None,
        movement_baseline_source=None,
    )

    assert diagnostics["movement_status"] == "new_case_no_baseline"
    assert diagnostics["baseline_verdict"] is None
    assert any("missing baseline" in note for note in diagnostics["diagnostic_notes"])


def test_public_benchmark_movement_status_uses_comparison_report(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="case_move",
        answer="NeverReturnedExpectedToken",
    )
    previous_report_path = tmp_path / "previous.json"
    previous_report_path.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case_move_qa_001",
                    "verdict": "pass",
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase2-movement-wiring",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        comparison_report_paths=[previous_report_path],
    )
    report = results[0].to_report()

    assert report["verdict"] == "fail"
    assert report["movement_status"] == "pass_to_fail"
    assert report["case_diagnostics"]["baseline_verdict"] == "pass"
    assert report["case_diagnostics"]["movement_baseline_source"] == str(previous_report_path)


def test_public_benchmark_case_diagnostics_are_append_only(tmp_path):
    data_path = _write_single_locomo_case(tmp_path, sample_id="sample_append")
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase2-append-only",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )
    report = results[0].to_report()
    legacy_fields = {
        "benchmark",
        "baseline",
        "case_id",
        "answer",
        "verdict",
        "source_hit",
        "source_hit_at_k",
        "episode_candidate_message_ids",
        "planned_evidence_message_ids",
        "v3_diagnostics",
        "kernel_trace_events",
        "pass",
    }

    assert legacy_fields <= set(report)
    assert "case_diagnostics" in report
    assert report["failure_class"] == report["case_diagnostics"]["failure_class"]
    assert report["source_hit"] in {True, False, None}
    assert report["case_diagnostics"]["source_hit_semantics"] == "final_projection_source_overlap"


def test_public_benchmark_partial_and_final_reports_have_diagnostic_schema_parity(tmp_path):
    data_path = _write_single_locomo_case(tmp_path, sample_id="sample_schema")
    settings = Settings(data_dir=tmp_path / ".memoryos")

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase2-partial-schema",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    partial_path = settings.data_dir / "evals" / "phase2-partial-schema_locomo.partial.json"
    final_path = settings.data_dir / "evals" / "phase2-partial-schema_locomo.json"
    partial_rows = json.loads(partial_path.read_text(encoding="utf-8"))
    final_rows = json.loads(final_path.read_text(encoding="utf-8"))

    mirror_fields = {
        "case_diagnostics",
        "failure_class",
        "movement_status",
        "answer_support_status",
        "judge_status",
    }
    assert mirror_fields <= set(partial_rows[-1])
    assert mirror_fields <= set(final_rows[-1])
    assert set(partial_rows[-1]["case_diagnostics"]) == set(
        final_rows[-1]["case_diagnostics"]
    )
    for field in mirror_fields - {"case_diagnostics"}:
        assert partial_rows[-1][field] == partial_rows[-1]["case_diagnostics"][field]
        assert final_rows[-1][field] == final_rows[-1]["case_diagnostics"][field]


def test_public_benchmark_source_hit_is_not_retrieval_localization(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_source_semantics",
        text="The source-hit semantics marker is MemoryOS Lite.",
        question="What is the source-hit semantics marker?",
        answer="NeverReturnedExpectedToken",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase2-source-hit-semantics",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )
    report = results[0].to_report()

    diagnostics = report["case_diagnostics"]
    assert "retrieved_evidence_ids" in diagnostics
    assert "selected_context_ids" in diagnostics
    assert "rendered_evidence_ids" in diagnostics
    assert diagnostics["retrieved_evidence_ids"] != []
    assert report["source_hit"] is False or report["verdict"] == "fail"
    assert diagnostics["failure_class"] != "retrieval_miss"


def test_public_benchmark_reports_v3_context_diagnostics_by_default(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        filename="locomo_v3_default.json",
        sample_id="sample_v3_default",
        text="The default v3 recall marker is MemoryOS Lite.",
        question="What is the default v3 recall marker?",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-default-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["memory_arch"] == "v3"
    assert report["v3_diagnostics"]
    assert report["case_diagnostics"]["memory_arch"] == "v3"


def test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context(tmp_path):
    data_path = _write_single_locomo_case(tmp_path, sample_id="sample_v1")
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v1-fallback-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["memory_arch"] != "v3"
    assert report["v3_diagnostics"] == []
    assert report["case_diagnostics"]["memory_arch"] in {None, "v1"}


def test_public_benchmark_v3_core_diagnostics_are_append_only(tmp_path, monkeypatch):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_core_diag",
        text="Alice prefers rail travel.",
        question="What does Alice prefer?",
        answer="rail travel",
    )
    original_run_baseline = public_benchmarks._run_baseline

    def seeded_run_baseline(
        baseline,
        case,
        messages,
        service,
        settings,
        budget_override=None,
    ):
        original_build_context = service.build_context

        def build_context_with_core(
            session_id,
            task,
            budget=None,
            retrieval_query=None,
            include_global_core=False,
        ):
            if service.store.get_core_memory_block("core_public_profile") is None:
                service.store.create_core_memory_block(
                    CoreMemoryBlock(
                        id="core_public_profile",
                        label="profile",
                        description="Stable user facts",
                        value="Alice prefers rail travel.",
                        limit_tokens=100,
                        source_refs=[
                            SourceRef(source_type="message", source_id=messages[0].id)
                        ],
                        tags=["profile"],
                        metadata={"scope": "benchmark"},
                    )
                )
            return original_build_context(
                session_id,
                task,
                budget=budget,
                retrieval_query=retrieval_query,
                include_global_core=include_global_core,
            )

        service.build_context = build_context_with_core
        return original_run_baseline(
            baseline,
            case,
            messages,
            service,
            settings,
            budget_override=budget_override,
        )

    monkeypatch.setattr(public_benchmarks, "_run_baseline", seeded_run_baseline)
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-core-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert "v3_layer_counts" in report
    assert "v3_budget_decisions" in report
    assert "v3_diagnostics" in report
    assert report["v3_layer_counts"]["core"] >= 1
    core_diagnostics = [d for d in report["v3_diagnostics"] if d["layer"] == "core"]
    assert core_diagnostics
    assert core_diagnostics[0]["budget_tokens"] > 0
    assert core_diagnostics[0]["metadata"]["label"] == "profile"
    assert core_diagnostics[0]["metadata"]["tags"] == ["profile"]
    assert "planned_evidence_source_hit_at_5" in report


def test_public_benchmark_v3_archival_scope_diagnostics_are_append_only(
    tmp_path,
    monkeypatch,
):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_archive_diag",
        text="Alice uses the attached archive marker.",
        question="What archive marker does Alice use?",
        answer="attached archive marker",
    )
    original_run_baseline = public_benchmarks._run_baseline

    def seeded_run_baseline(
        baseline,
        case,
        messages,
        service,
        settings,
        budget_override=None,
    ):
        original_build_context = service.build_context

        def build_context_with_archives(
            session_id,
            task,
            budget=None,
            retrieval_query=None,
            include_global_core=False,
        ):
            if not service.store.list_archive_attachments(
                scope_type="session",
                scope_id=session_id,
            ):
                ref = SourceRef(
                    source_type="message",
                    source_id=messages[0].id,
                    session_id=session_id,
                )
                service.store.create_archival_passage(
                    ArchivalPassage(
                        id="apsg_public_attached",
                        archive_id="archive_public_attached",
                        text="Alice uses the attached archive marker.",
                        source_refs=[ref],
                    )
                )
                service.store.create_archival_passage(
                    ArchivalPassage(
                        id="apsg_public_excluded",
                        archive_id="archive_public_excluded",
                        text="Alice uses an excluded archive marker.",
                        source_refs=[ref],
                    )
                )
                service.store.create_archive_attachment(
                    ArchiveAttachment(
                        id="aatt_public_attached",
                        archive_id="archive_public_attached",
                        scope_type="session",
                        scope_id=session_id,
                        source_refs=[ref],
                    )
                )
            return original_build_context(
                session_id,
                task,
                budget=budget,
                retrieval_query=retrieval_query,
                include_global_core=include_global_core,
            )

        service.build_context = build_context_with_archives
        return original_run_baseline(
            baseline,
            case,
            messages,
            service,
            settings,
            budget_override=budget_override,
        )

    monkeypatch.setattr(public_benchmarks, "_run_baseline", seeded_run_baseline)
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-archival-scope-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    eligibility = report["case_diagnostics"]["archival_eligibility"]
    assert report["verdict"] == "pass"
    assert report["movement_status"] == "new_case_no_baseline"
    assert "v3_diagnostics" in report
    assert report["source_hit"] is True
    assert "apsg_public_excluded" not in report["retrieval_candidate_source_ids"]
    assert eligibility["eligible_archive_ids"] == ["archive_public_attached"]
    assert eligibility["selected_passage_ids"] == ["apsg_public_attached"]
    assert eligibility["scope_excluded_passage_ids"] == ["apsg_public_excluded"]
    assert eligibility["archival_scope_excluded"] == 1
    assert eligibility["archival_no_match"] == 0


def test_public_benchmark_kernel_trace_remains_default_off(tmp_path):
    data_path = _write_single_locomo_case(tmp_path, sample_id="sample_kernel_default")
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-kernel-default-off-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["kernel_trace_events"] == []
    assert report["case_diagnostics"]["kernel_trace_present"] is False


def test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled(tmp_path):
    data_path = tmp_path / "locomo_kernel.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_kernel",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The kernel marker is MemoryOS Lite.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the kernel marker?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-kernel-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["memory_arch"] == "v3"
    assert report["kernel_trace_events"] == [
        "kernel_step_started",
        "tool_policy_decision",
        "approval_pending",
        "kernel_step_completed",
        "kernel_step_started",
        "tool_policy_decision",
        "approval_granted",
        "tool_executed",
        "kernel_step_completed",
    ]
    assert report["case_diagnostics"]["kernel_trace_present"] is True
    assert report["case_diagnostics"]["failure_class"] in {
        "supported_cited_answer",
        "evidence_hit_answer_fail",
        "unsupported_answer",
        "judge_questionable",
        "retrieval_miss",
        "context_missing_evidence",
    }
