import json

from memoryos_lite.cli import PUBLIC_TABLE_COLUMNS, _public_table_rows
from memoryos_lite.config import Settings
from memoryos_lite.public_benchmarks import load_public_benchmark_cases, run_public_benchmark


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
