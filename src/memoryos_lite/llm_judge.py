"""LLM-as-judge evaluator for semantic accuracy.

Uses GPT to judge whether an answer semantically satisfies expected
facts and avoids forbidden facts, beyond simple string matching.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from memoryos_lite.config import Settings
from memoryos_lite.schemas import EvalCase

_SYSTEM_PROMPT = """\
You are an evaluation judge. Given a question, an answer, expected facts, \
and forbidden facts, determine:
1. Which expected facts are semantically present in the answer (even if \
   phrased differently).
2. Which forbidden facts are present in the answer.
3. An overall verdict: "pass" if all expected facts are present and no \
   forbidden facts are present, otherwise "fail".

Respond ONLY with valid JSON:
{
  "expected_present": ["fact1", ...],
  "expected_missing": ["fact2", ...],
  "forbidden_present": ["fact3", ...],
  "verdict": "pass" or "fail",
  "reasoning": "brief explanation"
}
"""


@dataclass
class JudgeVerdict:
    """Result of LLM judge evaluation."""

    case_id: str
    verdict: str  # "pass" or "fail"
    expected_present: list[str]
    expected_missing: list[str]
    forbidden_present: list[str]
    reasoning: str


class LLMJudge:
    """GPT-as-judge for semantic evaluation of memory recall answers."""

    def __init__(self, settings: Settings) -> None:
        api_key = settings.chat_api_key
        if not api_key:
            raise ValueError(f"{settings.chat_api_key_name} required for LLM judge")
        kwargs: dict[str, Any] = {}
        if settings.chat_base_url:
            kwargs["base_url"] = settings.chat_base_url
        self.llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=SecretStr(api_key),
            temperature=0.0,
            timeout=settings.memoryos_llm_timeout_s,
            **kwargs,
        )

    def judge(self, case: EvalCase, answer: str) -> JudgeVerdict:
        """Judge whether answer satisfies the eval case semantically."""
        user_msg = (
            f"Question: {case.question}\n"
            f"Answer: {answer}\n"
            f"Expected facts: {json.dumps(case.expected_facts, ensure_ascii=False)}\n"
            f"Forbidden facts: {json.dumps(case.forbidden_facts, ensure_ascii=False)}"
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ]
        verdict = self._invoke_judge(case.case_id, messages)
        if verdict.verdict == "error":
            return self._invoke_judge(case.case_id, messages)
        return verdict

    def _invoke_judge(
        self, case_id: str, messages: list[SystemMessage | HumanMessage]
    ) -> JudgeVerdict:
        response = self.llm.invoke(
            messages
        )
        return self._parse_response(case_id, response.content)

    def judge_batch(self, cases: list[tuple[EvalCase, str]]) -> list[JudgeVerdict]:
        """Judge multiple (case, answer) pairs."""
        return [self.judge(case, answer) for case, answer in cases]

    def _parse_response(self, case_id: str, content: str | list) -> JudgeVerdict:
        """Parse LLM JSON response into JudgeVerdict."""
        text = content if isinstance(content, str) else str(content)
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        data = self._extract_json_object(text)
        if data is None:
            return JudgeVerdict(
                case_id=case_id,
                verdict="error",
                expected_present=[],
                expected_missing=[],
                forbidden_present=[],
                reasoning=f"Failed to parse LLM response: {text[:200]}",
            )
        return JudgeVerdict(
            case_id=case_id,
            verdict=data.get("verdict", "error"),
            expected_present=data.get("expected_present", []),
            expected_missing=data.get("expected_missing", []),
            forbidden_present=data.get("forbidden_present", []),
            reasoning=data.get("reasoning", ""),
        )

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            if start == -1:
                return None
            decoder = json.JSONDecoder()
            try:
                data, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None
