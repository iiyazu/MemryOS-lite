import json

import pytest
from pydantic import ValidationError

from memoryos_lite.cli import _eval_table_rows, _llm_judge_table_rows
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import (
    BaselineOutput,
    EvidenceItem,
    _baseline_from_evidence,
    _materialize_messages,
    _needs_multi_evidence,
    _project_evidence_text,
    _run_baseline,
    _score,
    builtin_cases,
    run_eval,
)
from memoryos_lite.llm_judge import JudgeVerdict
from memoryos_lite.schemas import EvalCase, MessageCreate, Role
from memoryos_lite.store import create_store


def test_eval_run_does_not_reset_main_store(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("main-data")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="主库数据不能被 eval 删除。"))

    results = run_eval(settings, run_id="test-run", baselines=["sliding_window"], isolated=True)

    assert results
    assert store.get_session(session.id) is not None
    assert store.list_messages(session.id)
    assert (settings.data_dir / "evals" / "test-run.json").exists()


def test_eval_forces_heuristic_paging_for_reproducibility(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        openai_api_key="dummy",
    )

    results = run_eval(settings, run_id="forced-heuristic", baselines=["memoryos_lite"])
    trace_dir = settings.data_dir / "eval_runs" / "forced-heuristic" / "traces"
    trace_paths = list(trace_dir.glob("*.jsonl"))

    assert results
    assert trace_paths
    trace_text = "\n".join(path.read_text(encoding="utf-8") for path in trace_paths)
    # FakePageDraftClient is injected in run_eval; it calls heuristic internally
    # but the paging_agent sees it as a real llm_client → mode is "agentic"
    assert '"paging_mode":"agentic"' in trace_text


def test_all_eval_baselines_obey_budget(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_eval(settings, run_id="budget-run", baselines=["all"], isolated=True)

    assert results
    assert {result.baseline for result in results} == {
        "sliding_window",
        "naive_summary",
        "vector_rag",
        "memoryos_lite",
    }
    assert all(result.context_tokens <= 90 for result in results)


def test_builtin_case_message_ids_are_stable():
    case = builtin_cases()[0]

    first = _materialize_messages(case)
    second = _materialize_messages(case)

    assert [message.id for message in first] == [message.id for message in second]
    assert first[0].id == case.required_sources[0]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Which event did I attend first?", True),
        ("What came first?", True),
        ("What is my first name?", False),
        ("What did I think at first?", False),
        ("First of all, what did I decide?", False),
    ],
)
def test_needs_multi_evidence_first_matching_is_narrow(question, expected):
    assert _needs_multi_evidence(question) is expected


def test_source_accuracy_requires_required_source_text():
    case = builtin_cases()[0]
    output = BaselineOutput(
        answer="用户的核心偏好是 Agent infra。",
        context_tokens=10,
        sources={"wrong_source": "用户的核心偏好是 Agent infra。"},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.answer_accuracy == 1.0
    assert result.source_accuracy == 0.0


def test_source_accuracy_fails_when_answer_contains_forbidden_fact():
    case = builtin_cases()[0]
    output = BaselineOutput(
        answer="用户的核心偏好是 Agent infra，不是前端动画。",
        context_tokens=10,
        sources={case.required_sources[0]: "用户的核心偏好是 Agent infra。"},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.answer_accuracy == 0.0
    assert result.source_hits == 0
    assert result.source_accuracy == 0.0


def test_lexical_scorer_flags_negated_forbidden_entity():
    case = EvalCase(
        case_id="negated_forbidden_entity",
        conversation=[],
        question="稳定方案是什么？",
        expected_facts=["MemoryOS Lite"],
        forbidden_facts=["Runbook Oncall Agent"],
        required_sources=["msg_001"],
    )
    output = BaselineOutput(
        answer=(
            "稳定方案是 MemoryOS Lite，不是 Runbook Oncall Agent，也不做 Runbook Oncall Agent。"
        ),
        context_tokens=10,
        sources={"msg_001": "第 1 版稳定方案：MemoryOS Lite。"},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.forbidden_hits == 1
    assert result.answer_accuracy == 0.0
    assert result.source_hits == 0
    assert result.source_accuracy == 0.0
    assert result.credited_fact_support == {}
    assert result.supporting_source_count == 0


def test_answer_accuracy_requires_all_expected_facts():
    case = EvalCase(
        case_id="partial_answer",
        conversation=[],
        question="项目主线和指标是什么？",
        expected_facts=["MemoryOS Lite", "source_accuracy"],
    )
    output = BaselineOutput(
        answer="项目主线是 MemoryOS Lite。",
        context_tokens=10,
        sources={
            "msg_001": "项目主线是 MemoryOS Lite。",
            "msg_002": "核心指标是 source_accuracy。",
        },
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.expected_hits == 1
    assert result.missing_expected_facts == ["source_accuracy"]
    assert result.unsupported_answered_facts == []
    assert result.missing_required_sources == []
    assert result.answer_accuracy == 0.0
    assert result.source_accuracy == 0.0


def test_answer_accuracy_follows_missing_expected_facts_invariant():
    case = EvalCase(
        case_id="no_expected_fact_regression",
        conversation=[],
        question="Is there anything expected?",
        expected_facts=[],
    )
    output = BaselineOutput(
        answer="No expected fact is configured.",
        context_tokens=10,
        sources={},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.expected_hits == 0
    assert result.missing_expected_facts == []
    assert result.answer_accuracy == 1.0


def test_source_accuracy_requires_all_fact_sources():
    case = EvalCase(
        case_id="partial_source",
        conversation=[],
        question="项目主线和指标是什么？",
        expected_facts=["MemoryOS Lite", "source_accuracy"],
        required_fact_sources={
            "MemoryOS Lite": ["msg_001"],
            "source_accuracy": ["msg_002"],
        },
    )
    output = BaselineOutput(
        answer="项目主线是 MemoryOS Lite，核心指标是 source_accuracy。",
        context_tokens=10,
        sources={"msg_001": "项目主线是 MemoryOS Lite。"},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.answer_accuracy == 1.0
    assert result.expected_fact_support == {"MemoryOS Lite": ["msg_001"]}
    assert result.unsupported_answered_facts == ["source_accuracy"]
    assert result.missing_required_sources == ["source_accuracy:msg_002"]
    assert result.source_accuracy == 0.0


def test_multi_fact_cases_reject_flat_required_sources():
    with pytest.raises(ValidationError, match="required_fact_sources"):
        EvalCase(
            case_id="ambiguous_multi_fact_sources",
            conversation=[],
            question="项目主线和指标是什么？",
            expected_facts=["MemoryOS Lite", "source_accuracy"],
            required_sources=["msg_001"],
        )


def test_multi_fact_cases_reject_missing_required_fact_source_key():
    with pytest.raises(ValidationError, match="missing keys: source_accuracy"):
        EvalCase(
            case_id="missing_required_fact_source_key",
            conversation=[],
            question="项目主线和指标是什么？",
            expected_facts=["MemoryOS Lite", "source_accuracy"],
            required_fact_sources={"MemoryOS Lite": ["msg_001"]},
        )


def test_multi_fact_cases_reject_unknown_required_fact_source_key():
    with pytest.raises(ValidationError, match="unknown keys: unrelated_fact"):
        EvalCase(
            case_id="unknown_required_fact_source_key",
            conversation=[],
            question="项目主线和指标是什么？",
            expected_facts=["MemoryOS Lite", "source_accuracy"],
            required_fact_sources={
                "MemoryOS Lite": ["msg_001"],
                "source_accuracy": ["msg_002"],
                "unrelated_fact": ["msg_003"],
            },
        )


def test_single_fact_cases_reject_incomplete_required_fact_source_keys():
    with pytest.raises(ValidationError, match="missing keys: MemoryOS Lite"):
        EvalCase(
            case_id="single_fact_typo_required_fact_source_key",
            conversation=[],
            question="稳定方案是什么？",
            expected_facts=["MemoryOS Lite"],
            required_fact_sources={"MemoryOSLite": ["msg_001"]},
        )


def test_required_fact_sources_reject_empty_source_list():
    with pytest.raises(ValidationError, match="empty keys: MemoryOS Lite"):
        EvalCase(
            case_id="empty_required_fact_source_list",
            conversation=[],
            question="稳定方案是什么？",
            expected_facts=["MemoryOS Lite"],
            required_fact_sources={"MemoryOS Lite": []},
        )


def test_multi_fact_cases_accept_complete_required_fact_sources():
    case = EvalCase(
        case_id="complete_required_fact_sources",
        conversation=[],
        question="项目主线和指标是什么？",
        expected_facts=["MemoryOS Lite", "source_accuracy"],
        required_fact_sources={
            "MemoryOS Lite": ["msg_001"],
            "source_accuracy": ["msg_002"],
        },
    )

    assert set(case.required_fact_sources) == set(case.expected_facts)


def test_missing_answer_fact_does_not_report_missing_source_support():
    case = EvalCase(
        case_id="missing_answer_fact",
        conversation=[],
        question="项目主线和指标是什么？",
        expected_facts=["MemoryOS Lite", "source_accuracy"],
        required_fact_sources={
            "MemoryOS Lite": ["msg_001"],
            "source_accuracy": ["msg_002"],
        },
    )
    output = BaselineOutput(
        answer="项目主线是 MemoryOS Lite。",
        context_tokens=10,
        sources={"msg_001": "项目主线是 MemoryOS Lite。"},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.missing_expected_facts == ["source_accuracy"]
    assert result.unsupported_answered_facts == []
    assert result.missing_required_sources == []
    assert result.source_accuracy == 0.0


def test_naive_summary_does_not_duplicate_selected_recent_message(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    case = EvalCase(
        case_id="naive_recent_dedup",
        conversation=[
            MessageCreate(role=Role.USER, content="项目约束：benchmark 必须可复现。"),
            MessageCreate(role=Role.ASSISTANT, content="已记录项目约束。"),
            MessageCreate(role=Role.USER, content="核心评估指标：source_accuracy。"),
            MessageCreate(role=Role.USER, content="无关长噪声：" + "噪声 " * 120),
        ],
        question="核心评估指标是什么？",
        expected_facts=["source_accuracy"],
        required_sources=["naive_recent_dedup_msg_003"],
    )
    messages = _materialize_messages(case)
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)

    output = _run_baseline("naive_summary", case, messages, service, settings)

    assert output.answer.count("核心评估指标：source_accuracy。") == 1
    assert output.sources == {"naive_recent_dedup_msg_003": "核心评估指标：source_accuracy。"}


def test_eval_projects_final_answer_without_stale_prefix():
    output = _baseline_from_evidence(
        "周会最终在哪个会议室开？",
        [
            EvidenceItem(
                text="B203 维护，会议室最终换 C505。",
                source_texts={"msg_005": "B203 维护，会议室最终换 C505。"},
            )
        ],
        context_tokens=10,
    )

    assert output.answer == "会议室最终换 C505"
    assert "B203" not in output.answer


def test_memoryos_eval_uses_fact_level_evidence_for_distractors(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    case = EvalCase(
        case_id="fact_level_distractor",
        conversation=[
            MessageCreate(role=Role.USER, content="家住在深圳南山区。"),
            MessageCreate(role=Role.ASSISTANT, content="已记录住址。"),
            MessageCreate(role=Role.USER, content="公司在深圳福田区。"),
            MessageCreate(role=Role.ASSISTANT, content="已记录办公地。"),
            MessageCreate(role=Role.USER, content="通勤大约 40 分钟。"),
            MessageCreate(role=Role.USER, content="周末常去海边。"),
        ],
        question="我家住在深圳哪个区？",
        expected_facts=["南山"],
        forbidden_facts=["福田"],
        required_sources=["fact_level_distractor_msg_001"],
    )
    messages = _materialize_messages(case)
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)

    output = _run_baseline("memoryos_lite", case, messages, service, settings)
    result = _score(case, "memoryos_lite", output, latency_ms=0)

    assert output.answer == "家住在深圳南山区。"
    assert "福田" not in output.answer
    assert result.answer_accuracy == 1.0
    assert result.source_accuracy == 1.0


def test_memoryos_eval_prefers_paged_evidence_over_recent_restatement(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    case = EvalCase(
        case_id="paged_over_recent",
        conversation=[
            MessageCreate(role=Role.USER, content="我喜欢喝黑咖啡。"),
            MessageCreate(role=Role.ASSISTANT, content="已记录偏好。"),
            MessageCreate(role=Role.USER, content="早上开会前准备一杯。"),
            MessageCreate(role=Role.USER, content="一直以来都喝黑咖啡，不加糖。"),
            MessageCreate(role=Role.ASSISTANT, content="已记录。"),
            MessageCreate(role=Role.USER, content="买了新的咖啡豆。"),
            MessageCreate(role=Role.USER, content="我的咖啡习惯固定是黑咖啡无糖。"),
        ],
        question="我的咖啡偏好是什么？",
        expected_facts=["黑咖啡"],
        forbidden_facts=["拿铁"],
        required_sources=["paged_over_recent_msg_001"],
    )
    messages = _materialize_messages(case)
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)

    output = _run_baseline("memoryos_lite", case, messages, service, settings)
    result = _score(case, "memoryos_lite", output, latency_ms=0)

    assert output.answer == "我喜欢喝黑咖啡。"
    assert result.source_accuracy == 1.0


def test_eval_prefers_recent_update_over_stale_page_evidence():
    output = _baseline_from_evidence(
        "当前数据库是什么？",
        [
            EvidenceItem(
                text="数据库选 PostgreSQL。",
                source_texts={"old_page_msg": "数据库选 PostgreSQL。"},
                origin="page",
            ),
            EvidenceItem(
                text="数据库改用 MySQL。",
                source_texts={"recent_msg": "数据库改用 MySQL。"},
            ),
        ],
        context_tokens=10,
    )

    assert output.answer == "MySQL"
    assert output.sources == {"recent_msg": "数据库改用 MySQL。"}


@pytest.mark.parametrize("noise", ["换行保持不变", "交换格式说明", "兑换券无关"])
def test_answer_projection_does_not_treat_huan_as_broad_update_marker(noise: str):
    projected = _project_evidence_text(
        "当前数据库是什么？",
        f"格式说明：{noise}。数据库选 PostgreSQL。",
    )

    assert projected == "PostgreSQL"


def test_forbidden_answer_receives_no_credited_source_support():
    case = EvalCase(
        case_id="forbidden_credit_guard",
        conversation=[],
        question="项目主线是什么？",
        expected_facts=["MemoryOS Lite"],
        forbidden_facts=["前端动画"],
        required_sources=["msg_001"],
    )
    output = BaselineOutput(
        answer="项目主线是 MemoryOS Lite，但也包含前端动画。",
        context_tokens=10,
        sources={"msg_001": "项目主线是 MemoryOS Lite。"},
    )

    result = _score(case, "test", output, latency_ms=0)

    assert result.answer_accuracy == 0.0
    assert result.source_accuracy == 0.0
    assert result.credited_fact_support == {}
    assert result.supporting_source_snippets == {}
    assert result.supporting_source_count == 0


def test_eval_report_includes_source_ids(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    run_eval(settings, run_id="source-report", baselines=["memoryos_lite"], isolated=True)
    report = json.loads((settings.data_dir / "evals" / "source-report.json").read_text())

    assert report
    assert all("source_ids" in row for row in report)
    assert all("source_snippets" in row for row in report)
    assert all("supporting_source_snippets" in row for row in report)
    assert all("expected_fact_support" in row for row in report)
    assert all("credited_fact_support" in row for row in report)
    assert all("missing_expected_facts" in row for row in report)
    assert all("unsupported_answered_facts" in row for row in report)
    assert all("missing_required_sources" in row for row in report)
    assert all("page_count" in row for row in report)
    assert all("loaded_pages" in row for row in report)
    assert all("dropped_pages" in row for row in report)
    assert all("dropped_page_details" in row for row in report)
    assert all("source_count" in row for row in report)
    assert all("supporting_source_count" in row for row in report)
    assert any(row["source_ids"] for row in report)
    assert any(row["source_snippets"] for row in report)
    assert any(row["supporting_source_snippets"] for row in report)
    assert any(row["expected_fact_support"] for row in report)
    dropped_audit_row = next(row for row in report if row["case_id"] == "dropped_page_audit_001")
    assert dropped_audit_row["dropped_page_details"]
    assert dropped_audit_row["dropped_page_details"][0]["reason"].startswith("rrf ")


def test_eval_cli_rows_include_dropped_cases(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_eval(settings, run_id="cli-dropped-cases", baselines=["memoryos_lite"])
    rows = _eval_table_rows(results)
    memoryos_row = next(row for row in rows if row["baseline"] == "memoryos_lite")

    assert memoryos_row["cases"] == "81"
    assert int(memoryos_row["dropped_cases"]) >= 1


def test_llm_judge_cli_rows_group_by_baseline():
    rows = _llm_judge_table_rows(
        [
            JudgeVerdict("memoryos_lite/case_001", "pass", [], [], [], ""),
            JudgeVerdict("memoryos_lite/case_002", "fail", [], [], [], ""),
            JudgeVerdict("vector_rag/case_001", "error", [], [], [], ""),
        ]
    )

    memoryos_row = next(row for row in rows if row["baseline"] == "memoryos_lite")
    vector_row = next(row for row in rows if row["baseline"] == "vector_rag")
    assert memoryos_row == {
        "baseline": "memoryos_lite",
        "cases": "2",
        "pass_rate": "0.50",
        "failed": "1",
        "errors": "0",
    }
    assert vector_row["errors"] == "1"


def test_eval_report_serializes_dropped_page_details():
    output = BaselineOutput(
        answer="未找到相关记忆",
        context_tokens=90,
        sources={},
        dropped_pages=1,
        dropped_page_details=[
            {
                "page_id": "page_001",
                "title": "Large page",
                "reason": "lexical_overlap=3",
                "estimated_tokens": 120,
            }
        ],
    )

    result = _score(builtin_cases()[0], "memoryos_lite", output, latency_ms=0)
    report = result.to_report()

    assert report["dropped_pages"] == 1
    assert report["dropped_page_details"] == [
        {
            "page_id": "page_001",
            "title": "Large page",
            "reason": "lexical_overlap=3",
            "estimated_tokens": 120,
        }
    ]


def test_supporting_source_snippets_show_only_credit_sources(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    run_eval(settings, run_id="supporting-snippets", baselines=["memoryos_lite"])
    report = json.loads((settings.data_dir / "evals" / "supporting-snippets.json").read_text())
    row = next(
        item
        for item in report
        if item["baseline"] == "memoryos_lite" and item["case_id"] == "hard_long_recall_001"
    )

    # source_snippets audits every surfaced source; supporting_source_snippets
    # below is the strict credited-source assertion.
    assert set(row["source_snippets"]) >= {"hard_long_recall_001_msg_004"}
    assert row["supporting_source_snippets"] == {
        "MemoryOS Lite": {
            "hard_long_recall_001_msg_004": "第 1 次最终决定：简历第二项目做 MemoryOS Lite。"
        }
    }


def test_memoryos_source_attribution_uses_original_message_text(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    case = EvalCase(
        case_id="page_source_guard",
        conversation=[
            MessageCreate(role=Role.USER, content="早期事实：用户的核心偏好是 Agent infra。"),
            MessageCreate(role=Role.ASSISTANT, content="已记录该偏好。"),
            MessageCreate(role=Role.USER, content="项目实现继续推进 LangGraph workflow。"),
            MessageCreate(role=Role.USER, content="无关噪声内容。"),
        ],
        question="用户的核心偏好是什么？",
        expected_facts=["Agent infra"],
        required_sources=["page_source_guard_msg_002"],
    )
    messages = _materialize_messages(case)
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)

    output = _run_baseline("memoryos_lite", case, messages, service, settings)
    result = _score(case, "memoryos_lite", output, latency_ms=0)

    assert "Agent infra" in output.answer
    assert result.answer_accuracy == 1.0
    assert result.source_accuracy == 0.0


def test_memoryos_baseline_preserves_required_sources(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_eval(
        settings,
        run_id="source-memoryos",
        baselines=["memoryos_lite"],
        isolated=True,
    )

    assert results
    assert all(result.source_accuracy == 1.0 for result in results)


def test_hard_cases_preserve_baseline_differentiation(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_eval(settings, run_id="hard-diff", baselines=["all"], isolated=True)
    hard_results = [
        result
        for result in results
        if result.case_id.startswith(
            (
                "hard_long_recall",
                "hard_source_budget",
                "hard_conflict_update",
                "noise_position_recall",
                "session_distractor_recall",
                "marker_ablation_recall",
            )
        )
    ]
    marker_results = [
        result for result in results if result.case_id.startswith("marker_ablation_recall")
    ]
    naive = [result for result in hard_results if result.baseline == "naive_summary"]
    memoryos = [result for result in hard_results if result.baseline == "memoryos_lite"]
    marker_sliding = [result for result in marker_results if result.baseline == "sliding_window"]
    marker_vector = [result for result in marker_results if result.baseline == "vector_rag"]
    marker_memoryos = [result for result in marker_results if result.baseline == "memoryos_lite"]

    assert naive
    assert memoryos
    assert marker_sliding
    assert marker_vector
    assert marker_memoryos
    assert any(result.source_accuracy == 0.0 for result in naive)
    assert sum(result.source_accuracy for result in memoryos) > sum(
        result.source_accuracy for result in naive
    )
    assert all(result.source_accuracy == 1.0 for result in memoryos)
    assert all(result.source_accuracy == 0.0 for result in marker_sliding)
    assert all(result.source_accuracy == 1.0 for result in marker_vector)
    assert all(result.source_accuracy == 1.0 for result in marker_memoryos)


def test_builtin_cases_include_multi_fact_source_cases():
    cases = builtin_cases()

    multi_cases = [case for case in cases if case.case_id.startswith("multi_source_recall")]
    hard_cases = [
        case
        for case in cases
        if case.case_id.startswith(
            (
                "hard_long_recall",
                "hard_source_budget",
                "hard_conflict_update",
                "noise_position_recall",
                "session_distractor_recall",
            )
        )
    ]
    hard_conflict_cases = [
        case for case in cases if case.case_id.startswith("hard_conflict_update")
    ]
    noise_position_cases = [
        case for case in cases if case.case_id.startswith("noise_position_recall")
    ]
    boundary_cases = [
        case for case in cases if case.case_id.startswith("session_distractor_recall")
    ]
    marker_ablation_cases = [
        case for case in cases if case.case_id.startswith("marker_ablation_recall")
    ]
    dropped_page_audit_cases = [
        case for case in cases if case.case_id.startswith("dropped_page_audit")
    ]

    assert len(cases) == 81
    assert multi_cases
    assert all(len(case.expected_facts) == 2 for case in multi_cases)
    assert all(case.required_fact_sources for case in multi_cases)
    assert len(multi_cases) == 8
    assert len(hard_cases) == 40
    assert len(hard_conflict_cases) == 8
    assert len(noise_position_cases) == 8
    assert len(boundary_cases) == 8
    assert len(marker_ablation_cases) == 8
    assert len(dropped_page_audit_cases) == 1


def test_marker_ablation_cases_do_not_use_evidence_boost_markers():
    marker_words = ("最终", "不做", "主线", "改为", "更新")
    cases = [case for case in builtin_cases() if case.case_id.startswith("marker_ablation_recall")]

    assert cases
    for case in cases:
        case_text = (
            case.question + "\n" + "\n".join(message.content for message in case.conversation)
        )
        assert not any(marker in case_text for marker in marker_words)
