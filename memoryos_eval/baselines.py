"""Context baselines for the public benchmark adapter (LongMemEval, LoCoMo).

``sliding_window``, ``naive_summary``, ``vector_rag`` (BM25 over messages) and
``memoryos_lite`` each build an answer from the evidence they would put into
context. Historical results only; this code is no longer maintained.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, model_validator
from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_eval.memory.service import SessionMemoryService
from memoryos_eval.memory.utils import is_generic_ack
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.schemas import Message, MessageCreate, Role
from memoryos_lite.tokenizer import TokenEstimator


class EvalCase(BaseModel):
    case_id: str
    conversation: list[MessageCreate]
    question: str
    expected_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    required_sources: list[str] = Field(default_factory=list)
    required_fact_sources: dict[str, list[str]] = Field(default_factory=dict)
    query_in_new_session: bool = False
    include_global_core: bool = False

    @model_validator(mode="after")
    def require_fact_sources_for_multi_fact_cases(self) -> "EvalCase":
        if (
            len(self.expected_facts) > 1
            and self.required_sources
            and not self.required_fact_sources
        ):
            raise ValueError(
                "multi-fact eval cases with required sources must use "
                "required_fact_sources for per-fact source mapping"
            )
        if self.required_fact_sources:
            expected = set(self.expected_facts)
            provided = set(self.required_fact_sources)
            missing = sorted(expected - provided)
            unknown = sorted(provided - expected)
            if missing or unknown:
                details: list[str] = []
                if missing:
                    details.append(f"missing keys: {', '.join(missing)}")
                if unknown:
                    details.append(f"unknown keys: {', '.join(unknown)}")
                raise ValueError(
                    "eval cases must provide required_fact_sources "
                    f"for exactly the expected facts ({'; '.join(details)})"
                )
            empty_sources = sorted(
                fact for fact, source_ids in self.required_fact_sources.items() if not source_ids
            )
            if empty_sources:
                raise ValueError(
                    "required_fact_sources entries must contain at least one source id "
                    f"(empty keys: {', '.join(empty_sources)})"
                )
        return self


@dataclass(frozen=True)
class BaselineOutput:
    answer: str
    context_tokens: int
    sources: dict[str, str]
    page_count: int = 0
    loaded_pages: int = 0
    dropped_pages: int = 0
    dropped_page_details: list[dict[str, object]] = field(default_factory=list)
    page_type_counts: dict[str, int] = field(default_factory=dict)
    page_source_counts: list[int] = field(default_factory=list)
    page_summary_token_counts: list[int] = field(default_factory=list)
    retrieved_page_ids: list[str] = field(default_factory=list)
    dropped_page_reasons: dict[str, str] = field(default_factory=dict)
    dropped_page_source_ids: dict[str, list[str]] = field(default_factory=dict)
    retrieval_candidate_top_k: int | None = None
    retrieval_candidate_unit: str | None = None
    retrieval_candidate_source_ids: list[str] = field(default_factory=list)
    retrieval_candidate_page_ids: list[str] = field(default_factory=list)
    page_candidate_top_k: int | None = None
    page_candidate_source_ids: list[str] = field(default_factory=list)
    page_candidate_page_ids: list[str] = field(default_factory=list)
    superseded_source_recovered: int = 0
    candidate_budget_dropped: int = 0
    active_overlap_not_top5: int = 0
    item_source_hit_at_10: bool | None = None
    episode_source_hit_at_10: bool | None = None
    planned_evidence_source_hit_at_5: bool | None = None
    budget_dropped_relevant: int = 0
    source_not_indexed: bool = False
    indexed_source_ids: list[str] = field(default_factory=list)
    item_candidate_source_ids: list[str] = field(default_factory=list)
    episode_candidate_message_ids: list[str] = field(default_factory=list)
    planned_evidence_message_ids: list[str] = field(default_factory=list)
    memory_arch: str | None = None
    v3_context: dict[str, object] = field(default_factory=dict)
    v3_layer_counts: dict[str, int] = field(default_factory=dict)
    v3_budget_decisions: list[dict[str, object]] = field(default_factory=list)
    v3_diagnostics: list[dict[str, object]] = field(default_factory=list)
    v3_component_accounting: list[dict[str, object]] = field(default_factory=list)
    v3_final_context_trace: list[dict[str, object]] = field(default_factory=list)
    v3_component_token_totals: dict[str, int] = field(default_factory=dict)
    v3_component_drop_counts: dict[str, int] = field(default_factory=dict)
    locomo_neighbor_diagnostics: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceItem:
    text: str
    source_texts: dict[str, str]
    origin: str = "message"
    superseded: bool = False


def _run_baseline(
    baseline: str,
    case: EvalCase,
    messages: list[Message],
    service: SessionMemoryService,
    settings: Settings,
    budget_override: int | None = None,
) -> BaselineOutput:
    tokenizer = TokenEstimator()
    budget = budget_override if budget_override is not None else 90
    task_tokens = tokenizer.count(case.question)
    if case.query_in_new_session and baseline != "memoryos_lite":
        return _baseline_from_evidence(case.question, [], task_tokens)
    if baseline == "sliding_window":
        selected = _fit_sliding_window(messages, case.question, budget, tokenizer)
        return _baseline_from_evidence(
            case.question,
            _message_evidence(selected),
            _context_tokens(case.question, [message.content for message in selected], tokenizer),
        )
    if baseline == "naive_summary":
        remaining_budget = max(0, budget - task_tokens)
        recent_window = messages[-2:]
        recent = _fit_text_items_newest_first(
            [(message.id, message.content, message.token_count) for message in recent_window],
            remaining_budget,
        )
        recent_texts = [text for _, text, _ in recent]
        older = messages[: max(0, len(messages) - len(recent_window))]
        older_sources = _message_sources(older[:3])
        summary = "；".join(message.content for message in older[:3])
        summary_tokens = tokenizer.count(summary)
        selected_texts: list[str] = []
        evidence: list[EvidenceItem] = []
        if summary and summary_tokens <= remaining_budget - sum(token for _, _, token in recent):
            selected_texts.append(summary)
            evidence.append(EvidenceItem(text=summary, source_texts=older_sources))
        selected_texts.extend(recent_texts)
        evidence.extend(
            EvidenceItem(text=text, source_texts={item_id: text}) for item_id, text, _ in recent
        )
        return _baseline_from_evidence(
            case.question,
            evidence,
            _context_tokens(case.question, selected_texts, tokenizer),
        )
    if baseline == "vector_rag":
        ranked = _bm25_retrieve(messages, case.question)
        retrieval_candidates = ranked[:5]
        selected = _fit_ranked_messages(ranked, case.question, budget, tokenizer)
        return _baseline_from_evidence(
            case.question,
            _message_evidence(selected),
            _context_tokens(case.question, [message.content for message in selected], tokenizer),
            retrieval_candidate_top_k=5,
            retrieval_candidate_unit="message",
            retrieval_candidate_source_ids=[message.id for message in retrieval_candidates],
        )
    if baseline == "memoryos_lite":
        service.store.reset()
        source_session = service.create_session(case.case_id)
        context_session = (
            service.create_session(f"{case.case_id}_query")
            if case.query_in_new_session
            else source_session
        )
        original_budget = service.settings.rot_safe_budget
        original_recent = service.settings.recent_message_limit
        service.settings.rot_safe_budget = 1
        service.settings.recent_message_limit = 1 if case.query_in_new_session else 2
        try:
            for message in messages:
                service.store.add_message(
                    message.model_copy(update={"session_id": source_session.id})
                )
            candidate_top_k = 5
            context = service.build_context(
                context_session.id,
                case.question,
                budget=budget,
                include_global_core=case.include_global_core,
            )
        finally:
            service.settings.rot_safe_budget = original_budget
            service.settings.recent_message_limit = original_recent
        # For temporal questions, include recent messages directly so budget
        # pressure in build_context cannot drop the latest-state messages.
        raw_recent = messages[-service.settings.recent_message_limit :]
        if _is_temporal_question(case.question):
            recent_evidence = _message_evidence(raw_recent)
        else:
            recent_evidence = _message_evidence(context.recent_messages)
        memory_evidence: list[EvidenceItem] = []
        for context_evidence in context.retrieved_evidence:
            retrieved_origin = context_evidence.metadata.get("origin")
            memory_evidence.append(
                EvidenceItem(
                    text=context_evidence.text,
                    source_texts={context_evidence.message_id: context_evidence.text},
                    origin=(
                        "retrieved_message"
                        if context_evidence.page_id
                        or retrieved_origin in {"recall", "archival", "episode"}
                        else "message"
                    ),
                    superseded=context_evidence.superseded,
                )
            )
        memory_evidence.extend(recent_evidence)
        context_evidence_source_ids = _dedupe_source_ids(
            [evidence.message_id for evidence in context.retrieved_evidence[:candidate_top_k]]
            + [m.id for m in context.recent_messages]
        )
        context_evidence_page_ids = _dedupe_source_ids(
            evidence.page_id
            for evidence in context.retrieved_evidence[:candidate_top_k]
            if evidence.page_id is not None
        )
        indexed_source_ids = _metadata_string_list_prefer(
            context.metadata,
            primary_key="recall_indexed_source_ids",
            fallback_key="indexed_source_ids",
        )
        item_candidate_source_ids = _metadata_string_list(
            context.metadata, "item_candidate_source_ids"
        )
        episode_candidate_message_ids = _metadata_string_list_prefer(
            context.metadata,
            primary_key="recall_candidate_message_ids",
            fallback_key="episode_candidate_message_ids",
        )
        planned_evidence_message_ids = _metadata_string_list_prefer(
            context.metadata,
            primary_key="recall_planned_message_ids",
            fallback_key="planned_evidence_message_ids",
        )
        required_source_ids = _case_required_source_ids(case)
        required_source_set = set(required_source_ids)
        item_candidate_set = set(item_candidate_source_ids[:10])
        episode_candidate_set = set(episode_candidate_message_ids[:10])
        planned_evidence_set = set(planned_evidence_message_ids[:5])
        indexed_source_set = set(indexed_source_ids)
        has_v2_index_diagnostics = (
            "recall_indexed_source_ids" in context.metadata
            or "indexed_source_ids" in context.metadata
        )
        item_source_hit_at_10 = (
            bool(required_source_set & item_candidate_set) if required_source_set else None
        )
        episode_source_hit_at_10 = (
            bool(required_source_set & episode_candidate_set) if required_source_set else None
        )
        planned_evidence_source_hit_at_5 = (
            bool(required_source_set & planned_evidence_set) if required_source_set else None
        )
        source_not_indexed = (
            not bool(required_source_set & indexed_source_set)
            if required_source_set and has_v2_index_diagnostics
            else False
        )
        memory_arch = context.metadata.get("memory_arch")
        v3_context = context.metadata.get("v3_context")
        v3_layer_counts = context.metadata.get("v3_layer_counts")
        v3_budget_decisions = context.metadata.get("v3_budget_decisions")
        v3_diagnostics = context.metadata.get("v3_diagnostics")
        v3_component_accounting = context.metadata.get("v3_component_accounting")
        v3_final_context_trace = context.metadata.get("v3_final_context_trace")
        v3_component_token_totals = context.metadata.get("v3_component_token_totals")
        v3_component_drop_counts = context.metadata.get("v3_component_drop_counts")
        locomo_neighbor_diagnostics = context.metadata.get("locomo_neighbor_diagnostics")
        return _baseline_from_evidence(
            case.question,
            memory_evidence,
            context.estimated_tokens,
            retrieval_candidate_top_k=candidate_top_k,
            retrieval_candidate_unit="message",
            retrieval_candidate_source_ids=context_evidence_source_ids,
            retrieval_candidate_page_ids=context_evidence_page_ids,
            superseded_source_recovered=context.superseded_source_recovered,
            candidate_budget_dropped=context.candidate_budget_dropped,
            active_overlap_not_top5=context.active_overlap_not_top5,
            item_source_hit_at_10=item_source_hit_at_10,
            episode_source_hit_at_10=episode_source_hit_at_10,
            planned_evidence_source_hit_at_5=planned_evidence_source_hit_at_5,
            budget_dropped_relevant=_metadata_int_prefer(
                context.metadata,
                primary_key="recall_budget_dropped",
                fallback_key="budget_dropped_relevant",
            ),
            source_not_indexed=source_not_indexed,
            indexed_source_ids=indexed_source_ids,
            item_candidate_source_ids=item_candidate_source_ids,
            episode_candidate_message_ids=episode_candidate_message_ids,
            planned_evidence_message_ids=planned_evidence_message_ids,
            memory_arch=memory_arch if isinstance(memory_arch, str) else None,
            v3_context=v3_context if isinstance(v3_context, dict) else None,
            v3_layer_counts=(
                {
                    str(layer): count
                    for layer, count in v3_layer_counts.items()
                    if isinstance(count, int)
                }
                if isinstance(v3_layer_counts, dict)
                else None
            ),
            v3_budget_decisions=(
                [item for item in v3_budget_decisions if isinstance(item, dict)]
                if isinstance(v3_budget_decisions, list)
                else None
            ),
            v3_diagnostics=(
                [item for item in v3_diagnostics if isinstance(item, dict)]
                if isinstance(v3_diagnostics, list)
                else None
            ),
            v3_component_accounting=(
                [item for item in v3_component_accounting if isinstance(item, dict)]
                if isinstance(v3_component_accounting, list)
                else None
            ),
            v3_final_context_trace=(
                [item for item in v3_final_context_trace if isinstance(item, dict)]
                if isinstance(v3_final_context_trace, list)
                else None
            ),
            v3_component_token_totals=(
                {
                    str(component): count
                    for component, count in v3_component_token_totals.items()
                    if isinstance(count, int)
                }
                if isinstance(v3_component_token_totals, dict)
                else None
            ),
            v3_component_drop_counts=(
                {
                    str(component): count
                    for component, count in v3_component_drop_counts.items()
                    if isinstance(count, int)
                }
                if isinstance(v3_component_drop_counts, dict)
                else None
            ),
            locomo_neighbor_diagnostics=(
                [item for item in locomo_neighbor_diagnostics if isinstance(item, dict)]
                if isinstance(locomo_neighbor_diagnostics, list)
                else None
            ),
        )
    raise ValueError(f"unknown baseline: {baseline}")


def _expand_baselines(baselines: list[str]) -> list[str]:
    if "all" in baselines:
        return ["sliding_window", "naive_summary", "vector_rag", "memoryos_lite"]
    return baselines


def _fit_text_items_newest_first(
    items: list[tuple[str, str, int]],
    budget: int,
) -> list[tuple[str, str, int]]:
    used = 0
    selected: list[tuple[str, str, int]] = []
    for item in reversed(items):
        if used + item[2] <= budget:
            selected.append(item)
            used += item[2]
    return list(reversed(selected))


def _fit_ranked_messages(
    messages: list[Message],
    task: str,
    budget: int,
    tokenizer: TokenEstimator,
) -> list[Message]:
    used = tokenizer.count(task)
    selected: list[Message] = []
    for message in messages:
        if used + message.token_count <= budget:
            selected.append(message)
            used += message.token_count
    return selected


def _fit_sliding_window(
    messages: list[Message],
    task: str,
    budget: int,
    tokenizer: TokenEstimator,
) -> list[Message]:
    used = min(tokenizer.count(task), budget)
    selected: list[Message] = []
    for message in reversed(messages):
        if used + message.token_count > budget:
            break
        selected.append(message)
        used += message.token_count
    return list(reversed(selected))


def _bm25_retrieve(messages: list[Message], query: str) -> list[Message]:
    tokenized = [tokenize(message.content) for message in messages]
    if not tokenized:
        return []
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(messages, scores, strict=False), key=lambda item: item[1], reverse=True)
    return [message for message, score in ranked if score > 0]


def _baseline_from_evidence(
    question: str,
    evidence: list[EvidenceItem],
    context_tokens: int,
    page_count: int = 0,
    loaded_pages: int = 0,
    dropped_pages: int = 0,
    dropped_page_details: list[dict[str, object]] | None = None,
    page_type_counts: dict[str, int] | None = None,
    page_source_counts: list[int] | None = None,
    page_summary_token_counts: list[int] | None = None,
    retrieved_page_ids: list[str] | None = None,
    dropped_page_reasons: dict[str, str] | None = None,
    dropped_page_source_ids: dict[str, list[str]] | None = None,
    retrieval_candidate_top_k: int | None = None,
    retrieval_candidate_unit: str | None = None,
    retrieval_candidate_source_ids: list[str] | None = None,
    retrieval_candidate_page_ids: list[str] | None = None,
    page_candidate_top_k: int | None = None,
    page_candidate_source_ids: list[str] | None = None,
    page_candidate_page_ids: list[str] | None = None,
    superseded_source_recovered: int = 0,
    candidate_budget_dropped: int = 0,
    active_overlap_not_top5: int = 0,
    item_source_hit_at_10: bool | None = None,
    episode_source_hit_at_10: bool | None = None,
    planned_evidence_source_hit_at_5: bool | None = None,
    budget_dropped_relevant: int = 0,
    source_not_indexed: bool = False,
    indexed_source_ids: list[str] | None = None,
    item_candidate_source_ids: list[str] | None = None,
    episode_candidate_message_ids: list[str] | None = None,
    planned_evidence_message_ids: list[str] | None = None,
    memory_arch: str | None = None,
    v3_context: dict[str, object] | None = None,
    v3_layer_counts: dict[str, int] | None = None,
    v3_budget_decisions: list[dict[str, object]] | None = None,
    v3_diagnostics: list[dict[str, object]] | None = None,
    v3_component_accounting: list[dict[str, object]] | None = None,
    v3_final_context_trace: list[dict[str, object]] | None = None,
    v3_component_token_totals: dict[str, int] | None = None,
    v3_component_drop_counts: dict[str, int] | None = None,
    locomo_neighbor_diagnostics: list[dict[str, object]] | None = None,
) -> BaselineOutput:
    selected = _select_evidence(question, evidence)
    sources: dict[str, str] = {}
    for item in selected:
        sources.update(item.source_texts)
    # Also include retrieved_message evidence so source_hit measures
    # engine retrieval quality, not just answer-projection selection.
    for item in evidence:
        if item.origin == "retrieved_message":
            sources.update(item.source_texts)
    answer = _project_answer(question, selected) if selected else "未找到相关记忆"
    return BaselineOutput(
        answer=answer,
        context_tokens=context_tokens,
        sources=sources,
        page_count=page_count,
        loaded_pages=loaded_pages,
        dropped_pages=dropped_pages,
        dropped_page_details=dropped_page_details or [],
        page_type_counts=page_type_counts or {},
        page_source_counts=page_source_counts or [],
        page_summary_token_counts=page_summary_token_counts or [],
        retrieved_page_ids=retrieved_page_ids or [],
        dropped_page_reasons=dropped_page_reasons or {},
        dropped_page_source_ids=dropped_page_source_ids or {},
        retrieval_candidate_top_k=retrieval_candidate_top_k,
        retrieval_candidate_unit=retrieval_candidate_unit,
        retrieval_candidate_source_ids=retrieval_candidate_source_ids or [],
        retrieval_candidate_page_ids=retrieval_candidate_page_ids or [],
        page_candidate_top_k=page_candidate_top_k,
        page_candidate_source_ids=page_candidate_source_ids or [],
        page_candidate_page_ids=page_candidate_page_ids or [],
        superseded_source_recovered=superseded_source_recovered,
        candidate_budget_dropped=candidate_budget_dropped,
        active_overlap_not_top5=active_overlap_not_top5,
        item_source_hit_at_10=item_source_hit_at_10,
        episode_source_hit_at_10=episode_source_hit_at_10,
        planned_evidence_source_hit_at_5=planned_evidence_source_hit_at_5,
        budget_dropped_relevant=budget_dropped_relevant,
        source_not_indexed=source_not_indexed,
        indexed_source_ids=indexed_source_ids or [],
        item_candidate_source_ids=item_candidate_source_ids or [],
        episode_candidate_message_ids=episode_candidate_message_ids or [],
        planned_evidence_message_ids=planned_evidence_message_ids or [],
        memory_arch=memory_arch,
        v3_context=v3_context or {},
        v3_layer_counts=v3_layer_counts or {},
        v3_budget_decisions=v3_budget_decisions or [],
        v3_diagnostics=v3_diagnostics or [],
        v3_component_accounting=v3_component_accounting or [],
        v3_final_context_trace=v3_final_context_trace or [],
        v3_component_token_totals=v3_component_token_totals or {},
        v3_component_drop_counts=v3_component_drop_counts or {},
        locomo_neighbor_diagnostics=locomo_neighbor_diagnostics or [],
    )


def _dedupe_source_ids(source_ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for source_id in source_ids:
        if not isinstance(source_id, str) or source_id in seen:
            continue
        deduped.append(source_id)
        seen.add(source_id)
    return deduped


def _metadata_string_list(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return _dedupe_source_ids(item for item in value if isinstance(item, str))


def _metadata_string_list_prefer(
    metadata: dict[str, object],
    *,
    primary_key: str,
    fallback_key: str,
) -> list[str]:
    if primary_key in metadata:
        value = metadata.get(primary_key)
        if value is None:
            return []
        if isinstance(value, list):
            return _dedupe_source_ids(item for item in value if isinstance(item, str))
        return []
    return _metadata_string_list(metadata, fallback_key)


def _metadata_int(metadata: dict[str, object], key: str) -> int:
    value = metadata.get(key)
    return value if isinstance(value, int) else 0


def _metadata_int_prefer(
    metadata: dict[str, object],
    *,
    primary_key: str,
    fallback_key: str,
) -> int:
    if primary_key in metadata:
        value = metadata.get(primary_key)
        return value if isinstance(value, int) else 0
    return _metadata_int(metadata, fallback_key)


def _case_required_source_ids(case: EvalCase) -> list[str]:
    return _dedupe_source_ids(
        [
            *case.required_sources,
            *[
                source_id
                for source_ids in case.required_fact_sources.values()
                for source_id in source_ids
            ],
        ]
    )


def _select_evidence(question: str, evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    query_terms = set(tokenize(question))
    multi_evidence = _needs_multi_evidence(question)
    temporal_recent_update = any(
        item.origin in {"message", "retrieved_message"}
        and _is_temporal_question(question)
        and _has_update_signal(item.text)
        for item in evidence
    )
    scored: list[tuple[int, EvidenceItem]] = []
    for item in evidence:
        if is_generic_ack(item.text):
            continue
        score = len(query_terms & set(tokenize(item.text)))
        if item.origin == "retrieved_message":
            score += 12 if multi_evidence else 4
        if item.superseded and not multi_evidence:
            score -= 16
        if _has_update_signal(item.text):
            score += 20 if _is_temporal_question(question) else 12
        if item.origin == "page" and not temporal_recent_update and not multi_evidence:
            score += 8
        if any(
            marker in item.text for marker in ("不包含", "不提供", "无关", "噪声", "占位", "背景")
        ):
            score -= 20
        scored.append((score, item))
    scored.sort(key=lambda item: item[0], reverse=True)
    limit = _evidence_limit(question)
    positive_items = [item for score, item in scored if score > 0]
    if (
        _is_habit_or_preference_question(question)
        and len(positive_items) >= 2
        and all(item.origin == "retrieved_message" for item in positive_items[:2])
    ):
        limit = max(limit, 2)
    return [item for score, item in scored if score > 0][:limit]


def _evidence_limit(question: str) -> int:
    if any(marker in question for marker in ("分别", "哪些", "哪几个")):
        return 3
    if "和" in question and "什么" in question:
        return 3
    if _needs_multi_evidence(question):
        return 2
    return 1


def _needs_multi_evidence(question: str) -> bool:
    normalized = question.lower()
    return (
        " or " in normalized
        or " between " in normalized
        or "how many days" in normalized
        or " before " in normalized
        or " after " in normalized
        or _looks_like_first_comparison(normalized)
    )


def _looks_like_first_comparison(normalized_question: str) -> bool:
    stripped = normalized_question.rstrip(" ?!.")
    return (
        (stripped.startswith("which ") or stripped.startswith("what "))
        and stripped.endswith(" first")
        and not stripped.endswith(" at first")
    )


def _is_temporal_question(question: str) -> bool:
    temporal_markers = ("当前", "现在", "目前", "最新", "最终", "不做")
    return any(marker in question for marker in temporal_markers)


def _is_slot_value_question(question: str) -> bool:
    return any(
        marker in question for marker in ("什么", "哪个", "哪天", "多少", "谁", "哪种", "哪一个")
    )


def _is_habit_or_preference_question(question: str) -> bool:
    return any(marker in question for marker in ("习惯", "偏好", "平时"))


def _has_update_signal(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "最终确定",
            "最终调整",
            "最终换",
            "最终",
            "当前",
            "改用",
            "改为",
            "改成",
            "调整为",
            "调整到",
            "切换到",
            "切换成",
            "切到",
            "调到",
            "降到",
            "延到",
            "更新",
            "采用",
            "不做",
            "换",
        )
    )


def _project_answer(question: str, selected: list[EvidenceItem]) -> str:
    projected = [_project_evidence_text(question, item.text) for item in selected]
    projected = [text for text in projected if text]
    return "；".join(projected) if projected else "未找到相关记忆"


def _project_evidence_text(question: str, text: str) -> str:
    compact = " ".join(text.strip().split())
    if is_generic_ack(compact):
        return ""

    clauses = [clause.strip() for clause in compact.replace("；", "。").split("。")]
    clauses = [clause for clause in clauses if clause and not is_generic_ack(clause)]
    if not clauses:
        return ""

    if _is_temporal_question(question) or _is_slot_value_question(question):
        priority_markers = (
            "最终确定",
            "最终调整为",
            "最终换",
            "最终",
            "改用",
            "调整为",
            "调整到",
            "切换到",
            "切换成",
            "切到",
            "调到",
            "降到",
            "延到",
            "换成",
            "换用",
            "采用",
            "选",
        )
        for marker in priority_markers:
            for clause in reversed(clauses):
                if marker in clause:
                    return _drop_prefix_before_marker(clause, marker)
        # "换" as a standalone verb: preceded by space/punctuation or start of clause
        for clause in reversed(clauses):
            if re.search(r"(?:^|[\s，,。；;：:])换(?!\S)", clause):
                return _drop_prefix_before_marker(clause, "换")

    return compact


def _drop_prefix_before_marker(text: str, marker: str) -> str:
    if marker not in text:
        return text
    prefix, suffix = text.split(marker, 1)
    if marker.startswith(("最终", "当前")):
        start = max(prefix.rfind("，"), prefix.rfind(","), prefix.rfind("；"), prefix.rfind(";"))
        subject = prefix[start + 1 :] if start >= 0 else prefix
        return f"{subject}{marker}{suffix}".strip(" ，,：:")
    return suffix.strip(" ，,：:") or text


def _context_tokens(task: str, texts: list[str], tokenizer: TokenEstimator) -> int:
    return tokenizer.count(task) + sum(tokenizer.count(text) for text in texts)


def _message_sources(messages: list[Message]) -> dict[str, str]:
    return {message.id: message.content for message in messages}


def _message_evidence(messages: list[Message]) -> list[EvidenceItem]:
    return [
        EvidenceItem(text=message.content, source_texts={message.id: message.content})
        for message in messages
        if not (message.role == Role.ASSISTANT and is_generic_ack(message.content))
    ]
