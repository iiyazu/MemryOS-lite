from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import BaselineOutput, _expand_baselines, _run_baseline
from memoryos_lite.llm_judge import LLMJudge
from memoryos_lite.public_case_diagnostics import build_case_diagnostics
from memoryos_lite.public_case_movement import load_public_case_movement
from memoryos_lite.schemas import EvalCase, Message, MessageCreate, Role
from memoryos_lite.store import create_store
from memoryos_lite.tokenizer import TokenEstimator


@dataclass(frozen=True)
class PublicBenchmarkCase:
    benchmark: str
    case: EvalCase
    messages: list[Message]
    expected_answer: str
    expected_source_ids: list[str]
    expected_session_ids: list[str]
    source_sessions_by_id: dict[str, str]
    question_type: str | None = None


@dataclass(frozen=True)
class AnswerEvidence:
    evidence_id: str
    text: str
    component: str = "context"
    source_ids: list[str] = field(default_factory=list)
    session_id: str | None = None
    date: str | None = None
    rendered_index: int | None = None
    estimated_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublicBenchmarkResult:
    benchmark: str
    baseline: str
    case_id: str
    question: str
    expected_answer: str
    answer: str
    answer_mode: str
    verdict: str
    reasoning: str
    expected_present: list[str]
    expected_missing: list[str]
    source_ids: list[str]
    expected_source_ids: list[str]
    source_overlap_ids: list[str]
    missing_source_ids: list[str]
    retrieval_candidate_top_k: int | None
    retrieval_candidate_unit: str | None
    retrieval_candidate_page_ids: list[str]
    retrieval_candidate_source_ids: list[str]
    retrieval_candidate_session_ids: list[str]
    page_candidate_top_k: int | None
    page_candidate_page_ids: list[str]
    page_candidate_source_ids: list[str]
    page_candidate_session_ids: list[str]
    source_recall: float | None
    source_hit: bool | None
    source_hit_at_k: bool | None
    page_source_overlap_at_k: bool | None
    expected_session_ids: list[str]
    source_session_ids: list[str]
    session_overlap_ids: list[str]
    missing_session_ids: list[str]
    session_recall: float | None
    session_hit: bool | None
    session_hit_at_k: bool | None
    page_session_overlap_at_k: bool | None
    context_tokens: int
    page_count: int
    loaded_pages: int
    dropped_pages: int
    page_type_counts: dict[str, int]
    page_source_counts: list[int]
    page_summary_token_counts: list[int]
    retrieved_page_ids: list[str]
    dropped_page_reasons: dict[str, str]
    dropped_relevant_page_ids: list[str]
    dropped_relevant_page_count: int
    superseded_source_recovered: int
    candidate_budget_dropped: int
    active_overlap_not_top5: int
    latency_ms: int
    question_type: str | None = None
    episode_source_hit_at_10: bool | None = None
    item_source_hit_at_10: bool | None = None
    planned_evidence_source_hit_at_5: bool | None = None
    budget_dropped_relevant: int = 0
    source_not_indexed: bool = False
    indexed_source_ids: list[str] = field(default_factory=list)
    item_candidate_source_ids: list[str] = field(default_factory=list)
    episode_candidate_message_ids: list[str] = field(default_factory=list)
    planned_evidence_message_ids: list[str] = field(default_factory=list)
    item_source_overlap_at_k: bool | None = None
    item_promoted_evidence_count: int = 0
    item_evidence_budget_dropped: int = 0
    item_hit_item_ids: list[str] = field(default_factory=list)
    item_hit_source_ids: list[str] = field(default_factory=list)
    item_count_in_session: int = 0
    memory_arch: str | None = None
    v3_context: dict[str, Any] = field(default_factory=dict)
    v3_layer_counts: dict[str, int] = field(default_factory=dict)
    v3_budget_decisions: list[dict[str, Any]] = field(default_factory=list)
    v3_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    v3_component_accounting: list[dict[str, Any]] = field(default_factory=list)
    v3_final_context_trace: list[dict[str, Any]] = field(default_factory=list)
    v3_component_token_totals: dict[str, int] = field(default_factory=dict)
    v3_component_drop_counts: dict[str, int] = field(default_factory=dict)
    locomo_neighbor_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    kernel_trace_events: list[str] = field(default_factory=list)
    case_diagnostics: dict[str, Any] = field(default_factory=dict)
    failure_class: str = "unknown"
    movement_status: str = "new_case_no_baseline"
    answer_support_status: str = "unknown"
    judge_status: str = "unknown"

    def to_report(self) -> dict[str, object]:
        data = asdict(self)
        data["pass"] = self.verdict == "pass"
        return data


def load_public_benchmark_cases(
    benchmark: str,
    data_path: Path,
    limit: int | None = None,
) -> list[PublicBenchmarkCase]:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    normalized = benchmark.strip().lower()
    if normalized == "longmemeval":
        cases = _load_longmemeval(data)
    elif normalized == "locomo":
        cases = _load_locomo(data)
    else:
        raise ValueError("benchmark must be 'longmemeval' or 'locomo'")
    return cases[:limit] if limit is not None else cases


def run_public_benchmark(
    settings: Settings,
    benchmark: str,
    data_path: Path,
    run_id: str,
    baselines: list[str],
    limit: int | None = None,
    llm_answer: bool = False,
    llm_judge: bool = False,
    isolated: bool = True,
    comparison_report_paths: list[Path] | None = None,
) -> list[PublicBenchmarkResult]:
    public_cases = load_public_benchmark_cases(benchmark, data_path, limit=limit)
    comparison = load_public_case_movement(comparison_report_paths or [])
    answerer = PublicAnswerer(settings) if llm_answer else None
    judge = LLMJudge(settings) if llm_judge else None
    eval_root = settings.memoryos_eval_data_dir or settings.data_dir / "eval_runs"
    run_dir = eval_root / run_id
    run_settings = settings.model_copy(
        update={
            "data_dir": run_dir,
            "database_url": None,
            "memoryos_paging_mode": settings.memoryos_paging_mode,
            "openai_api_key": None,
            "deepseek_api_key": settings.deepseek_api_key,
            "rot_safe_budget": 4_800,
            "memoryos_embedding_provider": "fastembed",
            "memoryos_recall_pipeline": settings.memoryos_recall_pipeline,
            "memoryos_rewrite_enabled": settings.memoryos_rewrite_enabled,
            "memoryos_rerank_enabled": settings.memoryos_rerank_enabled,
        }
    )
    store = create_store(run_settings)
    if isolated:
        store.reset()
    service = MemoryOSService(store=store, settings=run_settings)
    results: list[PublicBenchmarkResult] = []

    source_mapping: dict[str, str] = {}
    report_dir = settings.data_dir / "evals"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}_{benchmark.lower()}.json"
    partial_report_path = report_dir / f"{run_id}_{benchmark.lower()}.partial.json"

    def write_partial_report() -> None:
        partial_report_path.write_text(
            json.dumps([result.to_report() for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    for public_case in public_cases:
        for baseline in _expand_baselines(baselines):
            start = time.perf_counter()
            output = _run_baseline(
                baseline,
                public_case.case,
                public_case.messages,
                service,
                run_settings,
                budget_override=run_settings.rot_safe_budget,
            )
            answer = _public_projected_answer_with_citations(output.answer, output.sources)
            answer_error: str | None = None
            if answerer is not None:
                try:
                    answer = answerer.answer(
                        public_case.case.question,
                        _answer_evidence_from_output(output),
                    )
                except Exception as exc:
                    answer_error = f"answer_error: {exc}"
                    answer = ""
            latency_ms = int((time.perf_counter() - start) * 1000)
            if judge is not None:
                if answer_error is not None:
                    verdict_label = "error"
                    reasoning = answer_error
                    expected_present = []
                    expected_missing = list(public_case.case.expected_facts)
                else:
                    try:
                        verdict = judge.judge(public_case.case, answer)
                        verdict_label = verdict.verdict
                        reasoning = verdict.reasoning
                        expected_present = verdict.expected_present
                        expected_missing = verdict.expected_missing
                    except Exception as exc:
                        verdict_label = "error"
                        reasoning = f"judge_error: {exc}"
                        expected_present = []
                        expected_missing = list(public_case.case.expected_facts)
            else:
                verdict_label = "pass" if public_case.expected_answer in answer else "fail"
                reasoning = answer_error or "exact substring match"
                expected_present = [public_case.expected_answer] if verdict_label == "pass" else []
                expected_missing = [] if verdict_label == "pass" else [public_case.expected_answer]
            # Use actual session ID (not case title) for item metrics
            session_for_items = store.get_session_by_title(
                public_case.case.case_id
            )
            actual_session_id = (
                session_for_items.id
                if session_for_items
                else public_case.case.case_id
            )
            item_metrics = _extract_item_metrics(
                store, actual_session_id, public_case.expected_source_ids
            )
            comparison_key = (public_case.benchmark, baseline, public_case.case.case_id)
            baseline_case = comparison.get(comparison_key)
            results.append(
                _to_public_result(
                    public_case,
                    baseline,
                    answer,
                    "llm" if answerer is not None else "projected",
                    sorted(output.sources),
                    verdict_label,
                    reasoning,
                    expected_present,
                    expected_missing,
                    output,
                    latency_ms,
                    item_metrics,
                    baseline_verdict=(
                        baseline_case.verdict if baseline_case is not None else None
                    ),
                    movement_baseline_source=(
                        baseline_case.source if baseline_case is not None else None
                    ),
                )
            )
        # Collect source mapping before store resets for next case
        session = store.get_session_by_title(public_case.case.case_id)
        if session is not None:
            stored_msgs = store.list_messages(session.id)
            for bench_msg, stored_msg in zip(
                public_case.messages, stored_msgs, strict=False
            ):
                source_mapping[bench_msg.id] = stored_msg.id
        write_partial_report()

    run_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = run_dir / "source_mapping.json"
    mapping_path.write_text(
        json.dumps(source_mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_path.write_text(
        json.dumps([result.to_report() for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def _load_longmemeval(data: Any) -> list[PublicBenchmarkCase]:
    if not isinstance(data, list):
        raise ValueError("LongMemEval data must be a JSON list")
    tokenizer = TokenEstimator()
    cases: list[PublicBenchmarkCase] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("question_id") or f"longmemeval_{index:04d}")
        question = str(item.get("question") or "").strip()
        answer = _answer_to_text(item.get("answer"))
        if not question or not answer:
            continue
        session_ids = [str(value) for value in item.get("haystack_session_ids", [])]
        dates = [str(value) for value in item.get("haystack_dates", [])]
        answer_session_ids = [str(value) for value in item.get("answer_session_ids", [])]
        messages: list[Message] = []
        expected_source_ids: list[str] = []
        source_sessions_by_id: dict[str, str] = {}
        seen_message_ids: set[str] = set()
        haystack_sessions = item.get("haystack_sessions", [])
        for session_index, session in enumerate(haystack_sessions, start=1):
            session_id = (
                session_ids[session_index - 1]
                if session_index - 1 < len(session_ids)
                else f"session_{session_index}"
            )
            date = dates[session_index - 1] if session_index - 1 < len(dates) else ""
            if not isinstance(session, list):
                continue
            for turn_index, turn in enumerate(session, start=1):
                if not isinstance(turn, dict):
                    continue
                content = str(turn.get("content") or "").strip()
                if not content:
                    continue
                role = _role_from_text(str(turn.get("role") or "user"))
                message_id = f"{case_id}:{_safe_id(session_id)}:{turn_index:03d}"
                if message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)
                source_sessions_by_id[message_id] = session_id
                if turn.get("has_answer") is True:
                    expected_source_ids.append(message_id)
                dated_content = _with_date(content, date)
                messages.append(
                    Message(
                        id=message_id,
                        session_id=case_id,
                        role=role,
                        content=dated_content,
                        metadata={"benchmark_session_id": session_id, "benchmark_date": date},
                        token_count=tokenizer.count(dated_content),
                    )
                )
        if not expected_source_ids and answer_session_ids:
            expected_source_ids = [
                message.id
                for message in messages
                if source_sessions_by_id.get(message.id) in set(answer_session_ids)
            ]
        cases.append(
            PublicBenchmarkCase(
                benchmark="longmemeval",
                case=EvalCase(
                    case_id=case_id,
                    conversation=[
                        MessageCreate(
                            role=message.role,
                            content=message.content,
                            metadata=message.metadata,
                        )
                        for message in messages
                    ],
                    question=question,
                    expected_facts=[answer],
                    required_sources=expected_source_ids,
                ),
                messages=messages,
                expected_answer=answer,
                expected_source_ids=expected_source_ids,
                expected_session_ids=answer_session_ids,
                source_sessions_by_id=source_sessions_by_id,
                question_type=str(item.get("question_type") or "") or None,
            )
        )
    return cases


def _load_locomo(data: Any) -> list[PublicBenchmarkCase]:
    if not isinstance(data, list):
        raise ValueError("LoCoMo data must be a JSON list")
    tokenizer = TokenEstimator()
    cases: list[PublicBenchmarkCase] = []
    for sample_index, sample in enumerate(data, start=1):
        if not isinstance(sample, dict):
            continue
        sample_id = str(sample.get("sample_id") or f"locomo_{sample_index:02d}")
        messages, source_sessions_by_id = _locomo_messages(sample, sample_id, tokenizer)
        for qa_index, qa in enumerate(sample.get("qa", []), start=1):
            if not isinstance(qa, dict):
                continue
            question = str(qa.get("question") or "").strip()
            answer = _answer_to_text(qa.get("answer"))
            if not question or not answer:
                continue
            case_id = f"{sample_id}_qa_{qa_index:03d}"
            case_messages = _with_case_message_ids(case_id, messages)
            case_source_sessions_by_id = {
                f"{case_id}:{source_id}": session_id
                for source_id, session_id in source_sessions_by_id.items()
            }
            evidence_ids = [
                f"{case_id}:{sample_id}:{value}" for value in _list_of_text(qa.get("evidence"))
            ]
            evidence_sessions = sorted(
                {
                    case_source_sessions_by_id[source_id]
                    for source_id in evidence_ids
                    if source_id in case_source_sessions_by_id
                }
            )
            cases.append(
                PublicBenchmarkCase(
                    benchmark="locomo",
                    case=EvalCase(
                        case_id=case_id,
                        conversation=[
                            MessageCreate(
                                role=message.role,
                                content=message.content,
                                metadata=message.metadata,
                            )
                            for message in case_messages
                        ],
                        question=question,
                        expected_facts=[answer],
                        required_sources=evidence_ids,
                    ),
                    messages=case_messages,
                    expected_answer=answer,
                    expected_source_ids=evidence_ids,
                    expected_session_ids=evidence_sessions,
                    source_sessions_by_id=case_source_sessions_by_id,
                    question_type=str(qa.get("category") or "") or None,
                )
            )
    return cases


def _locomo_messages(
    sample: dict[str, Any],
    sample_id: str,
    tokenizer: TokenEstimator,
) -> tuple[list[Message], dict[str, str]]:
    conversation = sample.get("conversation", {})
    if not isinstance(conversation, dict):
        return [], {}
    session_keys = sorted(
        (key for key, value in conversation.items() if re.fullmatch(r"session_\d+", key)),
        key=lambda key: int(key.rsplit("_", 1)[1]),
    )
    messages: list[Message] = []
    source_sessions_by_id: dict[str, str] = {}
    for session_key in session_keys:
        date = str(conversation.get(f"{session_key}_date_time") or "")
        turns = conversation.get(session_key, [])
        if not isinstance(turns, list):
            continue
        for turn_index, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                continue
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            speaker = str(turn.get("speaker") or "").strip()
            dia_id = str(turn.get("dia_id") or f"D{session_key.rsplit('_', 1)[1]}:{turn_index}")
            message_id = f"{sample_id}:{dia_id}"
            session_id = session_key.replace("session_", "D")
            source_sessions_by_id[message_id] = session_id
            content = _with_date(f"{speaker}: {text}" if speaker else text, date)
            messages.append(
                Message(
                    id=message_id,
                    session_id=sample_id,
                    role=Role.USER,
                    content=content,
                    metadata={
                        "benchmark_session_id": session_id,
                        "benchmark_date": date,
                        "benchmark_dialog_id": dia_id,
                    },
                    token_count=tokenizer.count(content),
                )
            )
    return messages, source_sessions_by_id


def _with_case_message_ids(case_id: str, messages: list[Message]) -> list[Message]:
    return [
        message.model_copy(update={"id": f"{case_id}:{message.id}", "session_id": case_id})
        for message in messages
    ]


def _extract_item_metrics(
    store: Any, session_id: str, expected_source_ids: list[str]
) -> dict[str, Any]:
    """Extract item-level retrieval metrics from traces."""
    all_items = store.list_items(session_id)
    item_count_in_session = len(all_items)

    traces = store.list_traces(session_id)
    item_trace = next(
        (t for t in traces if t.event_type == "item_retrieval"), None
    )
    if item_trace is None:
        return {
            "item_source_overlap_at_k": None,
            "item_promoted_evidence_count": 0,
            "item_evidence_budget_dropped": 0,
            "source_not_indexed": False,
            "item_hit_item_ids": [],
            "item_hit_source_ids": [],
            "item_count_in_session": item_count_in_session,
        }
    payload = item_trace.payload
    hit_source_ids = payload.get("promoted_source_message_ids", [])
    item_hit_ids = payload.get("item_hit_ids", hit_source_ids)
    promoted_count = payload.get("promoted_evidence_count", 0)
    budget_dropped = payload.get("item_evidence_budget_dropped", 0)

    overlap = bool(set(hit_source_ids) & set(expected_source_ids))

    all_indexed_sources: set[str] = set()
    for page in store.list_pages(session_id):
        all_indexed_sources.update(page.source_message_ids)
    for item in all_items:
        all_indexed_sources.update(item.source_message_ids)
    source_not_indexed = not bool(set(expected_source_ids) & all_indexed_sources)

    return {
        "item_source_overlap_at_k": overlap,
        "item_promoted_evidence_count": promoted_count,
        "item_evidence_budget_dropped": budget_dropped,
        "source_not_indexed": source_not_indexed,
        "item_hit_item_ids": item_hit_ids,
        "item_hit_source_ids": hit_source_ids,
        "item_count_in_session": item_count_in_session,
    }


def _to_public_result(
    public_case: PublicBenchmarkCase,
    baseline: str,
    answer: str,
    answer_mode: str,
    source_ids: list[str],
    verdict: str,
    reasoning: str,
    expected_present: list[str],
    expected_missing: list[str],
    output: BaselineOutput,
    latency_ms: int,
    item_metrics: dict[str, Any] | None = None,
    baseline_verdict: str | None = None,
    movement_baseline_source: str | None = None,
) -> PublicBenchmarkResult:
    source_set = set(source_ids)
    expected_source_set = set(public_case.expected_source_ids)
    source_overlap = sorted(source_set & expected_source_set)
    missing_source_ids = sorted(expected_source_set - source_set)
    source_recall = len(source_overlap) / len(expected_source_set) if expected_source_set else None
    candidate_source_set = set(output.retrieval_candidate_source_ids)
    candidate_source_overlap = sorted(candidate_source_set & expected_source_set)
    candidate_is_message = output.retrieval_candidate_unit == "message"
    page_candidate_source_set = set(output.page_candidate_source_ids)
    page_candidate_source_overlap = sorted(page_candidate_source_set & expected_source_set)
    source_session_ids = sorted(
        {
            public_case.source_sessions_by_id[source_id]
            for source_id in source_ids
            if source_id in public_case.source_sessions_by_id
        }
    )
    retrieval_candidate_session_ids = sorted(
        {
            public_case.source_sessions_by_id[source_id]
            for source_id in output.retrieval_candidate_source_ids
            if source_id in public_case.source_sessions_by_id
        }
    )
    page_candidate_session_ids = sorted(
        {
            public_case.source_sessions_by_id[source_id]
            for source_id in output.page_candidate_source_ids
            if source_id in public_case.source_sessions_by_id
        }
    )
    expected_session_set = set(public_case.expected_session_ids)
    session_overlap = sorted(set(source_session_ids) & expected_session_set)
    missing_session_ids = sorted(expected_session_set - set(source_session_ids))
    candidate_session_overlap = sorted(set(retrieval_candidate_session_ids) & expected_session_set)
    page_candidate_session_overlap = sorted(set(page_candidate_session_ids) & expected_session_set)
    session_recall = (
        len(session_overlap) / len(expected_session_set) if expected_session_set else None
    )
    dropped_relevant_page_ids = sorted(
        page_id
        for page_id, page_source_ids in output.dropped_page_source_ids.items()
        if set(page_source_ids) & expected_source_set
    )
    case_diagnostics = build_case_diagnostics(
        benchmark=public_case.benchmark,
        baseline=baseline,
        case_id=public_case.case.case_id,
        memory_arch=output.memory_arch,
        answer=answer,
        answer_mode=answer_mode,
        verdict=verdict,
        reasoning=reasoning,
        expected_source_ids=public_case.expected_source_ids,
        retrieval_candidate_source_ids=output.retrieval_candidate_source_ids,
        episode_candidate_message_ids=output.episode_candidate_message_ids,
        planned_evidence_message_ids=output.planned_evidence_message_ids,
        source_ids=source_ids,
        v3_context=output.v3_context,
        v3_diagnostics=output.v3_diagnostics,
        kernel_trace_events=output.kernel_trace_events,
        baseline_verdict=baseline_verdict,
        movement_baseline_source=movement_baseline_source,
    )
    return PublicBenchmarkResult(
        benchmark=public_case.benchmark,
        baseline=baseline,
        case_id=public_case.case.case_id,
        question=public_case.case.question,
        expected_answer=public_case.expected_answer,
        answer=answer,
        answer_mode=answer_mode,
        verdict=verdict,
        reasoning=reasoning,
        expected_present=expected_present,
        expected_missing=expected_missing,
        source_ids=source_ids,
        expected_source_ids=public_case.expected_source_ids,
        source_overlap_ids=source_overlap,
        missing_source_ids=missing_source_ids,
        retrieval_candidate_top_k=output.retrieval_candidate_top_k,
        retrieval_candidate_unit=output.retrieval_candidate_unit,
        retrieval_candidate_page_ids=output.retrieval_candidate_page_ids,
        retrieval_candidate_source_ids=output.retrieval_candidate_source_ids,
        retrieval_candidate_session_ids=retrieval_candidate_session_ids,
        page_candidate_top_k=output.page_candidate_top_k,
        page_candidate_page_ids=output.page_candidate_page_ids,
        page_candidate_source_ids=output.page_candidate_source_ids,
        page_candidate_session_ids=page_candidate_session_ids,
        source_recall=source_recall,
        source_hit=bool(source_overlap) if expected_source_set else None,
        source_hit_at_k=(
            bool(candidate_source_overlap)
            if expected_source_set
            and output.retrieval_candidate_top_k is not None
            and candidate_is_message
            else None
        ),
        page_source_overlap_at_k=(
            bool(page_candidate_source_overlap)
            if expected_source_set and output.page_candidate_top_k is not None
            else None
        ),
        expected_session_ids=public_case.expected_session_ids,
        source_session_ids=source_session_ids,
        session_overlap_ids=session_overlap,
        missing_session_ids=missing_session_ids,
        session_recall=session_recall,
        session_hit=bool(session_overlap) if expected_session_set else None,
        session_hit_at_k=(
            bool(candidate_session_overlap)
            if expected_session_set
            and output.retrieval_candidate_top_k is not None
            and candidate_is_message
            else None
        ),
        page_session_overlap_at_k=(
            bool(page_candidate_session_overlap)
            if expected_session_set and output.page_candidate_top_k is not None
            else None
        ),
        context_tokens=output.context_tokens,
        page_count=output.page_count,
        loaded_pages=output.loaded_pages,
        dropped_pages=output.dropped_pages,
        page_type_counts=output.page_type_counts,
        page_source_counts=output.page_source_counts,
        page_summary_token_counts=output.page_summary_token_counts,
        retrieved_page_ids=output.retrieved_page_ids,
        dropped_page_reasons=output.dropped_page_reasons,
        dropped_relevant_page_ids=dropped_relevant_page_ids,
        dropped_relevant_page_count=len(dropped_relevant_page_ids),
        superseded_source_recovered=output.superseded_source_recovered,
        candidate_budget_dropped=output.candidate_budget_dropped,
        active_overlap_not_top5=output.active_overlap_not_top5,
        latency_ms=latency_ms,
        question_type=public_case.question_type,
        episode_source_hit_at_10=output.episode_source_hit_at_10,
        item_source_hit_at_10=output.item_source_hit_at_10,
        planned_evidence_source_hit_at_5=output.planned_evidence_source_hit_at_5,
        budget_dropped_relevant=output.budget_dropped_relevant,
        source_not_indexed=(
            output.source_not_indexed or (item_metrics or {}).get("source_not_indexed", False)
        ),
        indexed_source_ids=output.indexed_source_ids,
        item_candidate_source_ids=output.item_candidate_source_ids,
        episode_candidate_message_ids=output.episode_candidate_message_ids,
        planned_evidence_message_ids=output.planned_evidence_message_ids,
        item_source_overlap_at_k=(item_metrics or {}).get("item_source_overlap_at_k"),
        item_promoted_evidence_count=(item_metrics or {}).get("item_promoted_evidence_count", 0),
        item_evidence_budget_dropped=(item_metrics or {}).get("item_evidence_budget_dropped", 0),
        item_hit_item_ids=(item_metrics or {}).get("item_hit_item_ids", []),
        item_hit_source_ids=(item_metrics or {}).get("item_hit_source_ids", []),
        item_count_in_session=(item_metrics or {}).get("item_count_in_session", 0),
        memory_arch=output.memory_arch,
        v3_context=output.v3_context,
        v3_layer_counts=output.v3_layer_counts,
        v3_budget_decisions=output.v3_budget_decisions,
        v3_diagnostics=output.v3_diagnostics,
        v3_component_accounting=output.v3_component_accounting,
        v3_final_context_trace=output.v3_final_context_trace,
        v3_component_token_totals=output.v3_component_token_totals,
        v3_component_drop_counts=output.v3_component_drop_counts,
        locomo_neighbor_diagnostics=output.locomo_neighbor_diagnostics,
        kernel_trace_events=output.kernel_trace_events,
        case_diagnostics=case_diagnostics,
        failure_class=str(case_diagnostics["failure_class"]),
        movement_status=str(case_diagnostics["movement_status"]),
        answer_support_status=str(case_diagnostics["answer_support_status"]),
        judge_status=str(case_diagnostics["judge_status"]),
    )


def _role_from_text(value: str) -> Role:
    normalized = value.strip().lower()
    if normalized == "assistant":
        return Role.ASSISTANT
    if normalized == "system":
        return Role.SYSTEM
    if normalized == "tool":
        return Role.TOOL
    return Role.USER


def _answer_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value).strip()


def _list_of_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _with_date(content: str, date: str) -> str:
    return f"[{date}] {content}" if date else content


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value)


def _answer_evidence_from_output(output: BaselineOutput) -> list[AnswerEvidence]:
    trace_by_source_id = _final_trace_by_source_id(output.v3_final_context_trace)
    evidence: list[AnswerEvidence] = []
    for index, (source_id, text) in enumerate(sorted(output.sources.items()), start=1):
        trace = trace_by_source_id.get(source_id, {})
        metadata = trace.get("metadata") if isinstance(trace.get("metadata"), dict) else {}
        evidence.append(
            AnswerEvidence(
                evidence_id=source_id,
                text=text,
                component=str(trace.get("component") or "context"),
                source_ids=[source_id],
                session_id=_string_or_none(metadata.get("benchmark_session_id")),
                date=_string_or_none(metadata.get("benchmark_date")) or _date_from_text(text),
                rendered_index=(
                    trace.get("rendered_index")
                    if isinstance(trace.get("rendered_index"), int)
                    else index
                ),
                estimated_tokens=(
                    trace.get("estimated_tokens")
                    if isinstance(trace.get("estimated_tokens"), int)
                    else None
                ),
                metadata={str(key): value for key, value in metadata.items()},
            )
        )
    evidence.sort(
        key=lambda item: (
            item.rendered_index is None,
            item.rendered_index if item.rendered_index is not None else 10_000_000,
            item.evidence_id,
        )
    )
    return evidence


def _public_projected_answer_with_citations(answer: str, sources: dict[str, str]) -> str:
    if not sources:
        return "Insufficient retrieved evidence to answer with source citations."
    if _has_any_citation(answer):
        return answer
    citations = " ".join(f"[{source_id}]" for source_id in sorted(sources))
    return f"{answer} {citations}".strip()


def _has_any_citation(answer: str) -> bool:
    return bool(re.search(r"\[[^\]\s]+\]", answer))


def _final_trace_by_source_id(trace: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in trace:
        if row.get("dropped") is True:
            continue
        for source_id in _source_ids_from_trace_row(row):
            rows.setdefault(source_id, row)
    return rows


def _source_ids_from_trace_row(row: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    source_ids = row.get("source_ids")
    if isinstance(source_ids, str):
        ids.append(source_ids)
    elif isinstance(source_ids, list):
        ids.extend(item for item in source_ids if isinstance(item, str))
    refs = row.get("source_refs")
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict) and isinstance(ref.get("source_id"), str):
                ids.append(ref["source_id"])
    return _dedupe(ids)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _date_from_text(text: str) -> str | None:
    match = re.match(r"^\[([^\]]+)\]", text.strip())
    return match.group(1) if match else None


class PublicAnswerer:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.chat_api_key
        if not api_key:
            raise ValueError(f"{settings.chat_api_key_name} required for public benchmark answerer")
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

    def answer(self, question: str, sources: dict[str, str] | list[AnswerEvidence]) -> str:
        evidence = _coerce_answer_evidence(sources)
        if not evidence:
            return "Insufficient retrieved evidence to answer with source citations."
        allowed_ids = ", ".join(item.evidence_id for item in evidence)
        context = json.dumps(
            [
                {
                    "id": item.evidence_id,
                    "component": item.component,
                    "source_ids": item.source_ids,
                    "session_id": item.session_id,
                    "date": item.date,
                    "rendered_index": item.rendered_index,
                    "estimated_tokens": item.estimated_tokens,
                    "metadata": item.metadata,
                    "text": item.text,
                }
                for item in evidence
            ],
            ensure_ascii=False,
            indent=2,
        )
        response = self.llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You answer memory benchmark questions using only the provided structured "
                        "evidence. Allowed citation IDs: "
                        f"{allowed_ids}. You must cite every factual claim with exact [id] "
                        "citations from the allowed IDs. Do not invent citation IDs. If the "
                        "evidence is insufficient, answer exactly: Insufficient retrieved "
                        "evidence to answer with source citations. For temporal or session "
                        "questions, use the evidence date and session_id metadata. relative "
                        "temporal phrases in evidence, such as 'last week' or 'yesterday', "
                        "are usable when anchored by evidence date metadata; cite the "
                        "anchoring evidence instead of refusing only because the exact "
                        "calendar date is implicit. If evidence is relevant but incomplete, "
                        "give a supported partial answer with a clear limitation and "
                        "citations. reserve the exact refusal for cases with no relevant "
                        "retrieved evidence. For yes/no preference or career questions, "
                        "when cited evidence supports an alternative plan, career path, "
                        "preference, or non-career interest, answer likely yes or likely no "
                        "with that limitation instead of refusing only because the evidence "
                        "does not literally mention the option in the question. If the "
                        "question asks whether someone would pursue option X, and evidence "
                        "shows they are pursuing a different option Y, a cautious likely no "
                        "answer is supported when every claim is cited."
                    )
                ),
                HumanMessage(content=f"Retrieved evidence:\n{context}\n\nQuestion: {question}"),
            ]
        )
        return response.content if isinstance(response.content, str) else str(response.content)


def _coerce_answer_evidence(
    sources: dict[str, str] | list[AnswerEvidence],
) -> list[AnswerEvidence]:
    if isinstance(sources, dict):
        return [
            AnswerEvidence(evidence_id=source_id, text=text, source_ids=[source_id])
            for source_id, text in sorted(sources.items())
        ]
    return sources
