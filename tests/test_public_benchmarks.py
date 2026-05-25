import builtins
import importlib
import json

import pytest

import memoryos_lite.public_benchmarks as public_benchmarks
from memoryos_lite.cli import PUBLIC_TABLE_COLUMNS, _public_table_rows
from memoryos_lite.config import Settings
from memoryos_lite.evals import BaselineOutput
from memoryos_lite.public_benchmarks import load_public_benchmark_cases, run_public_benchmark
from memoryos_lite.public_maintenance_planner import (
    EvalGoldSidecar,
    ModelVisiblePlannerInput,
    build_maintenance_artifact,
)
from memoryos_lite.v3_contracts import (
    ArchivalPassage,
    ArchiveAttachment,
    CoreMemoryBlock,
    SourceRef,
)


@pytest.fixture(autouse=True)
def _disable_fastembed_for_public_benchmark_tests(monkeypatch):
    monkeypatch.setenv("MEMORYOS_EMBEDDING_PROVIDER", "none")


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


def test_public_benchmark_respects_explicit_embedding_provider_none(
    tmp_path, monkeypatch
):
    from memoryos_lite.retrieval.providers.fastembed_client import FastEmbedClient

    def fail_fastembed_init(self):
        raise AssertionError("FastEmbedClient should not be constructed")

    monkeypatch.setattr(FastEmbedClient, "__init__", fail_fastembed_init)
    data_path = _write_single_locomo_case(tmp_path)
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_embedding_provider="none",
    )

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-no-embedding-test",
        baselines=["sliding_window"],
        llm_answer=False,
        llm_judge=False,
    )

    assert len(results) == 1


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


def test_public_benchmark_projected_answer_cites_selected_evidence(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_cited_projection",
        text="The citation contract marker is MemoryOS Lite.",
        question="What is the citation contract marker?",
        answer="MemoryOS Lite",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="phase6-cited-projection-red",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    result = results[0]
    expected_source_id = "sample_cited_projection_qa_001:sample_cited_projection:D1:1"
    diagnostics = result.case_diagnostics
    assert expected_source_id in result.source_ids
    assert f"[{expected_source_id}]" in result.answer
    assert diagnostics["citation_contract_status"] == "supported_cited_answer"
    assert diagnostics["unsupported_citation_ids"] == []
    assert diagnostics["answer_support_status"] == "supported_cited_answer"


def test_public_case_diagnostics_flags_projected_unretrieved_citation():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    diagnostics = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="projected-unretrieved-citation",
        memory_arch="v3",
        answer="The answer cites unavailable evidence [msg_unselected].",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_selected"],
        retrieval_candidate_source_ids=["msg_selected"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=["msg_selected"],
        v3_context={},
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict=None,
        movement_baseline_source=None,
    )

    assert diagnostics["unsupported_citation_ids"] == ["msg_unselected"]
    assert diagnostics["citation_contract_status"] == "unsupported_citation"
    assert diagnostics["failure_class"] == "unsupported_answer"


def test_public_answerer_renders_structured_evidence_with_citation_contract(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            return type("FakeResponse", (), {"content": "MemoryOS Lite [msg_selected]"})()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "What did Alice choose?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="msg_selected",
                text="Alice chose MemoryOS Lite.",
                component="recall",
                source_ids=["source_msg_selected"],
                session_id="D1",
                date="2026-05-22",
            )
        ],
    )

    assert answer == "MemoryOS Lite [msg_selected]"
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "Allowed citation IDs: msg_selected" in prompt_text
    assert '"id": "msg_selected"' in prompt_text
    assert '"component": "recall"' in prompt_text
    assert '"session_id": "D1"' in prompt_text
    assert '"date": "2026-05-22"' in prompt_text
    assert "Alice chose MemoryOS Lite." in prompt_text
    assert "cite every factual claim with exact [id]" in prompt_text
    assert "Insufficient retrieved evidence to answer with source citations." in prompt_text


def test_public_answerer_normalizes_unique_short_locomo_citations_to_allowed_ids(
    tmp_path, monkeypatch
):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Melanie planned to go camping around June 2023 [D2:7], "
                        "with later camping evidence also available [D6:16]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "When was Melanie planning to go camping?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_007:conv-26:D2:7",
                text=(
                    "[1:14 pm on 25 May, 2023] Melanie: I am thinking about "
                    "going camping next month."
                ),
                component="recall",
                source_ids=["conv-26_qa_007:conv-26:D2:7"],
                session_id="D2",
                date="1:14 pm on 25 May, 2023",
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_007:conv-26:D6:16",
                text="[8:18 pm on 6 July, 2023] Melanie: Camping was fun.",
                component="recall",
                source_ids=["conv-26_qa_007:conv-26:D6:16"],
                session_id="D6",
                date="8:18 pm on 6 July, 2023",
            ),
        ],
    )

    assert "[conv-26_qa_007:conv-26:D2:7]" in answer
    assert "[conv-26_qa_007:conv-26:D6:16]" in answer
    assert "[D2:7]" not in answer
    assert "[D6:16]" not in answer


def test_public_answerer_normalized_locomo_citations_reach_result_diagnostics(
    tmp_path, monkeypatch
):
    full_id = "conv-26_qa_007:conv-26:D2:7"

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Melanie planned to go camping around June 2023 [D2:7]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )
    evidence = [
        public_benchmarks.AnswerEvidence(
            evidence_id=full_id,
            text=(
                "[1:14 pm on 25 May, 2023] Melanie: I am thinking about "
                "going camping next month."
            ),
            component="recall",
            source_ids=[full_id],
            session_id="D2",
            date="1:14 pm on 25 May, 2023",
        )
    ]

    answer = answerer.answer("When was Melanie planning to go camping?", evidence)

    public_case = public_benchmarks.PublicBenchmarkCase(
        benchmark="locomo",
        case=public_benchmarks.EvalCase(
            case_id="conv-26_qa_007",
            conversation=[
                public_benchmarks.MessageCreate(
                    role=public_benchmarks.Role.USER,
                    content="Melanie planned to go camping around June 2023.",
                )
            ],
            question="When was Melanie planning to go camping?",
            expected_facts=["June 2023"],
        ),
        messages=[],
        expected_answer="June 2023",
        expected_source_ids=[full_id],
        expected_session_ids=["D2"],
        source_sessions_by_id={full_id: "D2"},
    )
    output = BaselineOutput(
        answer="Melanie planned to go camping around June 2023.",
        context_tokens=12,
        sources={full_id: evidence[0].text},
        retrieval_candidate_source_ids=[full_id],
        memory_arch="v3",
        v3_final_context_trace=[
            {
                "component": "recall",
                "item_id": full_id,
                "source_ids": [full_id],
                "rendered_index": 1,
                "metadata": {
                    "benchmark_session_id": "D2",
                    "benchmark_date": "1:14 pm on 25 May, 2023",
                },
            }
        ],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": full_id,
                        "source_ids": [full_id],
                        "rendered_index": 1,
                        "included": True,
                        "dropped": False,
                    }
                ]
            }
        },
    )

    result = public_benchmarks._to_public_result(
        public_case,
        "memoryos_lite",
        answer,
        "llm",
        [full_id],
        "pass",
        "judge pass",
        ["June 2023"],
        [],
        output,
        latency_ms=1,
        answer_evidence=evidence,
        baseline_verdict="pass",
        movement_baseline_source="phase10.json",
    )

    diagnostics = result.case_diagnostics
    assert f"[{full_id}]" in result.answer
    assert "[D2:7]" not in result.answer
    assert diagnostics["cited_source_ids"] == [full_id]
    assert diagnostics["unsupported_citation_ids"] == []
    assert diagnostics["citation_contract_status"] == "supported_cited_answer"
    assert diagnostics["failure_class"] == "supported_cited_answer"
    assert diagnostics["evidence_handoff"]["failure_boundary"] == "none"


def test_public_answerer_brackets_parenthetical_allowed_citation_ids(
    tmp_path, monkeypatch
):
    source_a = "8ebdbe50:answer_8ad8a34f:003"
    source_b = "8ebdbe50:answer_8ad8a34f:009"

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "You completed a certification in Data Science last month "
                        f"({source_a}, {source_b})."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "What certification did I complete last month?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id=source_a,
                text=(
                    "I need to add my latest certification in Data Science, "
                    "which I completed last month, to my profile."
                ),
                component="recall",
                source_ids=[source_a],
                session_id="answer_8ad8a34f",
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id=source_b,
                text=(
                    "I need to update my LinkedIn profile to reflect my latest "
                    "certification in Data Science, which I completed last month."
                ),
                component="recall",
                source_ids=[source_b],
                session_id="answer_8ad8a34f",
            ),
        ],
    )

    assert f"[{source_a}]" in answer
    assert f"[{source_b}]" in answer
    assert f"({source_a}" not in answer


def test_public_answerer_guides_relative_temporal_evidence_before_refusal(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "relative temporal phrases" not in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Caroline met up with them last week relative to "
                        "9 June 2023 [conv-26_qa_010:conv-26:D3:11]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "When did Caroline meet up with her friends, family, and mentors?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_010:conv-26:D3:11",
                text=(
                    "[7:55 pm on 9 June, 2023] Caroline: Thanks, Mel! "
                    "My friends, family and mentors are my rocks. Here's a pic "
                    "from when we met up last week!"
                ),
                component="recall",
                source_ids=["conv-26_qa_010:conv-26:D3:11"],
                session_id="D3",
                date="7:55 pm on 9 June, 2023",
            )
        ],
    )

    assert "last week relative to 9 June 2023" in answer
    assert "[conv-26_qa_010:conv-26:D3:11]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "relative temporal phrases" in prompt_text
    assert "last week" in prompt_text
    assert "9 June, 2023" in prompt_text


def test_public_answerer_guides_supported_partial_evidence_before_refusal(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "supported partial answer" not in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "The retrieved evidence supports that Caroline is looking into "
                        "counseling and mental health as a career, but it does not directly "
                        "address writing [conv-26_qa_028:conv-26:D4:11]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Caroline pursue writing as a career option?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D4:11",
                text=(
                    "[10:37 am on 27 June, 2023] Caroline: Lately, I've been "
                    "looking into counseling and mental health as a career. I want "
                    "to help people who have gone through the same things as me."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D4:11"],
                session_id="D4",
                date="10:37 am on 27 June, 2023",
            )
        ],
    )

    assert "counseling and mental health as a career" in answer
    assert "does not directly address writing" in answer
    assert "[conv-26_qa_028:conv-26:D4:11]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "supported partial answer" in prompt_text
    assert "reserve the exact refusal" in prompt_text


def test_public_answerer_guides_yes_no_inference_before_refusal(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "yes/no preference or career questions" not in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Likely no: Caroline is pursuing counseling and mental health "
                        "work, while reading is described as a motivating interest "
                        "[conv-26_qa_028:conv-26:D7:5] "
                        "[conv-26_qa_028:conv-26:D7:9]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Caroline pursue writing as a career option?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:5",
                text=(
                    "Caroline is still looking into counseling and mental health "
                    "jobs because she wants people to have someone to talk to."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:5"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:9",
                text=(
                    "Caroline says books guide and motivate her and that reading is "
                    "part of her journey."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:9"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
        ],
    )

    assert "Likely no" in answer
    assert "[conv-26_qa_028:conv-26:D7:5]" in answer
    assert "[conv-26_qa_028:conv-26:D7:9]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "yes/no preference or career questions" in prompt_text
    assert "answer likely yes or likely no" in prompt_text
    assert "pursue option X" in prompt_text
    assert "different option Y" in prompt_text


def test_public_answerer_guides_complete_qualified_fact_answers(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "preserve explicit qualifiers" not in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "I attended the University of Melbourne "
                            "[3b6f954b:answer_94030872:009]."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "I attended the University of Melbourne in Australia "
                        "[3b6f954b:answer_94030872:009]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Where did I attend for my study abroad program?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="3b6f954b:answer_94030872:009",
                text=(
                    "I attended the University of Melbourne in Australia "
                    "for my study abroad program."
                ),
                component="recall",
                source_ids=["3b6f954b:answer_94030872:009"],
                session_id="answer_94030872",
                date="2023/05/23 (Tue) 10:24",
            )
        ],
    )

    assert "University of Melbourne in Australia" in answer
    assert "[3b6f954b:answer_94030872:009]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "preserve explicit qualifiers" in prompt_text
    assert "countries" in prompt_text


def test_public_answerer_omits_internal_diagnostics_metadata_from_prompt(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "rank_features" in prompt_text or "packet_member_message_ids" in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Likely no: Caroline is pursuing counseling and mental health "
                        "work, while reading is a motivating interest "
                        "[conv-26_qa_028:conv-26:D7:5] [conv-26_qa_028:conv-26:D7:9]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Caroline pursue writing as a career option?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:5",
                text=(
                    "Caroline is looking into counseling and mental health jobs "
                    "because she wants people to have someone to talk to."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:5"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
                metadata={
                    "rank_features": {"token_overlap": 2.0},
                    "packet_member_message_ids": ["conv-26_qa_028:conv-26:D7:5"],
                },
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:9",
                text=(
                    "Caroline says books guide and motivate her and that reading "
                    "is part of her journey."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:9"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
                metadata={
                    "rank_features": {"token_overlap": 1.0},
                    "packet_member_message_ids": ["conv-26_qa_028:conv-26:D7:9"],
                },
            ),
        ],
    )

    assert "Likely no" in answer
    assert "[conv-26_qa_028:conv-26:D7:5]" in answer
    assert "[conv-26_qa_028:conv-26:D7:9]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "rank_features" not in prompt_text
    assert "packet_member_message_ids" not in prompt_text


def test_public_answerer_preserves_explicit_location_qualifier_without_metadata_noise(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "rank_features" in prompt_text or "packet_member_message_ids" in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "I attended the University of Melbourne in Australia "
                        "[3b6f954b:answer_94030872:009]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Where did I attend for my study abroad program?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="3b6f954b:answer_94030872:009",
                text=(
                    "I attended the University of Melbourne in Australia "
                    "for my study abroad program."
                ),
                component="recall",
                source_ids=["3b6f954b:answer_94030872:009"],
                session_id="answer_94030872",
                date="2023/05/23 (Tue) 10:24",
                metadata={
                    "rank_features": {"token_overlap": 5.0},
                    "packet_member_message_ids": ["3b6f954b:answer_94030872:009"],
                },
            )
        ],
    )

    assert "University of Melbourne in Australia" in answer
    assert "[3b6f954b:answer_94030872:009]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "rank_features" not in prompt_text
    assert "packet_member_message_ids" not in prompt_text


def test_public_answerer_repairs_missing_location_qualifier_after_retry(
    tmp_path, monkeypatch
):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "I attended my study abroad program at the University of "
                        "Melbourne [3b6f954b:answer_94030872:009]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Where did I attend for my study abroad program?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="3b6f954b:answer_94030872:009",
                text=(
                    "I attended the University of Melbourne in Australia "
                    "for my study abroad program."
                ),
                component="recall",
                source_ids=["3b6f954b:answer_94030872:009"],
                session_id="answer_94030872",
                date="2023/05/23 (Tue) 10:24",
            )
        ],
    )

    assert "University of Melbourne in Australia" in answer
    assert "[3b6f954b:answer_94030872:009]" in answer


def test_public_answerer_retries_when_answer_omits_explicit_location_qualifier(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            if self.calls == 1:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Based on the evidence, you attended the University of "
                            "Melbourne for your study abroad program "
                            "[3b6f954b:answer_94030872:009]."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "You attended the University of Melbourne in Australia "
                        "for your study abroad program "
                        "[3b6f954b:answer_94030872:009]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Where did I attend for my study abroad program?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="3b6f954b:answer_94030872:009",
                text=(
                    "I attended the University of Melbourne in Australia "
                    "for my study abroad program."
                ),
                component="recall",
                source_ids=["3b6f954b:answer_94030872:009"],
                session_id="answer_94030872",
                date="2023/05/23 (Tue) 10:24",
            )
        ],
    )

    assert "University of Melbourne in Australia" in answer
    assert "[3b6f954b:answer_94030872:009]" in answer
    assert len(captured_prompts) == 2
    assert "omitted explicit qualifiers" in captured_prompts[1]
    assert "Australia" in captured_prompts[1]


def test_public_answerer_retries_missing_qualifiers_after_refusal(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            if self.calls in (1, 2):
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "You attended the University of Melbourne in Australia "
                        "for your study abroad program "
                        "[3b6f954b:answer_94030872:009]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Where did I attend for my study abroad program?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="3b6f954b:answer_94030872:009",
                text=(
                    "I attended the University of Melbourne in Australia "
                    "for my study abroad program."
                ),
                component="recall",
                source_ids=["3b6f954b:answer_94030872:009"],
                session_id="answer_94030872",
                date="2023/05/23 (Tue) 10:24",
            )
        ],
    )

    assert answer == (
        "You attended the University of Melbourne in Australia "
        "for your study abroad program [3b6f954b:answer_94030872:009]."
    )
    assert len(captured_prompts) == 3
    assert "omitted explicit qualifiers" in captured_prompts[2]
    assert "Australia" in captured_prompts[2]


def test_public_answerer_guides_relevant_evidence_over_refusal(
    tmp_path, monkeypatch
):
    captured_messages = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_messages.extend(messages)
            prompt_text = "\n".join(str(message.content) for message in messages)
            if "If any retrieved evidence is relevant" not in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Likely no: Caroline is looking into counseling and mental "
                        "health work, while books are described as motivation rather "
                        "than a writing career [conv-26_qa_028:conv-26:D7:5] "
                        "[conv-26_qa_028:conv-26:D7:9]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Caroline pursue writing as a career option?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:5",
                text=(
                    "Caroline is looking into counseling and mental health jobs "
                    "because she wants people to have someone to talk to."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:5"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:9",
                text=(
                    "Caroline says the book she read motivates her and that "
                    "reading is part of her journey."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:9"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
        ],
    )

    assert "Likely no" in answer
    assert "[conv-26_qa_028:conv-26:D7:5]" in answer
    assert "[conv-26_qa_028:conv-26:D7:9]" in answer
    prompt_text = "\n".join(str(message.content) for message in captured_messages)
    assert "If any retrieved evidence is relevant" in prompt_text
    assert "do not use the exact refusal" in prompt_text


def test_public_answerer_retries_exact_refusal_when_evidence_exists(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            if self.calls == 1:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Likely no: Caroline is looking into counseling and mental "
                        "health work, while reading is described as motivation rather "
                        "than a writing career [conv-26_qa_028:conv-26:D7:5] "
                        "[conv-26_qa_028:conv-26:D7:9]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Caroline pursue writing as a career option?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:5",
                text=(
                    "Caroline is looking into counseling and mental health jobs "
                    "because she wants people to have someone to talk to."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:5"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:9",
                text=(
                    "Caroline says the book she read motivates her and that "
                    "reading is part of her journey."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:9"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
        ],
    )

    assert "Likely no" in answer
    assert "[conv-26_qa_028:conv-26:D7:5]" in answer
    assert "[conv-26_qa_028:conv-26:D7:9]" in answer
    assert len(captured_prompts) == 2
    assert "This is a retry after an overly cautious draft" in captured_prompts[1]
    assert "Do not return the exact refusal" in captured_prompts[1]
    assert "Do not require the exact option text to appear" in captured_prompts[1]


def test_public_answerer_retry_prompt_drops_exact_refusal_clause(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Insufficient retrieved evidence to answer with source citations."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answerer.answer(
        "When did I volunteer at the local animal shelter's fundraising dinner?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="58ef2f1c:answer_59547700:009",
                text="I volunteered at the fundraising dinner on February 14th.",
                component="recall",
                source_ids=["58ef2f1c:answer_59547700:009"],
                session_id="answer_59547700",
                date="2023/04/02 (Sun) 22:15",
            )
        ],
    )

    assert len(captured_prompts) == 2
    assert "This is a retry after an overly cautious draft" in captured_prompts[1]
    assert "Do not return the exact refusal" in captured_prompts[1]
    assert (
        "answer exactly: Insufficient retrieved evidence to answer with source citations."
        not in captured_prompts[1]
    )
    assert "The provided evidence was selected as relevant" in captured_prompts[1]


def test_public_answerer_does_not_synthesize_likely_no_after_repeated_refusal(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Insufficient retrieved evidence to answer with source citations."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Dana accept the promotion?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="msg_promotion_interest",
                text=(
                    "Dana said the promotion aligns with her long-term goals "
                    "and she is excited about the chance to lead the team."
                ),
                component="recall",
                source_ids=["msg_promotion_interest"],
                session_id="D1",
                date="2026-05-23",
            ),
        ],
    )

    assert answer == "Insufficient retrieved evidence to answer with source citations."
    assert len(captured_prompts) == 2
    assert "This is a retry after an overly cautious draft" in captured_prompts[1]


def test_public_answerer_repairs_missing_preference_support_after_supported_answer(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            captured_prompts.append("\n".join(str(message.content) for message in messages))
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Likely no: Caroline is pursuing counseling and mental "
                        "health work, while there is no indication that she is "
                        "pursuing writing as a career [conv-26_qa_028:conv-26:D7:5] "
                        "[conv-26_qa_028:conv-26:D7:9]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "Would Caroline pursue writing as a career option?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:5",
                text=(
                    "Caroline is looking into counseling and mental health jobs "
                    "because she wants people to have someone to talk to."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:5"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_028:conv-26:D7:9",
                text=(
                    "Caroline says the book she read motivates her and that "
                    "reading is part of her journey."
                ),
                component="recall",
                source_ids=["conv-26_qa_028:conv-26:D7:9"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            ),
        ],
    )

    assert "Likely no" in answer
    assert "reading is part of her journey" in answer
    assert len(captured_prompts) == 1


def test_public_answerer_grounds_last_year_temporal_inference_from_evidence_date(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            if self.calls == 1:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            if (
                "last year" in prompt_text
                and "evidence date metadata" in prompt_text
                and "explicit calendar year" in prompt_text
            ):
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": "2022 [conv-26_qa_027:conv-26:D7:8]"
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Insufficient retrieved evidence to answer with source citations."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "When did Melanie read the book 'Nothing is Impossible'?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="conv-26_qa_027:conv-26:D7:8",
                text=(
                    "This book I read last year reminds me to always pursue my "
                    "dreams, just like you are doing!"
                ),
                component="recall",
                source_ids=["conv-26_qa_027:conv-26:D7:8"],
                session_id="D7",
                date="4:33 pm on 12 July, 2023",
            )
        ],
    )

    assert answer.startswith("2022")
    assert "[conv-26_qa_027:conv-26:D7:8]" in answer
    assert len(captured_prompts) == 2
    assert "last year" in captured_prompts[1]
    assert "evidence date metadata" in captured_prompts[1]
    assert "explicit calendar year" in captured_prompts[1]


def test_public_answerer_recovers_temporal_holiday_answer_after_retry(
    tmp_path, monkeypatch
):
    captured_prompts = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            prompt_text = "\n".join(str(message.content) for message in messages)
            captured_prompts.append(prompt_text)
            if self.calls == 1:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "Insufficient retrieved evidence to answer with source citations."
                        )
                    },
                )()
            if "holiday names" in prompt_text and "month names" in prompt_text:
                return type(
                    "FakeResponse",
                    (),
                    {
                        "content": (
                            "You volunteered on February 14th "
                            "[58ef2f1c:answer_59547700:009]."
                        )
                    },
                )()
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "Insufficient retrieved evidence to answer with source citations."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "When did I volunteer at the local animal shelter's fundraising dinner?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="58ef2f1c:answer_59547700:009",
                text=(
                    'I volunteered in LA at the "Love is in the Air" fundraising '
                    "dinner back on Valentine's Day."
                ),
                component="recall",
                source_ids=["58ef2f1c:answer_59547700:009"],
                session_id="answer_59547700",
                date="2023/04/02 (Sun) 22:15",
            )
        ],
    )

    assert answer == "You volunteered on February 14th [58ef2f1c:answer_59547700:009]."
    assert len(captured_prompts) == 2
    assert "holiday names" in captured_prompts[1]
    assert "month names" in captured_prompts[1]
    assert "Valentine's Day" in captured_prompts[1]


def test_public_answerer_does_not_append_location_qualifiers_to_temporal_answer(
    tmp_path, monkeypatch
):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return type(
                "FakeResponse",
                (),
                {
                    "content": (
                        "You volunteered on Valentine's Day "
                        "[58ef2f1c:answer_59547700:009]."
                    )
                },
            )()

    monkeypatch.setattr(public_benchmarks, "ChatOpenAI", FakeChatOpenAI)
    answerer = public_benchmarks.PublicAnswerer(
        Settings(data_dir=tmp_path / ".memoryos", openai_api_key="test-key")
    )

    answer = answerer.answer(
        "When did I volunteer at the local animal shelter's fundraising dinner?",
        [
            public_benchmarks.AnswerEvidence(
                evidence_id="58ef2f1c:answer_59547700:009",
                text=(
                    'I volunteered in LA at the "Love is in the Air" fundraising '
                    "dinner back on Valentine's Day."
                ),
                component="recall",
                source_ids=["58ef2f1c:answer_59547700:009"],
                session_id="answer_59547700",
                date="2023/04/02 (Sun) 22:15",
            )
        ],
    )

    assert answer == (
        "You volunteered on Valentine's Day [58ef2f1c:answer_59547700:009]."
    )


def test_answer_evidence_preserves_final_context_render_order():
    output = BaselineOutput(
        answer="answer",
        context_tokens=10,
        sources={
            "source_z_first": "first rendered evidence",
            "source_a_second": "second rendered evidence",
        },
        v3_final_context_trace=[
            {
                "component": "recall",
                "source_ids": ["source_z_first"],
                "rendered_index": 1,
                "metadata": {"benchmark_session_id": "D1"},
            },
            {
                "component": "recall",
                "source_ids": ["source_a_second"],
                "rendered_index": 2,
                "metadata": {"benchmark_session_id": "D1"},
            },
        ],
    )

    evidence = public_benchmarks._answer_evidence_from_output(output)

    assert [item.evidence_id for item in evidence] == [
        "source_z_first",
        "source_a_second",
    ]


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


def test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice(
    tmp_path,
):
    data_path = tmp_path / "locomo_v3_packets.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_v3_packets",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Caroline",
                                "dia_id": "D1:1",
                                "text": "I am weighing psychology classes.",
                            },
                            {
                                "speaker": "Caroline",
                                "dia_id": "D1:2",
                                "text": "Counseling could help people.",
                            },
                        ],
                        "session_2": [
                            {
                                "speaker": "Caroline",
                                "dia_id": "D2:1",
                                "text": "Education fields career options are distracting.",
                            }
                        ],
                        "session_3": [
                            {
                                "speaker": "Caroline",
                                "dia_id": "D3:1",
                                "text": "Education fields career planning is distracting.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What fields would Caroline pursue in education?",
                            "answer": "psychology and counseling",
                            "evidence": ["D1:1", "D1:2"],
                        }
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
        run_id="public-v3-packet-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    packets = report["v3_context"]["metadata"]["recall_evidence_packets"]
    assert packets
    assert any(packet["packet_session_id"] == "D1" for packet in packets)
    assert report["case_diagnostics"]["retrieved_evidence_ids"]
    assert (
        report["case_diagnostics"]["source_hit_semantics"]
        == "final_projection_source_overlap"
    )
    assert report["kernel_trace_events"] == []


def test_public_benchmark_reports_v3_component_accounting_append_only(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        filename="locomo_v3_accounting.json",
        sample_id="sample_v3_accounting",
        text="The v3 accounting marker is MemoryOS Lite.",
        question="What is the v3 accounting marker?",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-accounting-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert "v3_component_accounting" in report
    assert "v3_final_context_trace" in report
    assert "v3_component_token_totals" in report
    assert "v3_component_drop_counts" in report
    assert report["v3_component_accounting"]
    assert report["v3_final_context_trace"]
    assert report["case_diagnostics"]["final_context_trace_source_ids"]
    assert "v3_diagnostics" in report


def test_public_case_diagnostics_uses_v3_final_context_trace_source_refs():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    diagnostics = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="final-trace-source-refs",
        memory_arch="v3",
        answer="NeverReturnedExpectedToken",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_expected"],
        retrieval_candidate_source_ids=["msg_expected"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=["msg_expected"],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": "recall_item",
                        "source_refs": [
                            {"source_type": "message", "source_id": "msg_expected"}
                        ],
                        "included": True,
                        "dropped": False,
                    }
                ],
                "component_drop_counts": {"recall": 0},
                "locomo_neighbor_diagnostics": [],
            }
        },
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict=None,
        movement_baseline_source=None,
    )

    assert diagnostics["selected_context_status"] == "evidence_selected"
    assert diagnostics["final_context_trace_source_ids"] == ["msg_expected"]
    assert diagnostics["selected_context_overlap_ids"] == ["msg_expected"]


def test_public_case_diagnostics_does_not_select_dropped_v3_diagnostics():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    diagnostics = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="dropped-v3-diagnostic",
        memory_arch="v3",
        answer="NeverReturnedExpectedToken",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_dropped"],
        retrieval_candidate_source_ids=["msg_dropped"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=[],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": "msg_dropped",
                        "source_ids": ["msg_dropped"],
                        "source_refs": [
                            {"source_type": "message", "source_id": "msg_dropped"}
                        ],
                        "included": False,
                        "dropped": True,
                    }
                ],
            }
        },
        v3_diagnostics=[
            {
                "layer": "recall",
                "event_type": "budget",
                "item_id": "msg_dropped",
                "source_refs": [
                    {"source_type": "message", "source_id": "msg_dropped"}
                ],
                "included": False,
                "dropped": True,
            }
        ],
        kernel_trace_events=[],
        baseline_verdict=None,
        movement_baseline_source=None,
    )

    assert diagnostics["retrieval_status"] == "evidence_retrieved"
    assert diagnostics["selected_context_status"] == "evidence_missing"
    assert diagnostics["selected_context_overlap_ids"] == []
    assert diagnostics["final_context_trace_source_ids"] == []


def test_public_case_diagnostics_splits_selected_and_render_handoff_drops():
    from memoryos_lite.public_case_diagnostics import build_case_diagnostics

    selected_drop = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="selected-drop-demo",
        memory_arch="v3",
        answer="NeverReturnedExpectedToken",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_expected"],
        retrieval_candidate_source_ids=["msg_expected"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=[],
        v3_context={"metadata": {"final_context_trace": []}},
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict="fail",
        movement_baseline_source="previous.json",
    )

    assert selected_drop["retrieval_status"] == "evidence_retrieved"
    assert selected_drop["evidence_handoff"]["failure_boundary"] == "selected_drop"
    assert selected_drop["failure_class"] == "evidence_retrieved_not_selected"

    render_drop = build_case_diagnostics(
        benchmark="locomo",
        baseline="memoryos_lite",
        case_id="render-drop-demo",
        memory_arch="v3",
        answer="NeverReturnedExpectedToken",
        answer_mode="projected",
        verdict="fail",
        reasoning="exact substring match",
        expected_source_ids=["msg_expected"],
        retrieval_candidate_source_ids=["msg_expected"],
        episode_candidate_message_ids=[],
        planned_evidence_message_ids=[],
        source_ids=[],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": "msg_expected",
                        "source_ids": ["msg_expected"],
                        "source_refs": [
                            {"source_type": "message", "source_id": "msg_expected"}
                        ],
                        "included": True,
                        "dropped": False,
                    }
                ]
            }
        },
        v3_diagnostics=[],
        kernel_trace_events=[],
        baseline_verdict="fail",
        movement_baseline_source="previous.json",
    )

    assert render_drop["selected_context_status"] == "evidence_selected"
    assert render_drop["rendered_context_status"] == "evidence_missing"
    assert render_drop["evidence_handoff"]["failure_boundary"] == "render_drop"
    assert render_drop["failure_class"] == "evidence_selected_not_rendered"


def test_public_result_reports_answer_evidence_handoff_metadata():
    from memoryos_lite.evals import BaselineOutput
    from memoryos_lite.public_benchmarks import (
        PublicBenchmarkCase,
        _answer_evidence_from_output,
        _to_public_result,
    )
    from memoryos_lite.schemas import EvalCase

    output = BaselineOutput(
        answer="NeverReturnedExpectedToken",
        context_tokens=7,
        sources={"msg_expected": "[D5] expected rendered evidence"},
        retrieval_candidate_source_ids=["msg_expected"],
        memory_arch="v3",
        v3_final_context_trace=[
            {
                "component": "recall",
                "item_id": "recall_item",
                "source_ids": ["msg_expected"],
                "rendered_index": 3,
                "estimated_tokens": 7,
                "metadata": {
                    "benchmark_session_id": "D5",
                    "benchmark_date": "2023-05-08",
                },
            }
        ],
        v3_context={
            "metadata": {
                "final_context_trace": [
                    {
                        "component": "recall",
                        "item_id": "recall_item",
                        "source_ids": ["msg_expected"],
                        "rendered_index": 3,
                        "estimated_tokens": 7,
                        "metadata": {
                            "benchmark_session_id": "D5",
                            "benchmark_date": "2023-05-08",
                        },
                        "included": True,
                        "dropped": False,
                    }
                ]
            }
        },
    )
    answer_evidence = _answer_evidence_from_output(output)
    public_case = PublicBenchmarkCase(
        benchmark="locomo",
        case=EvalCase(
            case_id="answer-evidence-handoff",
            conversation=[],
            question="What is the marker?",
            expected_facts=["ExpectedToken"],
        ),
        messages=[],
        expected_answer="ExpectedToken",
        expected_source_ids=["msg_expected"],
        expected_session_ids=["D5"],
        source_sessions_by_id={"msg_expected": "D5"},
    )

    result = _to_public_result(
        public_case,
        "memoryos_lite",
        "NeverReturnedExpectedToken",
        "llm",
        ["msg_expected"],
        "fail",
        "judge fail",
        [],
        ["ExpectedToken"],
        output,
        latency_ms=1,
        answer_evidence=answer_evidence,
        baseline_verdict="fail",
        movement_baseline_source="previous.json",
    )
    report = result.to_report()

    handoff = report["case_diagnostics"]["evidence_handoff"]
    assert handoff["answer_evidence_ids"] == ["msg_expected"]
    assert handoff["answer_evidence_overlap_ids"] == ["msg_expected"]
    assert handoff["stage_status"]["answer_evidence"] == "evidence_in_answer_evidence"
    assert report["answer_evidence"][0]["session_id"] == "D5"
    assert report["answer_evidence"][0]["date"] == "2023-05-08"
    assert report["answer_evidence"][0]["rendered_index"] == 3


def test_public_benchmark_reports_locomo_neighbor_diagnostics(tmp_path):
    data_path = tmp_path / "locomo_neighbor.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_neighbor",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "Alice set up the picnic plan yesterday.",
                            },
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:2",
                                "text": "The queried neighbor marker is MemoryOS Lite.",
                            },
                        ],
                        "session_2": [
                            {
                                "speaker": "Bob",
                                "dia_id": "D2:1",
                                "text": "Adjacent distractor should stay out of D1 neighbor trace.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What is the queried neighbor marker?",
                            "answer": "MemoryOS Lite",
                            "evidence": ["D1:2"],
                        }
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
        run_id="public-locomo-neighbor-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    diagnostics = report["locomo_neighbor_diagnostics"]
    assert diagnostics
    assert any(
        str(row["metadata"].get("neighbor_of") or "").endswith("D1:2")
        and row["metadata"].get("benchmark_session_id") == "D1"
        for row in diagnostics
    )
    neighbor_rows = [row for row in diagnostics if row["metadata"].get("neighbor_of")]
    assert all(row["metadata"].get("benchmark_session_id") != "D2" for row in neighbor_rows)


def test_public_benchmark_v3_preserves_locomo_neighbor_sources_for_answer_evidence(
    tmp_path,
):
    distractor_sessions = {
        f"session_{index}": [
            {
                "speaker": "Caroline",
                "dia_id": f"D{index}:1",
                "text": (
                    "Caroline considered writing as a career option in an unrelated "
                    f"planning note {index}."
                ),
            }
        ]
        for index in range(1, 7)
    }
    data_path = tmp_path / "locomo_neighbor_source_preservation.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "sample_neighbor_source",
                    "conversation": {
                        **distractor_sessions,
                        "session_7_date_time": "1:56 pm on 8 May, 2023",
                        "session_7": [
                            {
                                "speaker": "Caroline",
                                "dia_id": "D7:1",
                                "text": "I want to help make a difference.",
                            },
                            {
                                "speaker": "Melanie",
                                "dia_id": "D7:2",
                                "text": "What is your plan to pitch in?",
                            },
                            {
                                "speaker": "Caroline",
                                "dia_id": "D7:3",
                                "text": "I am still comparing next steps.",
                            },
                            {
                                "speaker": "Melanie",
                                "dia_id": "D7:4",
                                "text": "What kind of work are you considering?",
                            },
                            {
                                "speaker": "Caroline",
                                "dia_id": "D7:5",
                                "text": (
                                    "I'm still looking into counseling and mental health "
                                    "jobs. I want people to have someone to talk to."
                                ),
                            },
                            {
                                "speaker": "Melanie",
                                "dia_id": "D7:6",
                                "text": "What keeps pushing you forward with that?",
                            },
                            {
                                "speaker": "Caroline",
                                "dia_id": "D7:7",
                                "text": (
                                    "Support helped my mental health. So I started looking "
                                    "into counseling and mental health career options."
                                ),
                            },
                            {
                                "speaker": "Melanie",
                                "dia_id": "D7:8",
                                "text": (
                                    "This book reminds me to pursue dreams, just like you "
                                    "are doing."
                                ),
                            },
                            {
                                "speaker": "Caroline",
                                "dia_id": "D7:9",
                                "text": (
                                    "Books guide me, motivate me, and help me discover who "
                                    "I am. Reading is part of my journey."
                                ),
                            },
                        ],
                    },
                    "qa": [
                        {
                            "question": "Would Caroline pursue writing as a career option?",
                            "answer": (
                                "Likely no; though she likes reading, she wants to be a "
                                "counselor"
                            ),
                            "evidence": ["D7:5", "D7:9"],
                        }
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
        run_id="phase6-locomo-neighbor-source-preservation",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    expected_sources = {
        "sample_neighbor_source_qa_001:sample_neighbor_source:D7:5",
        "sample_neighbor_source_qa_001:sample_neighbor_source:D7:9",
    }
    diagnostics = report["case_diagnostics"]

    assert expected_sources <= set(report["source_ids"])
    assert expected_sources <= set(diagnostics["rendered_evidence_ids"])
    assert diagnostics["rendered_context_status"] == "evidence_rendered"
    assert report["source_hit"] is True
    neighbor_rows = [
        row
        for row in report["locomo_neighbor_diagnostics"]
        if row["metadata"].get("neighbor_of")
    ]
    assert expected_sources <= {row["item_id"] for row in neighbor_rows}
    assert {
        row["metadata"].get("benchmark_session_id") for row in neighbor_rows
    } == {"D7"}


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
        build_public_case_movement_summary,
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
    assert movement_status("pass", "error") == "pass_to_fail"
    assert movement_status("fail", "pass") == "fail_to_pass"
    assert movement_status("pass", "pass") == "unchanged_pass"
    assert movement_status("fail", "fail") == "unchanged_fail"
    assert movement_status("error", "fail") == "unchanged_fail"

    summary = build_public_case_movement_summary(
        [
            {
                "case_id": "case-new-failure-class",
                "movement_status": "unchanged_fail",
                "failure_class": "answer_not_supported_by_judge",
                "case_diagnostics": {
                    "evidence_handoff": {
                        "failure_boundary": "custom_boundary",
                    }
                },
            }
        ]
    )
    assert summary["failure_classes"]["answer_not_supported_by_judge"] == [
        "case-new-failure-class"
    ]
    assert summary["failure_boundaries"]["custom_boundary"] == [
        "case-new-failure-class"
    ]


def test_public_case_movement_summary_reports_source_metric_movement_and_omits_missing_values():
    from memoryos_lite.public_case_movement import build_public_case_movement_summary

    summary = build_public_case_movement_summary(
        [
            {
                "case_id": "metric-improved",
                "source_hit": True,
                "case_diagnostics": {
                    "baseline_source_metrics": {"source_hit": False}
                },
            },
            {
                "case_id": "metric-regressed",
                "source_hit": False,
                "case_diagnostics": {
                    "baseline_source_metrics": {"source_hit": True}
                },
            },
            {
                "case_id": "metric-unchanged-hit",
                "source_hit": True,
                "case_diagnostics": {
                    "baseline_source_metrics": {"source_hit": True}
                },
            },
            {
                "case_id": "metric-unchanged-miss",
                "source_hit": False,
                "case_diagnostics": {
                    "baseline_source_metrics": {"source_hit": False}
                },
            },
            {
                "case_id": "metric-missing-current",
                "source_hit": None,
                "case_diagnostics": {
                    "baseline_source_metrics": {"source_hit": False}
                },
            },
            {
                "case_id": "metric-missing-baseline",
                "source_hit": True,
                "case_diagnostics": {"baseline_source_metrics": {}},
            },
        ]
    )

    source_hit_movement = summary["source_metric_movement"]["source_hit"]
    assert source_hit_movement == {
        "improved": ["metric-improved"],
        "regressed": ["metric-regressed"],
        "unchanged_hit": ["metric-unchanged-hit"],
        "unchanged_miss": ["metric-unchanged-miss"],
    }
    assert summary["counts"]["source_metric_movement"]["source_hit"] == {
        "improved": 1,
        "regressed": 1,
        "unchanged_hit": 1,
        "unchanged_miss": 1,
    }
    assert "missing baseline or current metric values are omitted" in summary[
        "diagnostic_note"
    ]


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


def test_public_benchmark_writes_case_movement_summary_for_comparison_report(tmp_path):
    data_path = tmp_path / "locomo_movement_summary.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "move_fail_to_pass",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The movement summary marker is emerald.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What color is the movement summary marker?",
                            "answer": "emerald",
                            "evidence": ["D1:1"],
                        }
                    ],
                },
                {
                    "sample_id": "move_pass_to_fail",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:1",
                                "text": "The movement summary distractor is slate.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What color is the missing movement marker?",
                            "answer": "violet",
                            "evidence": ["D9:9"],
                        }
                    ],
                },
                {
                    "sample_id": "move_new_case",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Casey",
                                "dia_id": "D1:1",
                                "text": "The newly tracked marker is bronze.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What color is the newly tracked marker?",
                            "answer": "bronze",
                            "evidence": ["D1:1"],
                        }
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )
    previous_report_path = tmp_path / "previous.json"
    previous_report_path.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "move_fail_to_pass_qa_001",
                    "verdict": "fail",
                    "source_hit": False,
                    "planned_evidence_source_hit_at_5": False,
                    "episode_source_hit_at_10": False,
                },
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "move_pass_to_fail_qa_001",
                    "verdict": "pass",
                    "source_hit": True,
                    "planned_evidence_source_hit_at_5": True,
                    "episode_source_hit_at_10": True,
                },
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recall_pipeline="v2",
    )

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="movement-summary",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        comparison_report_paths=[previous_report_path],
    )

    summary_path = settings.data_dir / "evals" / "movement-summary_locomo_movement_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["movement"]["fail_to_pass"] == ["move_fail_to_pass_qa_001"]
    assert summary["movement"]["pass_to_fail"] == ["move_pass_to_fail_qa_001"]
    assert summary["movement"]["unchanged_pass"] == []
    assert summary["movement"]["unchanged_fail"] == []
    assert summary["movement"]["new_case_no_baseline"] == ["move_new_case_qa_001"]
    assert summary["counts"]["movement"] == {
        "fail_to_pass": 1,
        "pass_to_fail": 1,
        "unchanged_pass": 0,
        "unchanged_fail": 0,
        "new_case_no_baseline": 1,
    }
    assert "retrieval_miss" in summary["failure_classes"]
    assert "render_drop" in summary["failure_boundaries"]
    assert summary["source_metric_movement"]["source_hit"]["improved"] == [
        "move_fail_to_pass_qa_001"
    ]
    assert summary["source_metric_movement"]["source_hit"]["regressed"] == [
        "move_pass_to_fail_qa_001"
    ]
    for metric in (
        "planned_evidence_source_hit_at_5",
        "episode_source_hit_at_10",
    ):
        assert summary["source_metric_movement"][metric]["improved"] == [
            "move_fail_to_pass_qa_001"
        ]
        assert summary["source_metric_movement"][metric]["regressed"] == [
            "move_pass_to_fail_qa_001"
        ]
    assert summary["counts"]["source_metric_movement"]["source_hit"] == {
        "improved": 1,
        "regressed": 1,
        "unchanged_hit": 0,
        "unchanged_miss": 0,
    }


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
    kernel_trace_events = report["kernel_trace_events"]
    assert [event["event_type"] for event in kernel_trace_events] == [
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
        "approval_pending",
        "kernel_step_completed",
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
        "approval_granted",
        "tool_executed",
        "tool_verified",
        "kernel_step_completed",
    ]
    for event in kernel_trace_events:
        assert event["step_id"].startswith("step_")
        assert isinstance(event["session_id"], str)
        assert event["session_id"]
        assert isinstance(event["sequence"], int)
        assert isinstance(event["payload"], dict)
    assert len({event["session_id"] for event in kernel_trace_events}) == 1

    pending_event = next(
        event
        for event in kernel_trace_events
        if event["event_type"] == "approval_pending"
    )
    selected_events = [
        event
        for event in kernel_trace_events
        if event["event_type"] == "tool_selected"
    ]
    assert len(selected_events) == 2
    assert pending_event["payload"]["metadata"]["tool_call_id"] == (
        selected_events[0]["payload"]["tool_call_id"]
    )
    assert selected_events[1]["payload"]["tool_call_id"] == (
        selected_events[0]["payload"]["tool_call_id"]
    )
    assert all(event["payload"]["candidate_reason"] for event in selected_events)
    approval_id = pending_event["approval_id"]
    assert approval_id.startswith("approval_")
    assert pending_event["payload"]["approval_id"] == approval_id
    assert pending_event["payload"]["tool_name"] == "archive_write"
    assert pending_event["payload"]["requested_action"]["source"] == (
        "public_benchmark_kernel_probe"
    )

    granted_event = next(
        event
        for event in kernel_trace_events
        if event["event_type"] == "approval_granted"
    )
    assert granted_event["approval_id"] == approval_id
    assert granted_event["payload"]["approved_action"]["content"].startswith(
        "Benchmark question reviewed:"
    )

    executed_event = next(
        event for event in kernel_trace_events if event["event_type"] == "tool_executed"
    )
    assert executed_event["approval_id"] == approval_id
    assert executed_event["payload"]["approval_id"] == approval_id
    assert executed_event["payload"]["tool_name"] == "archive_write"
    assert executed_event["payload"]["ok"] is True
    assert executed_event["payload"]["result"]["memory_id"].startswith("amem_")
    assert executed_event["payload"]["result"]["archive_id"] == executed_event["session_id"]

    verified_event = next(
        event for event in kernel_trace_events if event["event_type"] == "tool_verified"
    )
    assert verified_event["approval_id"] == approval_id
    assert verified_event["payload"]["tool_name"] == "archive_write"
    assert verified_event["payload"]["ok"] is True
    assert verified_event["payload"]["verification"]["status"] == "verified"
    assert verified_event["payload"]["verification"]["session_attachment_found"] is True
    assert verified_event["payload"]["verification"]["eligible_for_session"] is True
    assert report["case_diagnostics"]["kernel_trace_present"] is True
    assert report["case_diagnostics"]["failure_class"] in {
        "supported_cited_answer",
        "evidence_hit_answer_fail",
        "unsupported_answer",
        "judge_questionable",
        "retrieval_miss",
        "context_missing_evidence",
    }


def _model_visible_planner_input(
    *,
    answer_evidence: list[dict[str, object]] | None = None,
    selected_context_ids: list[str] | None = None,
    rendered_evidence_ids: list[str] | None = None,
    cited_source_ids: list[str] | None = None,
    final_context_trace_source_ids: list[str] | None = None,
    unsupported_citation_ids: list[str] | None = None,
    citation_contract_status: str = "supported_cited_answer",
):
    default_source_ids = ["msg_selected"]
    return ModelVisiblePlannerInput(
        question="What is recorded?",
        rendered_answer="MemoryOS Lite [msg_selected]",
        selected_context_ids=(
            default_source_ids if selected_context_ids is None else selected_context_ids
        ),
        final_context_trace_source_ids=(
            default_source_ids
            if final_context_trace_source_ids is None
            else final_context_trace_source_ids
        ),
        rendered_evidence_ids=(
            default_source_ids if rendered_evidence_ids is None else rendered_evidence_ids
        ),
        answer_evidence=(
            [{"id": "msg_selected", "text": "MemoryOS Lite"}]
            if answer_evidence is None
            else answer_evidence
        ),
        cited_source_ids=default_source_ids if cited_source_ids is None else cited_source_ids,
        unsupported_citation_ids=(
            [] if unsupported_citation_ids is None else unsupported_citation_ids
        ),
        citation_contract_status=citation_contract_status,
        archival_eligibility={},
        component_drop_counts={},
        kernel_trace_events=[],
    )


def _eval_gold_sidecar(
    *,
    verdict: str = "fail",
    judge_status: str = "judge_fail",
    failure_class: str = "retrieval_miss",
    movement_status: str = "unchanged_fail",
):
    return EvalGoldSidecar(
        case_id="case_gold",
        expected_answer="gold answer must not leak",
        expected_source_ids=["msg_gold"],
        verdict=verdict,
        judge_status=judge_status,
        failure_class=failure_class,
        movement_status=movement_status,
    )


def test_planner_proposal_excludes_eval_gold_and_is_proposal_only():
    artifact = build_maintenance_artifact(
        model_visible=_model_visible_planner_input(),
        eval_sidecar=_eval_gold_sidecar(),
    )

    serialized_proposal = artifact.proposal.model_dump_json()
    assert artifact.proposal.execution_mode == "proposal_only"
    assert artifact.proposal.gold_fields_used is False
    assert "gold answer must not leak" not in serialized_proposal
    assert "msg_gold" not in serialized_proposal
    assert "msg_selected" in serialized_proposal


def test_planner_without_model_visible_evidence_yields_diagnostic_only_denial():
    artifact = build_maintenance_artifact(
        model_visible=_model_visible_planner_input(
            answer_evidence=[],
            selected_context_ids=[],
            rendered_evidence_ids=[],
            cited_source_ids=[],
            final_context_trace_source_ids=[],
            citation_contract_status="no_cited_evidence",
        ),
        eval_sidecar=_eval_gold_sidecar(),
    )

    assert artifact.proposal.proposal_type == "diagnostic_only_denial"
    assert artifact.proposal.execution_mode == "proposal_only"
    assert artifact.proposal.tool_name is None
    assert artifact.proposal.arguments == {}
    assert artifact.proposal.source_refs == []
    assert artifact.proposal.gold_fields_used is False
    assert artifact.proposal.denial_reason


def test_planner_eval_sidecar_does_not_change_proposal_shape():
    model_visible = _model_visible_planner_input(
        citation_contract_status="supported_cited_answer"
    )
    baseline_artifact = build_maintenance_artifact(
        model_visible=model_visible,
        eval_sidecar=_eval_gold_sidecar(
            verdict="fail",
            judge_status="judge_fail",
            failure_class="evidence_hit_answer_fail",
            movement_status="unchanged_fail",
        ),
    )
    sidecar_artifact = build_maintenance_artifact(
        model_visible=model_visible,
        eval_sidecar=_eval_gold_sidecar(
            verdict="pass",
            judge_status="judge_pass",
            failure_class="retrieval_miss",
            movement_status="unchanged_pass",
        ),
    )

    assert sidecar_artifact.eval_sidecar.judge_status == "judge_pass"
    assert sidecar_artifact.eval_sidecar.failure_class == "retrieval_miss"
    assert sidecar_artifact.proposal == baseline_artifact.proposal
    serialized_arguments = json.dumps(
        sidecar_artifact.proposal.arguments,
        sort_keys=True,
    )
    assert "judge_pass" not in serialized_arguments
    assert "retrieval_miss" not in serialized_arguments
    assert "msg_gold" not in serialized_arguments
    assert "gold answer must not leak" not in serialized_arguments


def test_repair_smoke_denies_gold_fields_in_executable_tool_request():
    from memoryos_lite.public_repair_smoke import build_executable_repair_proposal

    row = {
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "case_id": "case_gold_qa_001",
        "model_visible_planner_input": _model_visible_planner_input().model_dump(
            mode="json"
        ),
        "eval_gold_sidecar": _eval_gold_sidecar().model_dump(mode="json"),
        "maintenance_proposal": {
            "proposal_type": "archive_write",
            "execution_mode": "proposal_only",
            "tool_name": "archive_write",
            "gold_fields_used": False,
            "arguments": {
                "content": "gold answer must not leak",
                "reason": "repair retrieval_miss unchanged_fail case_gold_qa_001",
            },
            "source_refs": [{"source_type": "message", "source_id": "msg_gold"}],
        },
    }

    proposal = build_executable_repair_proposal(
        row,
        source_id_aliases={"msg_selected": "repair_msg_001"},
    )

    assert proposal.executable is False
    assert proposal.denial_reason is not None
    assert (
        "gold" in proposal.denial_reason
        or "forbidden" in proposal.denial_reason
    )
    assert proposal.tool_request is None


def test_repair_smoke_rewrites_model_visible_source_refs_to_repair_store_ids():
    from memoryos_lite.public_repair_smoke import build_executable_repair_proposal

    source_id = "conv-26_qa_001:conv-26:D1:1"
    model_visible = _model_visible_planner_input(
        selected_context_ids=[source_id],
        rendered_evidence_ids=[source_id],
        cited_source_ids=[source_id],
        final_context_trace_source_ids=[source_id],
        answer_evidence=[{"id": source_id, "text": "visible evidence"}],
    )
    row = {
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "case_id": "conv-26_qa_001",
        "model_visible_planner_input": model_visible.model_dump(mode="json"),
        "eval_gold_sidecar": _eval_gold_sidecar().model_dump(mode="json"),
        "maintenance_proposal": {
            "proposal_type": "archive_write",
            "execution_mode": "proposal_only",
            "tool_name": "archive_write",
            "gold_fields_used": False,
            "arguments": {
                "content": "Visible answer from selected context.",
                "reason": "model-visible repair smoke",
            },
            "source_refs": [
                {"source_type": "message", "source_id": source_id},
            ],
        },
    }

    proposal = build_executable_repair_proposal(
        row,
        source_id_aliases={source_id: "repair_msg_001"},
    )

    assert proposal.executable is True
    assert proposal.tool_request is not None
    serialized = proposal.tool_request.model_dump_json()
    assert "conv-26_qa_001" not in serialized
    assert "repair_msg_001" in serialized


def test_repair_smoke_rewrites_argument_source_ids_before_forbidden_value_scan():
    from memoryos_lite.public_repair_smoke import build_executable_repair_proposal

    source_id = "conv-26_qa_001:conv-26:D1:1"
    model_visible = _model_visible_planner_input(
        selected_context_ids=[source_id],
        rendered_evidence_ids=[source_id],
        cited_source_ids=[source_id],
        final_context_trace_source_ids=[source_id],
        answer_evidence=[{"id": source_id, "text": "visible evidence"}],
    )
    row = {
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "case_id": "conv-26_qa_001",
        "model_visible_planner_input": model_visible.model_dump(mode="json"),
        "eval_gold_sidecar": EvalGoldSidecar(
            case_id="conv-26_qa_001",
            expected_answer="gold answer must not leak",
            expected_source_ids=[source_id],
            verdict="fail",
            judge_status="judge_fail",
            failure_class="retrieval_miss",
            movement_status="unchanged_fail",
        ).model_dump(mode="json"),
        "maintenance_proposal": {
            "proposal_type": "archive_write",
            "execution_mode": "proposal_only",
            "tool_name": "archive_write",
            "gold_fields_used": False,
            "arguments": {
                "content": f"Visible note from selected context [{source_id}].",
                "evidence_source_ids": [source_id],
            },
            "source_refs": [
                {"source_type": "message", "source_id": source_id},
            ],
        },
    }

    proposal = build_executable_repair_proposal(
        row,
        source_id_aliases={source_id: "repair_msg_001"},
    )

    assert proposal.executable is True
    assert proposal.tool_request is not None
    serialized = proposal.tool_request.model_dump_json()
    assert source_id not in serialized
    assert "conv-26_qa_001" not in serialized
    assert "repair_msg_001" in serialized


def test_public_repair_smoke_executes_phase16_kernel_tools_before_v3_context(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_repair",
        text="Alice records the repair marker.",
        question="What marker does Alice record?",
        answer="repair marker",
    )
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "sample_repair_qa_001",
                    "model_visible_planner_input": {
                        "question": "What marker does Alice record?",
                        "rendered_answer": "Alice records the repair marker.",
                        "selected_context_ids": [
                            "sample_repair_qa_001:sample_repair:D1:1"
                        ],
                        "final_context_trace_source_ids": [
                            "sample_repair_qa_001:sample_repair:D1:1"
                        ],
                        "rendered_evidence_ids": [
                            "sample_repair_qa_001:sample_repair:D1:1"
                        ],
                        "answer_evidence": [
                            {"id": "sample_repair_qa_001:sample_repair:D1:1"}
                        ],
                        "cited_source_ids": [
                            "sample_repair_qa_001:sample_repair:D1:1"
                        ],
                        "unsupported_citation_ids": [],
                        "citation_contract_status": "supported_cited_answer",
                        "archival_eligibility": {},
                        "component_drop_counts": {},
                        "kernel_trace_events": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "sample_repair_qa_001",
                        "expected_answer": "repair marker",
                        "expected_source_ids": [
                            "sample_repair_qa_001:sample_repair:D1:1"
                        ],
                        "verdict": "fail",
                        "judge_status": "judge_fail",
                        "failure_class": "retrieval_miss",
                        "movement_status": "unchanged_fail",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {
                            "content": "Alice records a model-visible context note."
                        },
                        "source_refs": [
                            {
                                "source_type": "message",
                                "source_id": "sample_repair_qa_001:sample_repair:D1:1",
                            }
                        ],
                        "gold_fields_used": False,
                    },
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
        run_id="repair-smoke-real-path",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )

    report = results[0].to_report()
    assert report["repair_smoke"]["enabled"] is True
    assert report["repair_smoke"]["executed_tool_names"] == ["archive_write"]
    serialized_repair = json.dumps(report["repair_smoke"], sort_keys=True)
    assert "repair marker" not in serialized_repair
    assert "sample_repair_qa_001:sample_repair:D1:1" not in serialized_repair
    assert "repair_msg_" in serialized_repair
    assert "tool_executed" in [
        event["event_type"] for event in report["repair_smoke"]["kernel_trace_events"]
    ]
    assert report["v3_context"]["metadata"]["archival_eligibility"][
        "eligible_archive_ids"
    ]


@pytest.mark.slow
def test_public_repair_smoke_requires_explicit_kernel_opt_in_and_baseline_report(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_repair_opt_in",
        text="Alice records a repair opt-in marker.",
        question="What does Alice record?",
        answer="repair opt-in marker",
    )
    source_id = "sample_repair_opt_in_qa_001:sample_repair_opt_in:D1:1"
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "sample_repair_opt_in_qa_001",
                    "model_visible_planner_input": {
                        "question": "What does Alice record?",
                        "rendered_answer": "Alice records a repair opt-in marker.",
                        "selected_context_ids": [source_id],
                        "final_context_trace_source_ids": [source_id],
                        "rendered_evidence_ids": [source_id],
                        "answer_evidence": [{"id": source_id}],
                        "cited_source_ids": [source_id],
                        "unsupported_citation_ids": [],
                        "citation_contract_status": "supported_cited_answer",
                        "archival_eligibility": {},
                        "component_drop_counts": {},
                        "kernel_trace_events": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "sample_repair_opt_in_qa_001",
                        "expected_answer": "repair opt-in marker",
                        "expected_source_ids": [source_id],
                        "verdict": "fail",
                        "judge_status": "judge_fail",
                        "failure_class": "retrieval_miss",
                        "movement_status": "unchanged_fail",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {
                            "content": "Alice records a model-visible opt-in note."
                        },
                        "source_refs": [
                            {"source_type": "message", "source_id": source_id}
                        ],
                        "gold_fields_used": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    default_results = run_public_benchmark(
        Settings(data_dir=tmp_path / ".memoryos-default", memoryos_memory_arch="v3"),
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-smoke-disabled",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    disabled_report = default_results[0].to_report()["repair_smoke"]
    assert disabled_report["enabled"] is False
    assert disabled_report["executed_tool_names"] == []

    with pytest.raises(ValueError, match="MEMORYOS_AGENT_KERNEL=v1"):
        run_public_benchmark(
            Settings(data_dir=tmp_path / ".memoryos-off", memoryos_memory_arch="v3"),
            benchmark="locomo",
            data_path=data_path,
            run_id="repair-smoke-kernel-off",
            baselines=["memoryos_lite"],
            llm_answer=False,
            llm_judge=False,
            repair_smoke_baseline_report_path=baseline_report,
        )

    with pytest.raises(ValueError, match="memoryos_lite"):
        run_public_benchmark(
            Settings(
                data_dir=tmp_path / ".memoryos-other-baseline",
                memoryos_memory_arch="v3",
                memoryos_agent_kernel="v1",
            ),
            benchmark="locomo",
            data_path=data_path,
            run_id="repair-smoke-other-baseline",
            baselines=["sliding_window"],
            llm_answer=False,
            llm_judge=False,
            repair_smoke_baseline_report_path=baseline_report,
        )

    enabled_results = run_public_benchmark(
        Settings(
            data_dir=tmp_path / ".memoryos-on",
            memoryos_memory_arch="v3",
            memoryos_agent_kernel="v1",
        ),
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-smoke-enabled",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )

    enabled_report = enabled_results[0].to_report()["repair_smoke"]
    assert enabled_report["enabled"] is True
    assert enabled_report["executed_tool_names"] == ["archive_write"]


@pytest.mark.slow
def test_public_repair_smoke_isolated_store_does_not_mutate_default_public_run(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_repair_isolation",
        text="Alice records an ordinary isolation marker.",
        question="What marker does Alice record?",
        answer="ordinary isolation marker",
    )
    original_data = data_path.read_text(encoding="utf-8")
    source_id = "sample_repair_isolation_qa_001:sample_repair_isolation:D1:1"
    repair_artifact_text = "isolated repair artifact must not leak to default runs"
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "sample_repair_isolation_qa_001",
                    "model_visible_planner_input": {
                        "question": "What marker does Alice record?",
                        "rendered_answer": "Alice records an ordinary isolation marker.",
                        "selected_context_ids": [source_id],
                        "final_context_trace_source_ids": [source_id],
                        "rendered_evidence_ids": [source_id],
                        "answer_evidence": [{"id": source_id}],
                        "cited_source_ids": [source_id],
                        "unsupported_citation_ids": [],
                        "citation_contract_status": "supported_cited_answer",
                        "archival_eligibility": {},
                        "component_drop_counts": {},
                        "kernel_trace_events": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "sample_repair_isolation_qa_001",
                        "expected_answer": "ordinary isolation marker",
                        "expected_source_ids": [source_id],
                        "verdict": "fail",
                        "judge_status": "judge_fail",
                        "failure_class": "retrieval_miss",
                        "movement_status": "unchanged_fail",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {"content": repair_artifact_text},
                        "source_refs": [
                            {"source_type": "message", "source_id": source_id}
                        ],
                        "gold_fields_used": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    default_before = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-isolation-default-before",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )[0].to_report()
    repair_report = run_public_benchmark(
        settings.model_copy(update={"memoryos_agent_kernel": "v1"}),
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-isolation-explicit",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )[0].to_report()
    default_after = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-isolation-default-after",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )[0].to_report()

    for default_report in (default_before, default_after):
        assert default_report["repair_smoke"]["enabled"] is False
        assert default_report["repair_smoke"]["executed_tool_names"] == []
        assert default_report["repair_smoke"]["kernel_trace_events"] == []
        assert default_report["kernel_trace_events"] == []

    repair_smoke = repair_report["repair_smoke"]
    assert repair_smoke["enabled"] is True
    assert repair_smoke["executed_tool_names"] == ["archive_write"]
    assert repair_smoke["data_dir"] == str(
        settings.data_dir / "eval_runs" / "repair-isolation-explicit"
    )
    assert "tool_executed" in [
        event["event_type"] for event in repair_smoke["kernel_trace_events"]
    ]

    assert data_path.read_text(encoding="utf-8") == original_data
    assert repair_artifact_text in (
        settings.data_dir
        / "eval_runs"
        / "repair-isolation-explicit"
        / "memoryos.db"
    ).read_text(encoding="utf-8", errors="ignore")
    assert repair_artifact_text not in json.dumps(default_after, sort_keys=True)
    assert repair_artifact_text not in (
        settings.data_dir
        / "eval_runs"
        / "repair-isolation-default-after"
        / "memoryos.db"
    ).read_text(encoding="utf-8", errors="ignore")


@pytest.mark.slow
def test_repair_smoke_archive_artifacts_are_visible_only_when_session_attached(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_repair_visibility",
        text="Alice records an ordinary visibility note.",
        question="What archive boundary marker is attached?",
        answer="ordinary visibility note",
    )
    source_id = "sample_repair_visibility_qa_001:sample_repair_visibility:D1:1"
    repair_archive_text = "attached repair archive boundary marker"
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "sample_repair_visibility_qa_001",
                    "model_visible_planner_input": {
                        "question": "What archive boundary marker is attached?",
                        "rendered_answer": "Alice records an ordinary visibility note.",
                        "selected_context_ids": [source_id],
                        "final_context_trace_source_ids": [source_id],
                        "rendered_evidence_ids": [source_id],
                        "answer_evidence": [{"id": source_id}],
                        "cited_source_ids": [source_id],
                        "unsupported_citation_ids": [],
                        "citation_contract_status": "supported_cited_answer",
                        "archival_eligibility": {},
                        "component_drop_counts": {},
                        "kernel_trace_events": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "sample_repair_visibility_qa_001",
                        "expected_answer": "ordinary visibility note",
                        "expected_source_ids": [source_id],
                        "verdict": "fail",
                        "judge_status": "judge_fail",
                        "failure_class": "retrieval_miss",
                        "movement_status": "unchanged_fail",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {"content": repair_archive_text},
                        "source_refs": [
                            {"source_type": "message", "source_id": source_id}
                        ],
                        "gold_fields_used": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    repair_report = run_public_benchmark(
        settings.model_copy(update={"memoryos_agent_kernel": "v1"}),
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-visibility-attached",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )[0].to_report()
    default_report = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-visibility-default",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )[0].to_report()

    repair_smoke = repair_report["repair_smoke"]
    assert repair_smoke["executed_tool_names"] == ["archive_write"]
    assert repair_smoke["archive_artifacts"] == [
        {
            "archive_id": repair_smoke["archive_artifacts"][0]["archive_id"],
            "passage_id": repair_smoke["archive_artifacts"][0]["passage_id"],
            "verification_status": "verified",
            "session_attachment_found": True,
            "eligible_for_session": True,
        }
    ]
    artifact = repair_smoke["archive_artifacts"][0]
    eligibility = repair_report["v3_context"]["metadata"]["archival_eligibility"]
    assert artifact["archive_id"] in eligibility["eligible_archive_ids"]
    assert artifact["passage_id"] in eligibility["selected_passage_ids"]

    default_eligibility = default_report["v3_context"]["metadata"][
        "archival_eligibility"
    ]
    assert default_report["repair_smoke"]["enabled"] is False
    assert artifact["archive_id"] not in default_eligibility["eligible_archive_ids"]
    assert artifact["passage_id"] not in default_eligibility["selected_passage_ids"]
    assert repair_archive_text not in json.dumps(default_report, sort_keys=True)


def test_repair_smoke_comparison_report_lists_case_level_movement_and_source_metrics(tmp_path):
    data_path = tmp_path / "locomo_two_cases.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "case_fail_to_pass",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Alice",
                                "dia_id": "D1:1",
                                "text": "The repair marker is emerald.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What color is the repair marker?",
                            "answer": "emerald",
                            "evidence": ["D1:1"],
                        }
                    ],
                },
                {
                    "sample_id": "case_pass_to_fail",
                    "conversation": {
                        "session_1": [
                            {
                                "speaker": "Bob",
                                "dia_id": "D1:1",
                                "text": "The ordinary marker is slate.",
                            }
                        ],
                    },
                    "qa": [
                        {
                            "question": "What color is the missing marker?",
                            "answer": "violet",
                            "evidence": ["D9:9"],
                        }
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case_fail_to_pass_qa_001",
                    "verdict": "fail",
                    "source_hit": False,
                    "planned_evidence_source_hit_at_5": False,
                    "episode_source_hit_at_10": False,
                    "model_visible_planner_input": {
                        "question": "What color is the repair marker?",
                        "rendered_answer": "The repair marker is emerald.",
                        "selected_context_ids": [
                            "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1"
                        ],
                        "final_context_trace_source_ids": [
                            "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1"
                        ],
                        "rendered_evidence_ids": [
                            "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1"
                        ],
                        "answer_evidence": [
                            {
                                "id": "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1"
                            }
                        ],
                        "cited_source_ids": [
                            "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1"
                        ],
                        "unsupported_citation_ids": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "case_fail_to_pass_qa_001",
                        "expected_answer": "emerald",
                        "expected_source_ids": [
                            "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1"
                        ],
                        "verdict": "fail",
                        "judge_status": "judge_fail",
                        "failure_class": "retrieval_miss",
                        "movement_status": "unchanged_fail",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {"content": "Visible non-gold emerald note."},
                        "source_refs": [
                            {
                                "source_type": "message",
                                "source_id": "case_fail_to_pass_qa_001:case_fail_to_pass:D1:1",
                            }
                        ],
                        "gold_fields_used": False,
                    },
                },
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "case_pass_to_fail_qa_001",
                    "verdict": "pass",
                    "source_hit": True,
                    "planned_evidence_source_hit_at_5": True,
                    "episode_source_hit_at_10": True,
                    "model_visible_planner_input": {
                        "question": "What color is the missing marker?",
                        "rendered_answer": "The ordinary marker is slate.",
                        "selected_context_ids": [
                            "case_pass_to_fail_qa_001:case_pass_to_fail:D1:1"
                        ],
                        "final_context_trace_source_ids": [
                            "case_pass_to_fail_qa_001:case_pass_to_fail:D1:1"
                        ],
                        "rendered_evidence_ids": [
                            "case_pass_to_fail_qa_001:case_pass_to_fail:D1:1"
                        ],
                        "answer_evidence": [
                            {
                                "id": "case_pass_to_fail_qa_001:case_pass_to_fail:D1:1"
                            }
                        ],
                        "cited_source_ids": [
                            "case_pass_to_fail_qa_001:case_pass_to_fail:D1:1"
                        ],
                        "unsupported_citation_ids": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "case_pass_to_fail_qa_001",
                        "expected_answer": "violet",
                        "expected_source_ids": [
                            "case_pass_to_fail_qa_001:case_pass_to_fail:D9:9"
                        ],
                        "verdict": "pass",
                        "judge_status": "judge_pass",
                        "failure_class": "source_miss_judge_pass",
                        "movement_status": "unchanged_pass",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {"content": "Visible non-gold slate note."},
                        "source_refs": [
                            {
                                "source_type": "message",
                                "source_id": "case_pass_to_fail_qa_001:case_pass_to_fail:D1:1",
                            }
                        ],
                        "gold_fields_used": False,
                    },
                },
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
    )

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-comparison-summary",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )

    summary_path = (
        settings.data_dir
        / "evals"
        / "repair-comparison-summary_locomo_repair_smoke_summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["same_slice_repair_smoke_only"] is True
    assert summary["full_chain_gate_status"] == "not_satisfied"
    assert summary["fail_to_pass"] == ["case_fail_to_pass_qa_001"]
    assert summary["pass_to_fail"] == ["case_pass_to_fail_qa_001"]
    assert summary["unchanged_fail"] == []
    assert summary["unchanged_pass"] == []
    assert set(summary["failure_classes"]) == {
        "retrieval_miss",
        "evidence_hit_answer_fail",
        "context_missing_evidence",
        "unsupported_answer",
        "judge_questionable",
        "source_miss_judge_pass",
    }
    assert summary["failure_classes"]["retrieval_miss"] == [
        "case_pass_to_fail_qa_001"
    ]
    assert summary["source_metric_movement"]["source_hit"]["improved"] == [
        "case_fail_to_pass_qa_001"
    ]
    assert summary["source_metric_movement"]["source_hit"]["regressed"] == [
        "case_pass_to_fail_qa_001"
    ]
    for metric in (
        "planned_evidence_source_hit_at_5",
        "episode_source_hit_at_10",
    ):
        assert summary["source_metric_movement"][metric]["improved"] == [
            "case_fail_to_pass_qa_001"
        ]
        assert summary["source_metric_movement"][metric]["regressed"] == [
            "case_pass_to_fail_qa_001"
        ]


def test_repair_smoke_summary_buckets_judge_pass_source_miss_separately():
    from memoryos_lite.public_repair_smoke import build_repair_smoke_comparison_summary

    baseline_rows = [
        {
            "case_id": "judge_pass_source_miss",
            "verdict": "pass",
            "source_hit": False,
            "planned_evidence_source_hit_at_5": False,
            "episode_source_hit_at_10": False,
        }
    ]
    repair_rows = [
        {
            "case_id": "judge_pass_source_miss",
            "verdict": "pass",
            "failure_class": "retrieval_miss",
            "source_hit": False,
            "planned_evidence_source_hit_at_5": False,
            "episode_source_hit_at_10": False,
        }
    ]

    summary = build_repair_smoke_comparison_summary(
        baseline_rows,
        repair_rows,
        llm_answer=True,
        llm_judge=True,
    )

    assert summary["unchanged_pass"] == ["judge_pass_source_miss"]
    assert summary["failure_classes"]["source_miss_judge_pass"] == [
        "judge_pass_source_miss"
    ]
    assert summary["failure_classes"]["retrieval_miss"] == []


def test_repair_smoke_summary_blocks_missing_extra_and_duplicate_baseline_rows():
    from memoryos_lite.public_repair_smoke import build_repair_smoke_comparison_summary

    baseline_rows = [
        {
            "case_id": "duplicate_baseline",
            "verdict": "pass",
            "source_hit": True,
        },
        {
            "case_id": "duplicate_baseline",
            "verdict": "fail",
            "source_hit": False,
        },
        {
            "case_id": "extra_baseline",
            "verdict": "pass",
            "source_hit": True,
        },
        {
            "case_id": "matched_baseline",
            "verdict": "fail",
            "source_hit": False,
        },
    ]
    repair_rows = [
        {
            "case_id": "duplicate_baseline",
            "verdict": "fail",
            "failure_class": "retrieval_miss",
            "source_hit": False,
        },
        {
            "case_id": "matched_baseline",
            "verdict": "pass",
            "failure_class": "supported_cited_answer",
            "source_hit": True,
        },
        {
            "case_id": "missing_baseline",
            "verdict": "fail",
            "failure_class": "retrieval_miss",
            "source_hit": False,
        },
    ]

    summary = build_repair_smoke_comparison_summary(
        baseline_rows,
        repair_rows,
        llm_answer=True,
        llm_judge=True,
    )

    assert summary["full_chain_gate_status"] == "blocked_baseline_mismatch"
    assert "baseline report must contain exactly one row" in summary[
        "full_chain_gate_reason"
    ]
    assert summary["baseline_coverage"] == {
        "valid": False,
        "matched_case_ids": ["matched_baseline"],
        "missing_baseline_case_ids": ["missing_baseline"],
        "extra_baseline_case_ids": ["extra_baseline"],
        "duplicate_baseline_case_ids": ["duplicate_baseline"],
        "duplicate_repair_case_ids": [],
    }
    assert summary["fail_to_pass"] == ["matched_baseline"]
    assert summary["failure_classes"]["retrieval_miss"] == [
        "duplicate_baseline",
        "missing_baseline",
    ]


def test_public_repair_smoke_summary_preserves_duplicate_baseline_rows(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="duplicate_baseline_sample",
        text="The duplicate baseline marker is cinnabar.",
        question="What is the duplicate baseline marker?",
        answer="cinnabar",
    )
    baseline_row = {
        "benchmark": "locomo",
        "baseline": "memoryos_lite",
        "case_id": "duplicate_baseline_sample_qa_001",
        "verdict": "fail",
        "source_hit": False,
        "planned_evidence_source_hit_at_5": False,
        "episode_source_hit_at_10": False,
    }
    baseline_report = tmp_path / "duplicate_baseline_report.json"
    baseline_report.write_text(
        json.dumps([baseline_row, dict(baseline_row)]),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
    )

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="duplicate-baseline-summary",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
        repair_smoke_baseline_report_path=baseline_report,
    )

    summary = json.loads(
        (
            settings.data_dir
            / "evals"
            / "duplicate-baseline-summary_locomo_repair_smoke_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["full_chain_gate_status"] == "blocked_baseline_mismatch"
    assert summary["baseline_coverage"]["duplicate_baseline_case_ids"] == [
        "duplicate_baseline_sample_qa_001"
    ]


@pytest.mark.parametrize(
    "failure_class",
    [
        "evidence_retrieved_not_selected",
        "evidence_selected_not_rendered",
        "evidence_rendered_not_answer_evidence",
    ],
)
def test_repair_smoke_summary_maps_context_diagnostic_classes(failure_class):
    from memoryos_lite.public_repair_smoke import build_repair_smoke_comparison_summary

    baseline_rows = [
        {
            "case_id": failure_class,
            "verdict": "fail",
            "source_hit": True,
        }
    ]
    repair_rows = [
        {
            "case_id": failure_class,
            "verdict": "fail",
            "failure_class": failure_class,
            "source_hit": True,
        }
    ]

    summary = build_repair_smoke_comparison_summary(
        baseline_rows,
        repair_rows,
        llm_answer=True,
        llm_judge=True,
    )

    assert summary["failure_classes"]["context_missing_evidence"] == [failure_class]


def test_no_llm_repair_smoke_report_is_diagnostic_not_full_chain_gate():
    from memoryos_lite.public_repair_smoke import build_repair_smoke_comparison_summary

    baseline_rows = [
        {
            "case_id": "case_no_llm_qa_001",
            "verdict": "fail",
            "source_hit": False,
        }
    ]
    repair_rows = [
        {
            "case_id": "case_no_llm_qa_001",
            "verdict": "pass",
            "answer_mode": "projected",
            "reasoning": "exact substring match",
            "source_hit": True,
        }
    ]

    no_llm_summary = build_repair_smoke_comparison_summary(
        baseline_rows,
        repair_rows,
        llm_answer=False,
        llm_judge=False,
    )

    assert no_llm_summary["answer_mode"] == "projected"
    assert no_llm_summary["judge_mode"] == "heuristic"
    assert no_llm_summary["full_chain_gate_status"] == "not_satisfied"
    assert "diagnostic only" in no_llm_summary["full_chain_gate_reason"]
    assert no_llm_summary["promotion_gate_satisfied"] is False
    assert no_llm_summary["quality_gate_satisfied"] is False

    provider_blocked_summary = build_repair_smoke_comparison_summary(
        baseline_rows,
        repair_rows,
        llm_answer=True,
        llm_judge=True,
        provider_errors=[
            {
                "stage": "answerer_init",
                "error": "OPENAI_API_KEY required for public benchmark answerer",
            }
        ],
    )

    assert (
        provider_blocked_summary["full_chain_gate_status"]
        == "blocked_provider_unavailable"
    )
    assert "provider unavailable" in provider_blocked_summary["full_chain_gate_reason"]
    assert provider_blocked_summary["provider_errors"] == [
        {
            "stage": "answerer_init",
            "error": "OPENAI_API_KEY required for public benchmark answerer",
        }
    ]


def test_full_chain_repair_smoke_provider_blocker_writes_summary(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_provider_blocked",
        text="Alice records a provider blocker marker.",
        question="What marker does Alice record?",
        answer="provider blocker marker",
    )
    source_id = "sample_provider_blocked_qa_001:sample_provider_blocked:D1:1"
    baseline_report = tmp_path / "baseline.json"
    baseline_report.write_text(
        json.dumps(
            [
                {
                    "benchmark": "locomo",
                    "baseline": "memoryos_lite",
                    "case_id": "sample_provider_blocked_qa_001",
                    "model_visible_planner_input": {
                        "question": "What marker does Alice record?",
                        "rendered_answer": "Alice records a provider blocker marker.",
                        "selected_context_ids": [source_id],
                        "final_context_trace_source_ids": [source_id],
                        "rendered_evidence_ids": [source_id],
                        "answer_evidence": [{"id": source_id}],
                        "cited_source_ids": [source_id],
                        "unsupported_citation_ids": [],
                        "citation_contract_status": "supported_cited_answer",
                        "archival_eligibility": {},
                        "component_drop_counts": {},
                        "kernel_trace_events": [],
                    },
                    "eval_gold_sidecar": {
                        "case_id": "sample_provider_blocked_qa_001",
                        "expected_answer": "provider blocker marker",
                        "expected_source_ids": [source_id],
                        "verdict": "fail",
                        "judge_status": "judge_fail",
                        "failure_class": "retrieval_miss",
                        "movement_status": "unchanged_fail",
                    },
                    "maintenance_proposal": {
                        "proposal_type": "archive_write",
                        "execution_mode": "proposal_only",
                        "tool_name": "archive_write",
                        "arguments": {"content": "Alice records a visible note."},
                        "source_refs": [
                            {"source_type": "message", "source_id": source_id}
                        ],
                        "gold_fields_used": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
        memoryos_llm_provider="openai",
        openai_api_key=None,
        deepseek_api_key=None,
    )

    run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="repair-provider-blocked",
        baselines=["memoryos_lite"],
        llm_answer=True,
        llm_judge=True,
        repair_smoke_baseline_report_path=baseline_report,
    )

    summary = json.loads(
        (
            settings.data_dir
            / "evals"
            / "repair-provider-blocked_locomo_repair_smoke_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["full_chain_gate_status"] == "blocked_provider_unavailable"
    assert "provider unavailable" in summary["full_chain_gate_reason"]
    assert summary["provider_errors"] == [
        {
            "stage": "answerer_init",
            "error": "OPENAI_API_KEY required for public benchmark answerer",
        },
        {
            "stage": "judge_init",
            "error": "OPENAI_API_KEY required for LLM judge",
        },
    ]


def test_public_report_emits_planner_artifacts_without_planner_tool_execution(tmp_path):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_planner_report",
        text="The planner marker is MemoryOS Lite.",
        question="What is the planner marker?",
        answer="MemoryOS Lite",
    )
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-planner-report-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert report["model_visible_planner_input"]["question"] == (
        "What is the planner marker?"
    )
    assert report["eval_gold_sidecar"]["expected_answer"] == "MemoryOS Lite"
    assert report["eval_gold_sidecar"]["expected_source_ids"] == [
        "sample_planner_report_qa_001:sample_planner_report:D1:1"
    ]
    assert report["maintenance_proposal"]["execution_mode"] == "proposal_only"
    assert report["maintenance_proposal"]["gold_fields_used"] is False
    assert all(
        event["event_type"] != "tool_executed"
        for event in report["kernel_trace_events"]
    )
