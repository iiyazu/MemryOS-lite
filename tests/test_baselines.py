import pytest

from memoryos_eval.baselines import (
    EvidenceItem,
    _baseline_from_evidence,
    _metadata_string_list_prefer,
    _needs_multi_evidence,
)


def test_evidence_selection_skips_generic_acknowledgements():
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


def test_evidence_selection_prefers_update_evidence_for_slot_questions():
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


def test_projects_final_answer_without_stale_prefix():
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
