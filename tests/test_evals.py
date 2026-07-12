import json

import pytest
from pydantic import ValidationError

from memoryos_lite.cli import _llm_judge_table_rows
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import (
    BaselineOutput,
    EvidenceItem,
    _baseline_from_evidence,
    _materialize_messages,
    _metadata_string_list_prefer,
    _needs_multi_evidence,
    _run_baseline,
    _score,
    builtin_cases,
    run_eval,
)
from memoryos_lite.llm_judge import JudgeVerdict
from memoryos_lite.schemas import EvalCase, MessageCreate, Role
from memoryos_lite.store import create_store

slow = pytest.mark.slow


@pytest.fixture(scope="module")
def _eval_v1_memoryos(tmp_path_factory):
    """Shared run_eval(v1, memoryos_lite) — reused by report/cli/source tests."""
    base = tmp_path_factory.mktemp("eval_v1_memoryos")
    settings = Settings(
        data_dir=base / ".memoryos",
        memoryos_memory_arch="v1",
        memoryos_paging_mode="heuristic",
    )
    results = run_eval(settings, run_id="shared-v1", baselines=["memoryos_lite"], isolated=True)
    report = json.loads((settings.data_dir / "evals" / "shared-v1.json").read_text())
    return {"settings": settings, "results": results, "report": report}


@pytest.fixture(scope="module")
def _eval_default_memoryos(tmp_path_factory):
    """Shared run_eval(default/v3, memoryos_lite) — reused by trace/snippet tests."""
    base = tmp_path_factory.mktemp("eval_default_memoryos")
    settings = Settings(data_dir=base / ".memoryos", openai_api_key="dummy")
    results = run_eval(settings, run_id="shared-default", baselines=["memoryos_lite"])
    report = json.loads((settings.data_dir / "evals" / "shared-default.json").read_text())
    trace_dir = settings.data_dir / "eval_runs" / "shared-default" / "traces"
    return {"settings": settings, "results": results, "report": report, "trace_dir": trace_dir}


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


def test_builtin_case_message_ids_are_stable():
    case = builtin_cases()[0]

    first = _materialize_messages(case)
    second = _materialize_messages(case)

    assert [message.id for message in first] == [message.id for message in second]
    assert first[0].id == case.required_sources[0]


def test_eval_evidence_selection_skips_generic_acknowledgements():
    selected = _baseline_from_evidence(
        "项目最终截止日期是哪天？",
        [
            EvidenceItem(
                text="已记录最终截止日期。",
                source_texts={"ack": "已记录最终截止日期。"},
                origin="retrieved_message",
            ),
            EvidenceItem(
                text="截止日期最终确定 11 月 1 日。",
                source_texts={"final": "截止日期最终确定 11 月 1 日。"},
                origin="retrieved_message",
            ),
        ],
        context_tokens=20,
    )

    assert selected.answer == "截止日期最终确定 11 月 1 日"
    assert selected.sources["final"] == "截止日期最终确定 11 月 1 日。"


def test_eval_evidence_selection_prefers_update_evidence_for_slot_questions():
    selected = _baseline_from_evidence(
        "RPC 框架用什么？",
        [
            EvidenceItem(
                text="架构设计：RPC 框架用 gRPC。",
                source_texts={"old": "架构设计：RPC 框架用 gRPC。"},
                origin="retrieved_message",
            ),
            EvidenceItem(
                text="与合作团队对接，RPC 框架采用 Thrift。",
                source_texts={"new": "与合作团队对接，RPC 框架采用 Thrift。"},
                origin="retrieved_message",
            ),
        ],
        context_tokens=20,
    )

    assert selected.answer == "Thrift"
    assert selected.sources["new"] == "与合作团队对接，RPC 框架采用 Thrift。"


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


@slow
def test_memoryos_baseline_preserves_required_sources(_eval_v1_memoryos):
    results = _eval_v1_memoryos["results"]

    assert results
    assert all(result.source_accuracy == 1.0 for result in results)


@slow
def test_memoryos_v3_default_preserves_hard_eval_source_accuracy(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")

    results = run_eval(
        settings,
        run_id="hard-default-v3",
        baselines=["memoryos_lite"],
        isolated=True,
        case_set="hard",
    )

    assert results
    assert all(result.source_accuracy == 1.0 for result in results)


@slow
def test_hard_cases_preserve_baseline_differentiation(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")

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


def test_metadata_string_list_prefers_recall_keys_over_legacy_keys():
    metadata = {
        "recall_candidate_message_ids": ["recall_a", "recall_b"],
        "episode_candidate_message_ids": ["legacy_a"],
    }

    assert _metadata_string_list_prefer(
        metadata,
        primary_key="recall_candidate_message_ids",
        fallback_key="episode_candidate_message_ids",
    ) == ["recall_a", "recall_b"]
