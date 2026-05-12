import json
import time
from dataclasses import asdict, dataclass, field

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.llm_judge import JudgeVerdict, LLMJudge
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.schemas import EvalCase, Message, MessageCreate, PageType, Role
from memoryos_lite.store import create_store
from memoryos_lite.tokenizer import TokenEstimator

CASE_COUNT = 8


@dataclass
class EvalResult:
    baseline: str
    case_id: str
    answer: str
    expected_hits: int
    forbidden_hits: int
    source_hits: int
    source_ids: list[str]
    source_snippets: dict[str, str]
    supporting_source_snippets: dict[str, dict[str, str]]
    expected_fact_support: dict[str, list[str]]
    credited_fact_support: dict[str, list[str]]
    missing_expected_facts: list[str]
    unsupported_answered_facts: list[str]
    missing_required_sources: list[str]
    context_tokens: int
    page_count: int
    loaded_pages: int
    dropped_pages: int
    dropped_page_details: list[dict[str, object]]
    source_count: int
    supporting_source_count: int
    latency_ms: int

    @property
    def answer_accuracy(self) -> float:
        return (
            1.0
            if (
                self.expected_hits > 0
                and not self.missing_expected_facts
                and self.forbidden_hits == 0
            )
            else 0.0
        )

    @property
    def source_accuracy(self) -> float:
        return (
            1.0
            if self.answer_accuracy == 1.0
            and self.source_hits == self.expected_hits
            and not self.unsupported_answered_facts
            and not self.missing_required_sources
            else 0.0
        )

    def to_report(self) -> dict[str, object]:
        data = asdict(self)
        data["answer_accuracy"] = self.answer_accuracy
        data["source_accuracy"] = self.source_accuracy
        return data


@dataclass(frozen=True)
class BaselineOutput:
    answer: str
    context_tokens: int
    sources: dict[str, str]
    page_count: int = 0
    loaded_pages: int = 0
    dropped_pages: int = 0
    dropped_page_details: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceItem:
    text: str
    source_texts: dict[str, str]


def builtin_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"long_recall_{index:03d}",
                conversation=[
                    MessageCreate(
                        role=Role.USER,
                        content=f"早期事实：用户的第 {index} 个核心偏好是 Agent infra。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录该偏好。"),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                    MessageCreate(role=Role.USER, content="项目实现继续推进 LangGraph workflow。"),
                ],
                question=f"用户的第 {index} 个核心偏好是什么？",
                expected_facts=["Agent infra"],
                forbidden_facts=["前端动画"],
                required_sources=[f"long_recall_{index:03d}_msg_001"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"state_continuity_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="项目最初考虑做运营助手。"),
                    MessageCreate(role=Role.ASSISTANT, content="已记录初始方向。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第 {index} 次决策：最终主线改为 MemoryOS Lite。",
                    ),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                ],
                question="项目最终主线是什么？",
                expected_facts=["MemoryOS Lite"],
                forbidden_facts=["运营助手"],
                required_sources=[f"state_continuity_{index:03d}_msg_003"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"conflict_update_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="我想做 Runbook Oncall Agent。"),
                    MessageCreate(role=Role.ASSISTANT, content="已记录旧方向。"),
                    MessageCreate(
                        role=Role.USER,
                        content=(
                            f"第 {index} 次更新：不做 Runbook Oncall Agent，改做 MemoryOS Lite。"
                        ),
                    ),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                ],
                question="用户最终不做哪个方向？",
                expected_facts=["Runbook Oncall Agent"],
                forbidden_facts=["Raffle Strategy Lab"],
                required_sources=[f"conflict_update_{index:03d}_msg_003"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"multi_source_recall_{index:03d}",
                conversation=[
                    MessageCreate(
                        role=Role.USER,
                        content=f"第二项目主线：第 {index} 版确定为 MemoryOS Lite。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录第二项目主线。"),
                    MessageCreate(role=Role.USER, content="核心评估指标：source_accuracy。"),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                ],
                question="第二项目主线和核心评估指标分别是什么？",
                expected_facts=["MemoryOS Lite", "source_accuracy"],
                forbidden_facts=["前端动画"],
                required_fact_sources={
                    "MemoryOS Lite": [f"multi_source_recall_{index:03d}_msg_001"],
                    "source_accuracy": [f"multi_source_recall_{index:03d}_msg_003"],
                },
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"hard_long_recall_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="甲。"),
                    MessageCreate(role=Role.ASSISTANT, content="乙。"),
                    MessageCreate(role=Role.USER, content="丙。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第 {index} 次最终决定：简历第二项目做 MemoryOS Lite。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                    MessageCreate(role=Role.USER, content="排版。"),
                    MessageCreate(role=Role.USER, content="README。"),
                ],
                question="简历第二项目最终决定做什么？",
                expected_facts=["MemoryOS Lite"],
                forbidden_facts=["前端动画", "运营助手"],
                required_sources=[f"hard_long_recall_{index:03d}_msg_004"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"hard_source_budget_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="甲。"),
                    MessageCreate(role=Role.ASSISTANT, content="乙。"),
                    MessageCreate(role=Role.USER, content="丙。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第 {index} 次决定：可信 benchmark 必须审计 source_accuracy。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                    MessageCreate(role=Role.USER, content="终端。"),
                    MessageCreate(role=Role.USER, content="会议。"),
                ],
                question="可信 benchmark 必须审计哪个指标？",
                expected_facts=["source_accuracy"],
                forbidden_facts=["前端动画"],
                required_sources=[f"hard_source_budget_{index:03d}_msg_004"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"hard_conflict_update_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="甲。"),
                    MessageCreate(role=Role.ASSISTANT, content="乙。"),
                    MessageCreate(role=Role.USER, content="丙。"),
                    MessageCreate(role=Role.USER, content="旧方向：Runbook Oncall Agent。"),
                    MessageCreate(role=Role.USER, content="临时方向：运营助手。"),
                    MessageCreate(
                        role=Role.USER,
                        content=(
                            f"第 {index} 次最终决定：不做旧方向和临时方向，改做 MemoryOS Lite。"
                        ),
                    ),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                    MessageCreate(role=Role.USER, content="最新无关：整理日程。"),
                    MessageCreate(role=Role.USER, content="最新无关：检查提交。"),
                ],
                question="最终决定改做什么项目？",
                expected_facts=["MemoryOS Lite"],
                forbidden_facts=["Runbook Oncall Agent", "运营助手"],
                required_sources=[f"hard_conflict_update_{index:03d}_msg_006"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"noise_position_recall_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="前置噪声：课程。"),
                    MessageCreate(role=Role.USER, content="甲。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第 {index} 次最终决定：memory infra 采用 page_count 指标。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                    MessageCreate(role=Role.USER, content="乙。"),
                    MessageCreate(role=Role.USER, content="中段噪声：排版。"),
                    MessageCreate(role=Role.USER, content="最新无关：计划会议。"),
                    MessageCreate(role=Role.USER, content="最新无关：整理路径。"),
                ],
                question="memory infra 最终采用哪个指标？",
                expected_facts=["page_count"],
                forbidden_facts=["source_accuracy"],
                required_sources=[f"noise_position_recall_{index:03d}_msg_003"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"session_distractor_recall_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="旁路：看板。"),
                    MessageCreate(role=Role.ASSISTANT, content="旁路。"),
                    MessageCreate(role=Role.USER, content="当前：课程。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第 {index} 次最终决定：当前会话项目是 MemoryOS Lite。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录当前会话项目。"),
                    MessageCreate(role=Role.USER, content="当前会话噪声：命令输出。"),
                    MessageCreate(role=Role.USER, content="最新无关：检查命令。"),
                    MessageCreate(role=Role.USER, content="最新无关：同步记录。"),
                ],
                question="当前会话项目最终是什么？",
                expected_facts=["MemoryOS Lite"],
                forbidden_facts=["数据看板"],
                required_sources=[f"session_distractor_recall_{index:03d}_msg_004"],
            )
        )
    for index in range(1, CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"marker_ablation_recall_{index:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="排期记录：下周整理文档。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第 {index} 版稳定方案：MemoryOS Lite。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录稳定方案。"),
                    MessageCreate(role=Role.USER, content=_noise(index)),
                    MessageCreate(role=Role.USER, content="最新无关：检查格式。"),
                    MessageCreate(role=Role.USER, content="最新无关：同步记录。"),
                ],
                question="稳定方案是什么？",
                expected_facts=["MemoryOS Lite"],
                forbidden_facts=["前端动画"],
                required_sources=[f"marker_ablation_recall_{index:03d}_msg_002"],
            )
        )
    cases.append(
        EvalCase(
            case_id="dropped_page_audit_001",
            conversation=[
                MessageCreate(
                    role=Role.USER,
                    content=(
                        "稳定方案预算审计背景：这是一段很长的历史上下文，用来形成"
                        "超出严格预算的 memory page。稳定方案相关讨论很多，但这里"
                        "只提供背景，不提供最终答案。" * 6
                    ),
                ),
                MessageCreate(
                    role=Role.USER,
                    content=(
                        "稳定方案预算审计补充：继续记录大量无关实现细节、命令输出、"
                        "会议摘要和重复说明，使被检索到的历史 page 在 90 token 预算"
                        "下无法装入上下文。" * 6
                    ),
                ),
                MessageCreate(
                    role=Role.USER,
                    content=(
                        "稳定方案预算审计噪声：保留检索关键词，但不包含需要回答的"
                        "项目名；这页存在的目的只是测试 dropped_page_details。" * 6
                    ),
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录预算审计背景。"),
                MessageCreate(role=Role.USER, content="稳定方案是 MemoryOS Lite。"),
                MessageCreate(role=Role.USER, content="最新无关：整理评测输出。"),
            ],
            question="稳定方案是什么？",
            expected_facts=["MemoryOS Lite"],
            forbidden_facts=["前端动画"],
            required_sources=["dropped_page_audit_001_msg_005"],
        )
    )
    return cases


def _noise(index: int) -> str:
    return (
        f"第 {index} 段无关长噪声：课程安排、排版偏好、天气记录、临时想法、"
        "无关工具输出、重复讨论、非当前任务信息。" * 6
    )


def run_eval(
    settings: Settings,
    run_id: str,
    baselines: list[str],
    isolated: bool = True,
    case_set: str = "builtin",
) -> list[EvalResult]:
    eval_root = settings.memoryos_eval_data_dir or settings.data_dir / "eval_runs"
    run_dir = eval_root / run_id
    run_settings = settings.model_copy(
        update={
            "data_dir": run_dir,
            "database_url": None,
            "memoryos_paging_mode": "heuristic",
            "openai_api_key": None,
        }
    )
    store = create_store(run_settings)
    if isolated:
        store.reset()
    service = MemoryOSService(store=store, settings=run_settings)
    results: list[EvalResult] = []

    cases = _select_cases(case_set)

    for case in cases:
        messages = _materialize_messages(case)
        for baseline in _expand_baselines(baselines):
            start = time.perf_counter()
            output = _run_baseline(baseline, case, messages, service, run_settings)
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(_score(case, baseline, output, latency_ms))

    report_dir = settings.data_dir / "evals"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}.json"
    report_path.write_text(
        json.dumps([result.to_report() for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def run_demo_eval(settings: Settings) -> list[EvalResult]:
    return run_eval(settings, run_id="demo_report", baselines=["all"], isolated=True)


def run_eval_llm(
    settings: Settings,
    run_id: str,
    baselines: list[str],
    isolated: bool = True,
    case_set: str = "builtin",
) -> list[JudgeVerdict]:
    """Run eval with LLM-as-judge scoring (requires OpenAI API key)."""
    judge = LLMJudge(settings)
    eval_root = settings.memoryos_eval_data_dir or settings.data_dir / "eval_runs"
    run_dir = eval_root / run_id
    run_settings = settings.model_copy(
        update={
            "data_dir": run_dir,
            "database_url": None,
            "memoryos_paging_mode": "heuristic",
            "openai_api_key": None,
        }
    )
    store = create_store(run_settings)
    if isolated:
        store.reset()
    service = MemoryOSService(store=store, settings=run_settings)
    verdicts: list[JudgeVerdict] = []
    for case in _select_cases(case_set):
        messages = _materialize_messages(case)
        for baseline in _expand_baselines(baselines):
            output = _run_baseline(baseline, case, messages, service, run_settings)
            verdict = judge.judge(case, output.answer)
            verdict.case_id = f"{baseline}/{case.case_id}"
            verdicts.append(verdict)

    report_dir = settings.data_dir / "evals"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}_llm_judge.json"
    report_path.write_text(
        json.dumps([asdict(v) for v in verdicts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return verdicts


def _select_cases(case_set: str) -> list[EvalCase]:
    """Dispatch case_set name to the concrete case list."""
    if case_set == "advanced":
        from memoryos_lite.evals_advanced import advanced_cases

        return advanced_cases()
    if case_set == "hard":
        from memoryos_lite.evals_hard import hard_cases

        return hard_cases()
    if case_set == "all":
        from memoryos_lite.evals_advanced import advanced_cases
        from memoryos_lite.evals_hard import hard_cases

        return builtin_cases() + advanced_cases() + hard_cases()
    return builtin_cases()


def _run_baseline(
    baseline: str,
    case: EvalCase,
    messages: list[Message],
    service: MemoryOSService,
    settings: Settings,
) -> BaselineOutput:
    tokenizer = TokenEstimator()
    budget = 90
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
        selected = _fit_ranked_messages(ranked, case.question, budget, tokenizer)
        return _baseline_from_evidence(
            case.question,
            _message_evidence(selected),
            _context_tokens(case.question, [message.content for message in selected], tokenizer),
        )
    if baseline == "memoryos_lite":
        if case.query_in_new_session:
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
            service.page(source_session.id)
            context = service.build_context(
                context_session.id,
                case.question,
                budget=budget,
                include_global_core=case.include_global_core,
            )
        finally:
            service.settings.rot_safe_budget = original_budget
            service.settings.recent_message_limit = original_recent
        pages = [service.store.load_page(item.page_id) for item in context.retrieved_pages]
        pages.extend(service.store.load_page(item.page_id) for item in context.active_task_pages)
        if context.pinned_core:
            pages_by_id = {page.id: page for page in service.store.list_pages(source_session.id)}
            if case.include_global_core:
                pages_by_id.update(
                    {page.id: page for page in service.store.list_global_core_pages()}
                )
            loaded_page_ids = {page.id for page in pages if page is not None}
            for summary in context.pinned_core:
                pinned_page = next(
                    (
                        page
                        for page in pages_by_id.values()
                        if page.page_type == PageType.CORE_PROFILE
                        and page.summary == summary
                        and page.id not in loaded_page_ids
                    ),
                    None,
                )
                if pinned_page is not None:
                    pages.append(pinned_page)
                    loaded_page_ids.add(pinned_page.id)
        evidence = _message_evidence(context.recent_messages)
        messages_by_id = {message.id: message for message in messages}
        for page in pages:
            if page is not None:
                evidence.append(
                    EvidenceItem(
                        text=page.summary,
                        source_texts=_page_fact_sources(page.source_message_ids, messages_by_id),
                    )
                )
        return _baseline_from_evidence(
            case.question,
            evidence,
            context.estimated_tokens,
            page_count=len(service.store.list_pages(source_session.id)),
            loaded_pages=len(pages),
            dropped_pages=len(context.dropped_pages),
            dropped_page_details=[item.model_dump() for item in context.dropped_pages],
        )
    raise ValueError(f"unknown baseline: {baseline}")


def _expand_baselines(baselines: list[str]) -> list[str]:
    if "all" in baselines:
        return ["sliding_window", "naive_summary", "vector_rag", "memoryos_lite"]
    return baselines


def _materialize_messages(case: EvalCase) -> list[Message]:
    tokenizer = TokenEstimator()
    return [
        Message(
            id=f"{case.case_id}_msg_{index:03d}",
            session_id=case.case_id,
            role=message.role,
            content=message.content,
            metadata=message.metadata,
            token_count=tokenizer.count(message.content),
        )
        for index, message in enumerate(case.conversation, start=1)
    ]


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
) -> BaselineOutput:
    selected = _select_evidence(question, evidence)
    sources: dict[str, str] = {}
    for item in selected:
        sources.update(item.source_texts)
    answer = "；".join(item.text for item in selected) if selected else "未找到相关记忆"
    return BaselineOutput(
        answer=answer,
        context_tokens=context_tokens,
        sources=sources,
        page_count=page_count,
        loaded_pages=loaded_pages,
        dropped_pages=dropped_pages,
        dropped_page_details=dropped_page_details or [],
    )


def _select_evidence(question: str, evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    query_terms = set(tokenize(question))
    scored: list[tuple[int, EvidenceItem]] = []
    for item in evidence:
        score = len(query_terms & set(tokenize(item.text)))
        if any(marker in question for marker in ("最终", "不做", "主线")) and any(
            marker in item.text for marker in ("最终", "不做", "改为", "更新")
        ):
            score += 20
        scored.append((score, item))
    scored.sort(key=lambda item: item[0], reverse=True)
    limit = 1 if any(marker in question for marker in ("最终", "不做")) else 3
    return [item for score, item in scored if score > 0][:limit]


def _context_tokens(task: str, texts: list[str], tokenizer: TokenEstimator) -> int:
    return tokenizer.count(task) + sum(tokenizer.count(text) for text in texts)


def _message_sources(messages: list[Message]) -> dict[str, str]:
    return {message.id: message.content for message in messages}


def _message_evidence(messages: list[Message]) -> list[EvidenceItem]:
    return [
        EvidenceItem(text=message.content, source_texts={message.id: message.content})
        for message in messages
    ]


def _page_fact_sources(
    source_message_ids: list[str],
    messages_by_id: dict[str, Message],
) -> dict[str, str]:
    return {
        source_id: messages_by_id[source_id].content
        for source_id in source_message_ids
        if source_id in messages_by_id
    }


def _score(
    case: EvalCase,
    baseline: str,
    output: BaselineOutput,
    latency_ms: int,
) -> EvalResult:
    expected_hits = sum(1 for fact in case.expected_facts if fact in output.answer)
    forbidden_hits = sum(1 for fact in case.forbidden_facts if fact in output.answer)
    expected_fact_support = _expected_fact_support(case, output)
    missing_expected_facts = [fact for fact in case.expected_facts if fact not in output.answer]
    unsupported_answered_facts = _unsupported_answered_facts(
        case,
        output,
        expected_fact_support,
    )
    missing_required_sources = _missing_required_sources(case, output, expected_fact_support)
    credited_fact_support = (
        {}
        if forbidden_hits > 0
        else _credited_fact_support(
            case,
            expected_fact_support,
            unsupported_answered_facts,
        )
    )
    source_hits = _source_hits(
        case,
        output,
        credited_fact_support,
        unsupported_answered_facts,
        missing_required_sources,
    )
    supporting_source_ids = {
        source_id for source_ids in credited_fact_support.values() for source_id in source_ids
    }
    return EvalResult(
        baseline=baseline,
        case_id=case.case_id,
        answer=output.answer,
        expected_hits=expected_hits,
        forbidden_hits=forbidden_hits,
        source_hits=source_hits,
        source_ids=sorted(output.sources),
        source_snippets=_source_snippets(output.sources),
        supporting_source_snippets=_supporting_source_snippets(
            output.sources,
            credited_fact_support,
        ),
        expected_fact_support=expected_fact_support,
        credited_fact_support=credited_fact_support,
        missing_expected_facts=missing_expected_facts,
        unsupported_answered_facts=unsupported_answered_facts,
        missing_required_sources=missing_required_sources,
        context_tokens=output.context_tokens,
        page_count=output.page_count,
        loaded_pages=output.loaded_pages,
        dropped_pages=output.dropped_pages,
        dropped_page_details=output.dropped_page_details,
        source_count=len(output.sources),
        supporting_source_count=len(supporting_source_ids),
        latency_ms=latency_ms,
    )


def _source_hits(
    case: EvalCase,
    output: BaselineOutput,
    credited_fact_support: dict[str, list[str]],
    unsupported_answered_facts: list[str],
    missing_required_sources: list[str],
) -> int:
    if any(fact in output.answer for fact in case.forbidden_facts):
        return 0
    missing_required_facts = {
        item.split(":", 1)[0] for item in missing_required_sources if ":" in item
    }
    unsupported = set(unsupported_answered_facts) | missing_required_facts
    return sum(
        1
        for fact in case.expected_facts
        if fact in output.answer and fact in credited_fact_support and fact not in unsupported
    )


def _expected_fact_support(
    case: EvalCase,
    output: BaselineOutput,
) -> dict[str, list[str]]:
    return {
        fact: [source_id for source_id, text in sorted(output.sources.items()) if fact in text]
        for fact in case.expected_facts
        if fact in output.answer and any(fact in text for text in output.sources.values())
    }


def _credited_fact_support(
    case: EvalCase,
    expected_fact_support: dict[str, list[str]],
    unsupported_answered_facts: list[str],
) -> dict[str, list[str]]:
    credited: dict[str, list[str]] = {}
    unsupported = set(unsupported_answered_facts)
    for fact, source_ids in expected_fact_support.items():
        if fact in unsupported:
            continue
        required_for_fact = case.required_fact_sources.get(fact)
        if required_for_fact is not None:
            fact_sources = [source_id for source_id in source_ids if source_id in required_for_fact]
        elif case.required_sources:
            fact_sources = [
                source_id for source_id in source_ids if source_id in case.required_sources
            ]
        else:
            fact_sources = source_ids
        if fact_sources:
            credited[fact] = fact_sources
    return credited


def _unsupported_answered_facts(
    case: EvalCase,
    output: BaselineOutput,
    expected_fact_support: dict[str, list[str]],
) -> list[str]:
    unsupported: list[str] = []
    for fact in case.expected_facts:
        if fact not in output.answer:
            continue
        if fact not in expected_fact_support:
            unsupported.append(fact)
            continue
        fact_support = set(expected_fact_support[fact])
        required_for_fact = case.required_fact_sources.get(fact)
        if required_for_fact is not None:
            if not set(required_for_fact) <= fact_support:
                unsupported.append(fact)
        elif case.required_sources and not fact_support & set(case.required_sources):
            unsupported.append(fact)
    return unsupported


def _missing_required_sources(
    case: EvalCase,
    output: BaselineOutput,
    expected_fact_support: dict[str, list[str]],
) -> list[str]:
    missing: list[str] = []
    for fact, required_sources in case.required_fact_sources.items():
        if fact not in output.answer:
            continue
        fact_support = set(expected_fact_support.get(fact, []))
        missing.extend(
            f"{fact}:{source_id}" for source_id in required_sources if source_id not in fact_support
        )
    if not case.required_fact_sources and case.required_sources:
        all_supporting_sources = {
            source_id for sources in expected_fact_support.values() for source_id in sources
        }
        if any(fact in output.answer for fact in case.expected_facts):
            missing.extend(
                source_id
                for source_id in case.required_sources
                if source_id not in all_supporting_sources
            )
    return sorted(missing)


def _source_snippets(sources: dict[str, str], limit: int = 120) -> dict[str, str]:
    return {source_id: _snippet(text, limit=limit) for source_id, text in sorted(sources.items())}


def _supporting_source_snippets(
    sources: dict[str, str],
    expected_fact_support: dict[str, list[str]],
    limit: int = 120,
) -> dict[str, dict[str, str]]:
    return {
        fact: {
            source_id: _snippet(sources[source_id], limit=limit)
            for source_id in source_ids
            if source_id in sources
        }
        for fact, source_ids in sorted(expected_fact_support.items())
    }


def _snippet(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
