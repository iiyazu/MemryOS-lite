"""Deterministic diagnostics for evidence-grounded agent answers.

These checks intentionally inspect answer text and retrieved evidence only.
They do not call an LLM and should not be mixed with public benchmark
retrieval/source-attribution metrics.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from memoryos_lite.config import Settings
from memoryos_lite.schemas import ContextEvidence

_CITATION_RE = re.compile(r"\[([^\]\s]+)\]")
_REFUSAL_MARKERS = (
    "insufficient retrieved evidence",
    "insufficient evidence",
    "not enough evidence",
    "no retrieved evidence",
    "unable to answer",
    "cannot answer",
    "can't answer",
    "未找到相关记忆",
)


@dataclass(frozen=True)
class AgentAnswerEvalResult:
    answer_has_citation: bool
    answer_uses_retrieved_source: bool
    refusal_when_no_evidence: bool | None
    unsupported_answer: bool
    cited_source_ids: list[str]
    retrieved_source_ids: list[str]
    unsupported_citation_ids: list[str]
    missing_citation: bool = False
    explicit_no_evidence_refusal: bool = False
    citation_contract_status: str = "unknown"

    def to_report(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AgentAnswerEvalCase:
    case_id: str
    answer: str
    retrieved_sources: Sequence[str | ContextEvidence]


@dataclass(frozen=True)
class AgentAnswerEvalSummary:
    total_cases: int
    no_evidence_cases: int
    answer_has_citation: float
    answer_uses_retrieved_source: float
    refusal_when_no_evidence: float | None
    unsupported_answer_rate: float
    results: list[AgentAnswerEvalResult]

    def to_report(self) -> dict[str, object]:
        return {
            "total_cases": self.total_cases,
            "no_evidence_cases": self.no_evidence_cases,
            "answer_has_citation": self.answer_has_citation,
            "answer_uses_retrieved_source": self.answer_uses_retrieved_source,
            "refusal_when_no_evidence": self.refusal_when_no_evidence,
            "unsupported_answer_rate": self.unsupported_answer_rate,
            "results": [result.to_report() for result in self.results],
        }


def run_agent_answer_eval(settings: Settings, run_id: str) -> AgentAnswerEvalSummary:
    """Run deterministic scripted answer diagnostics and write a JSON report."""

    cases = scripted_agent_answer_cases()
    summary = evaluate_agent_answers(cases)
    report_dir = settings.data_dir / "evals"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}_agent_answer.json"
    report = summary.to_report()
    report["description"] = (
        "Deterministic agent-answer diagnostics over scripted fixtures; no real LLM/API calls."
    )
    report["cases"] = [
        {
            "case_id": case.case_id,
            "answer": case.answer,
            "retrieved_source_ids": _retrieved_source_ids(case.retrieved_sources),
            "result": result.to_report(),
        }
        for case, result in zip(cases, summary.results, strict=True)
    ]
    Path(report_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def scripted_agent_answer_cases() -> list[AgentAnswerEvalCase]:
    """Small offline fixture set covering supported, refusal, and unsupported answers."""

    return [
        AgentAnswerEvalCase(
            case_id="supported_cited_answer",
            answer="MemoryOS Lite uses source citations [msg_supported].",
            retrieved_sources=["msg_supported"],
        ),
        AgentAnswerEvalCase(
            case_id="no_evidence_refusal",
            answer="Insufficient retrieved evidence to answer with source citations.",
            retrieved_sources=[],
        ),
        AgentAnswerEvalCase(
            case_id="unsupported_unretrieved_citation",
            answer="MemoryOS Lite solved LoCoMo [msg_wrong].",
            retrieved_sources=["msg_supported"],
        ),
    ]


def evaluate_agent_answer(
    answer: str,
    retrieved_sources: Iterable[str | ContextEvidence],
) -> AgentAnswerEvalResult:
    """Score one final agent answer against retrieved source IDs."""

    cited_source_ids = _extract_cited_source_ids(answer)
    retrieved_source_ids = _retrieved_source_ids(retrieved_sources)
    retrieved_source_set = set(retrieved_source_ids)
    cited_source_set = set(cited_source_ids)
    unsupported_citation_ids = sorted(cited_source_set - retrieved_source_set)
    has_retrieved_source = bool(cited_source_set & retrieved_source_set)
    no_evidence = not retrieved_source_ids
    refusal = _is_refusal(answer)
    has_content = bool(answer.strip())
    missing_citation = (
        bool(retrieved_source_ids)
        and has_content
        and not refusal
        and not cited_source_ids
    )
    explicit_no_evidence_refusal = no_evidence and refusal

    unsupported_answer = False
    if no_evidence:
        unsupported_answer = has_content and not refusal
    elif not refusal:
        unsupported_answer = not has_retrieved_source or bool(unsupported_citation_ids)
    if missing_citation:
        unsupported_answer = True

    if unsupported_citation_ids:
        citation_contract_status = "unsupported_citation"
    elif explicit_no_evidence_refusal:
        citation_contract_status = "no_evidence_refusal"
    elif no_evidence and has_content and not refusal:
        citation_contract_status = "unsupported_answer"
    elif missing_citation:
        citation_contract_status = "missing_citation"
    elif cited_source_ids and not unsupported_answer:
        citation_contract_status = "supported_cited_answer"
    elif not retrieved_source_ids:
        citation_contract_status = "no_evidence"
    else:
        citation_contract_status = "unsupported_answer"

    return AgentAnswerEvalResult(
        answer_has_citation=bool(cited_source_ids),
        answer_uses_retrieved_source=has_retrieved_source,
        refusal_when_no_evidence=(refusal if no_evidence else None),
        unsupported_answer=unsupported_answer,
        cited_source_ids=cited_source_ids,
        retrieved_source_ids=retrieved_source_ids,
        unsupported_citation_ids=unsupported_citation_ids,
        missing_citation=missing_citation,
        explicit_no_evidence_refusal=explicit_no_evidence_refusal,
        citation_contract_status=citation_contract_status,
    )


def evaluate_agent_answers(cases: Sequence[AgentAnswerEvalCase]) -> AgentAnswerEvalSummary:
    """Aggregate deterministic answer-level diagnostics for scripted cases."""

    results = [evaluate_agent_answer(case.answer, case.retrieved_sources) for case in cases]
    total = len(results)
    no_evidence_results = [result for result in results if not result.retrieved_source_ids]
    return AgentAnswerEvalSummary(
        total_cases=total,
        no_evidence_cases=len(no_evidence_results),
        answer_has_citation=_rate(result.answer_has_citation for result in results),
        answer_uses_retrieved_source=_rate(
            result.answer_uses_retrieved_source for result in results
        ),
        refusal_when_no_evidence=(
            _rate(result.refusal_when_no_evidence is True for result in no_evidence_results)
            if no_evidence_results
            else None
        ),
        unsupported_answer_rate=_rate(result.unsupported_answer for result in results),
        results=results,
    )


def _extract_cited_source_ids(answer: str) -> list[str]:
    seen: set[str] = set()
    cited: list[str] = []
    for match in _CITATION_RE.finditer(answer):
        source_id = match.group(1).strip()
        if source_id and source_id not in seen:
            cited.append(source_id)
            seen.add(source_id)
    return cited


def _retrieved_source_ids(
    retrieved_sources: Iterable[str | ContextEvidence],
) -> list[str]:
    seen: set[str] = set()
    source_ids: list[str] = []
    for source in retrieved_sources:
        source_id = source.message_id if isinstance(source, ContextEvidence) else source
        if source_id and source_id not in seen:
            source_ids.append(source_id)
            seen.add(source_id)
    return source_ids


def _is_refusal(answer: str) -> bool:
    normalized = " ".join(answer.lower().split())
    return any(marker in normalized for marker in _REFUSAL_MARKERS)


def _rate(values: Iterable[bool]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(1 for item in items if item) / len(items)
