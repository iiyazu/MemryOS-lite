from memoryos_lite.agent_answer_eval import (
    AgentAnswerEvalCase,
    evaluate_agent_answer,
    evaluate_agent_answers,
    run_agent_answer_eval,
)
from memoryos_lite.config import Settings
from memoryos_lite.schemas import ContextEvidence, Role


def test_agent_answer_eval_requires_citation_from_retrieved_source():
    evidence = ContextEvidence(
        message_id="msg_supported",
        text="MemoryOS Lite uses source citations.",
        role=Role.USER,
        reason="bm25=3.0",
        estimated_tokens=8,
    )

    result = evaluate_agent_answer(
        "MemoryOS Lite uses source citations [msg_supported].",
        [evidence],
    )

    assert result.answer_has_citation is True
    assert result.answer_uses_retrieved_source is True
    assert result.unsupported_answer is False
    assert result.unsupported_citation_ids == []


def test_agent_answer_eval_flags_citation_not_in_retrieved_sources():
    result = evaluate_agent_answer(
        "MemoryOS Lite uses source citations [msg_wrong].",
        ["msg_supported"],
    )

    assert result.answer_has_citation is True
    assert result.answer_uses_retrieved_source is False
    assert result.unsupported_answer is True
    assert result.unsupported_citation_ids == ["msg_wrong"]


def test_agent_answer_eval_accepts_no_evidence_refusal():
    result = evaluate_agent_answer(
        "Insufficient retrieved evidence to answer with source citations.",
        [],
    )

    assert result.answer_has_citation is False
    assert result.answer_uses_retrieved_source is False
    assert result.refusal_when_no_evidence is True
    assert result.unsupported_answer is False


def test_agent_answer_eval_summary_reports_unsupported_answer_rate():
    summary = evaluate_agent_answers(
        [
            AgentAnswerEvalCase(
                case_id="supported",
                answer="MemoryOS Lite uses source citations [msg_supported].",
                retrieved_sources=["msg_supported"],
            ),
            AgentAnswerEvalCase(
                case_id="refusal",
                answer="Insufficient retrieved evidence to answer with source citations.",
                retrieved_sources=[],
            ),
            AgentAnswerEvalCase(
                case_id="unsupported",
                answer="MemoryOS Lite solved LoCoMo [msg_wrong].",
                retrieved_sources=["msg_supported"],
            ),
        ]
    )

    report = summary.to_report()

    assert report["total_cases"] == 3
    assert report["no_evidence_cases"] == 1
    assert report["answer_has_citation"] == 2 / 3
    assert report["answer_uses_retrieved_source"] == 1 / 3
    assert report["refusal_when_no_evidence"] == 1.0
    assert report["unsupported_answer_rate"] == 1 / 3


def test_run_agent_answer_eval_writes_offline_report(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    summary = run_agent_answer_eval(settings, run_id="agent-answer-test")
    report_path = settings.data_dir / "evals" / "agent-answer-test_agent_answer.json"

    assert summary.total_cases == 3
    assert summary.refusal_when_no_evidence == 1.0
    assert summary.unsupported_answer_rate == 1 / 3
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "unsupported_unretrieved_citation" in report_text
    assert "no real LLM/API calls" in report_text
