"""Tests for LLM judge — parsing logic only (no API calls)."""

import json

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.llm_judge import LLMJudge
from memoryos_lite.schemas import EvalCase, MessageCreate, Role


def _make_case(
    expected: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> EvalCase:
    return EvalCase(
        case_id="test_001",
        conversation=[MessageCreate(role=Role.USER, content="hi")],
        question="What is X?",
        expected_facts=expected or ["fact_a"],
        forbidden_facts=forbidden or ["bad_fact"],
    )


def test_parse_valid_json():
    settings = Settings(openai_api_key="sk-fake")
    judge = LLMJudge(settings)
    response = json.dumps(
        {
            "expected_present": ["fact_a"],
            "expected_missing": [],
            "forbidden_present": [],
            "verdict": "pass",
            "reasoning": "All facts found",
        }
    )
    verdict = judge._parse_response("test_001", response)
    assert verdict.verdict == "pass"
    assert verdict.expected_present == ["fact_a"]
    assert verdict.expected_missing == []
    assert verdict.forbidden_present == []


def test_parse_json_with_code_fence():
    settings = Settings(openai_api_key="sk-fake")
    judge = LLMJudge(settings)
    response = (
        "```json\n"
        + json.dumps(
            {
                "expected_present": [],
                "expected_missing": ["fact_a"],
                "forbidden_present": ["bad_fact"],
                "verdict": "fail",
                "reasoning": "Missing expected, has forbidden",
            }
        )
        + "\n```"
    )
    verdict = judge._parse_response("test_001", response)
    assert verdict.verdict == "fail"
    assert verdict.expected_missing == ["fact_a"]
    assert verdict.forbidden_present == ["bad_fact"]


def test_parse_invalid_json_returns_error():
    settings = Settings(openai_api_key="sk-fake")
    judge = LLMJudge(settings)
    verdict = judge._parse_response("test_001", "not json at all")
    assert verdict.verdict == "error"
    assert "Failed to parse" in verdict.reasoning


def test_init_requires_api_key():
    settings = Settings(openai_api_key=None)
    with pytest.raises(ValueError, match="openai_api_key required"):
        LLMJudge(settings)
